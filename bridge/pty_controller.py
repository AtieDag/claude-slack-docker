"""PTY controller for spawning and managing Claude Code."""

import fcntl
import logging
import os
import pty
import select
import signal
import struct
import termios
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class PTYController:
    """Controller for managing Claude Code in a PTY."""

    def __init__(
        self,
        working_dir: str = "/workspace",
        on_output: Optional[Callable[[str], None]] = None,
    ):
        self.working_dir = working_dir
        self.on_output = on_output
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.running = False
        self.output_buffer = ""
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Start Claude Code in a PTY."""
        if self.running:
            logger.warning("Claude Code is already running")
            return False

        try:
            # Create pseudo-terminal
            self.master_fd, self.slave_fd = pty.openpty()

            # Set terminal size (80x24 is standard)
            self._set_terminal_size(80, 24)

            # Fork the process
            self.pid = os.fork()

            if self.pid == 0:
                # Child process
                os.close(self.master_fd)

                # Create new session and set controlling terminal
                os.setsid()

                # Set up slave as stdin/stdout/stderr
                os.dup2(self.slave_fd, 0)
                os.dup2(self.slave_fd, 1)
                os.dup2(self.slave_fd, 2)

                if self.slave_fd > 2:
                    os.close(self.slave_fd)

                # Change to working directory
                os.chdir(self.working_dir)

                # Set environment
                env = os.environ.copy()
                env["TERM"] = "xterm-256color"
                env["HOME"] = os.environ.get("HOME", "/root")

                # Execute Claude Code - interactive mode
                os.execvpe("claude", ["claude"], env)

            else:
                # Parent process
                os.close(self.slave_fd)
                self.slave_fd = None
                self.running = True

                # Make master_fd non-blocking
                flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
                fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                # Start output reader thread
                self._reader_thread = threading.Thread(
                    target=self._read_output, daemon=True
                )
                self._reader_thread.start()

                logger.info(f"Started Claude Code with PID {self.pid}")

                # Wait for Claude to initialize and handle initial prompts
                time.sleep(5)  # Give Claude more time to fully render prompts

                # Handle prompts sequentially with proper timing
                try:
                    # First Enter for trust dialog (cursor is on "Yes, proceed")
                    os.write(self.master_fd, b"\r")
                    logger.info("Sent Enter for trust dialog")
                    time.sleep(2)  # Wait for API key prompt

                    # API key dialog has "No" selected by default - move UP to "Yes"
                    os.write(self.master_fd, b"\x1b[A")  # Up arrow
                    logger.info("Sent Up arrow to select 'Yes' for API key")
                    time.sleep(0.3)

                    # Enter to confirm API key
                    os.write(self.master_fd, b"\r")
                    logger.info("Sent Enter for API key dialog")
                    time.sleep(3)

                    # Additional Enter for any other prompts
                    os.write(self.master_fd, b"\r")
                    logger.info("Sent additional Enter")
                except OSError:
                    pass

                return True

        except Exception as e:
            logger.error(f"Failed to start Claude Code: {e}")
            self._cleanup()
            return False

    def _set_terminal_size(self, cols: int, rows: int) -> None:
        """Set the terminal size."""
        if self.master_fd is not None:
            size = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)

    def _read_output(self) -> None:
        """Read output from PTY in background thread."""
        while self.running and self.master_fd is not None:
            try:
                # Use select to wait for data
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)

                if ready:
                    try:
                        data = os.read(self.master_fd, 4096)
                        if data:
                            text = data.decode("utf-8", errors="replace")
                            with self._lock:
                                self.output_buffer += text
                            if self.on_output:
                                self.on_output(text)
                    except OSError:
                        break

            except (ValueError, OSError):
                break

    def send_input(self, text: str) -> bool:
        """Send input to Claude Code."""
        if not self.running or self.master_fd is None:
            logger.warning("Cannot send input: Claude Code not running")
            return False

        try:
            # Send the text first
            os.write(self.master_fd, text.encode("utf-8"))
            # Small delay to ensure text is processed
            time.sleep(0.1)
            # Send carriage return (Enter key) separately
            os.write(self.master_fd, b"\r")
            logger.info(f"Sent input to Claude Code: {text[:50]}...")
            return True
        except OSError as e:
            logger.error(f"Failed to send input: {e}")
            return False

    def get_output(self, clear: bool = True) -> str:
        """Get accumulated output from buffer."""
        with self._lock:
            output = self.output_buffer
            if clear:
                self.output_buffer = ""
            return output

    def is_running(self) -> bool:
        """Check if Claude Code is still running."""
        if not self.running or self.pid is None:
            return False

        try:
            # Check if process is still alive
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid != 0:
                # Process has exited
                self.running = False
                logger.info(f"Claude Code exited with status {status}")
                return False
            return True
        except ChildProcessError:
            self.running = False
            return False

    def stop(self) -> None:
        """Stop Claude Code."""
        if not self.running:
            return

        logger.info("Stopping Claude Code...")

        # Send interrupt signal
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGINT)
                # Give it a moment to clean up
                for _ in range(10):
                    try:
                        pid, _ = os.waitpid(self.pid, os.WNOHANG)
                        if pid != 0:
                            break
                    except ChildProcessError:
                        break
                    time.sleep(0.1)
                else:
                    # Force kill if still running
                    os.kill(self.pid, signal.SIGKILL)
                    os.waitpid(self.pid, 0)
            except (OSError, ProcessLookupError):
                pass

        self._cleanup()
        logger.info("Claude Code stopped")

    def _cleanup(self) -> None:
        """Clean up resources."""
        self.running = False

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except OSError:
                pass
            self.slave_fd = None

        self.pid = None

    def restart(self) -> bool:
        """Restart Claude Code."""
        self.stop()
        return self.start()


class PTYManager:
    """Manager for PTY controller with session tracking."""

    _instance: Optional["PTYManager"] = None
    _controller: Optional[PTYController] = None
    _session_id: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "PTYManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def initialize(
        cls,
        working_dir: str = "/workspace",
        on_output: Optional[Callable[[str], None]] = None,
    ) -> "PTYManager":
        """Initialize the PTY manager."""
        instance = cls.get_instance()
        instance._controller = PTYController(working_dir, on_output)
        return instance

    @classmethod
    def get_controller(cls) -> Optional[PTYController]:
        """Get the PTY controller."""
        instance = cls.get_instance()
        return instance._controller

    @classmethod
    def start_claude(cls) -> bool:
        """Start Claude Code."""
        instance = cls.get_instance()
        if instance._controller:
            return instance._controller.start()
        return False

    @classmethod
    def stop_claude(cls) -> None:
        """Stop Claude Code."""
        instance = cls.get_instance()
        if instance._controller:
            instance._controller.stop()

    @classmethod
    def send_input(cls, text: str) -> bool:
        """Send input to Claude Code."""
        instance = cls.get_instance()
        if instance._controller:
            return instance._controller.send_input(text)
        return False

    @classmethod
    def is_running(cls) -> bool:
        """Check if Claude Code is running."""
        instance = cls.get_instance()
        if instance._controller:
            return instance._controller.is_running()
        return False

    @classmethod
    def set_session_id(cls, session_id: str) -> None:
        """Set the session ID."""
        instance = cls.get_instance()
        instance._session_id = session_id

    @classmethod
    def get_session_id(cls) -> Optional[str]:
        """Get the session ID."""
        instance = cls.get_instance()
        return instance._session_id
