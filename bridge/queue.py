"""In-memory message queue for handling rapid messages."""

import asyncio
import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class MessageQueue:
    """In-memory queue for handling messages per session.

    Messages are queued and processed sequentially to avoid
    overwhelming Claude Code with rapid inputs.
    """

    def __init__(
        self,
        send_callback: Callable[[str, str], bool],
        delay_between_messages: float = 0.5,
    ):
        """Initialize the message queue.

        Args:
            send_callback: Function to send message to tmux (session, message) -> success
            delay_between_messages: Delay in seconds between processing messages
        """
        self.queues: Dict[str, asyncio.Queue] = {}
        self.processors: Dict[str, asyncio.Task] = {}
        self.send_callback = send_callback
        self.delay = delay_between_messages
        self._running = True

    async def enqueue(self, session_id: str, message: str) -> None:
        """Add message to session queue.

        Creates a new queue and processor if needed.
        """
        if session_id not in self.queues:
            self.queues[session_id] = asyncio.Queue()
            self.processors[session_id] = asyncio.create_task(
                self._process_queue(session_id)
            )
            logger.info(f"Created queue for session: {session_id}")

        await self.queues[session_id].put(message)
        logger.debug(f"Enqueued message for session {session_id}: {message[:50]}...")

    async def _process_queue(self, session_id: str) -> None:
        """Process messages sequentially for a session."""
        logger.info(f"Started queue processor for session: {session_id}")

        while self._running:
            try:
                # Wait for next message with timeout
                try:
                    message = await asyncio.wait_for(
                        self.queues[session_id].get(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    # Check if queue is empty and should be cleaned up
                    if self.queues[session_id].empty():
                        continue
                    continue

                # Send message
                success = self.send_callback(session_id, message)
                if success:
                    logger.debug(f"Sent message to session {session_id}")
                else:
                    logger.warning(f"Failed to send message to session {session_id}")

                # Small delay between messages
                await asyncio.sleep(self.delay)

            except asyncio.CancelledError:
                logger.info(f"Queue processor cancelled for session: {session_id}")
                break
            except Exception as e:
                logger.error(f"Error processing queue for {session_id}: {e}")
                await asyncio.sleep(1.0)  # Back off on error

    def get_queue_size(self, session_id: str) -> int:
        """Get the number of pending messages for a session."""
        if session_id in self.queues:
            return self.queues[session_id].qsize()
        return 0

    async def clear_queue(self, session_id: str) -> int:
        """Clear all pending messages for a session.

        Returns the number of messages cleared.
        """
        if session_id not in self.queues:
            return 0

        count = 0
        while not self.queues[session_id].empty():
            try:
                self.queues[session_id].get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break

        return count

    async def remove_session(self, session_id: str) -> None:
        """Remove a session and its queue."""
        if session_id in self.processors:
            self.processors[session_id].cancel()
            try:
                await self.processors[session_id]
            except asyncio.CancelledError:
                pass
            del self.processors[session_id]

        if session_id in self.queues:
            del self.queues[session_id]

        logger.info(f"Removed queue for session: {session_id}")

    async def shutdown(self) -> None:
        """Shutdown all queue processors."""
        self._running = False

        for session_id in list(self.processors.keys()):
            await self.remove_session(session_id)

        logger.info("Message queue shutdown complete")
