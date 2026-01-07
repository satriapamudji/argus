"""Signal handling for graceful shutdown.

Handles SIGTERM and SIGINT for clean daemon shutdown.
"""

import asyncio
import logging
import signal
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class SignalHandler:
    """Handles shutdown signals for the daemon.

    Registers handlers for SIGTERM and SIGINT that trigger
    a graceful shutdown of the daemon.

    Usage:
        handler = SignalHandler()
        handler.register(loop, shutdown_callback)
        # ... daemon runs ...
        await handler.wait_for_shutdown()
    """

    def __init__(self) -> None:
        """Initialize the signal handler."""
        self._shutdown_event: Optional[asyncio.Event] = None
        self._shutdown_callback: Optional[Callable[[], None]] = None
        self._received_signal: Optional[signal.Signals] = None

    def register(
        self,
        loop: asyncio.AbstractEventLoop,
        shutdown_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """Register signal handlers.

        Args:
            loop: The asyncio event loop.
            shutdown_callback: Optional callback to run on shutdown.
        """
        self._shutdown_event = asyncio.Event()
        self._shutdown_callback = shutdown_callback

        # Register handlers for graceful shutdown signals
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig)
                logger.debug(f"Registered handler for {sig.name}")
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                # Fall back to signal.signal
                signal.signal(sig, self._handle_signal_sync)
                logger.debug(f"Registered sync handler for {sig.name} (Windows fallback)")

    def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle a shutdown signal (Unix).

        Args:
            sig: The signal received.
        """
        logger.info(f"Received {sig.name}, initiating graceful shutdown...")
        self._received_signal = sig

        if self._shutdown_callback:
            self._shutdown_callback()

        if self._shutdown_event:
            self._shutdown_event.set()

    def _handle_signal_sync(
        self,
        signum: int,
        frame: object,  # noqa: ARG002
    ) -> None:
        """Handle a shutdown signal (Windows fallback).

        Args:
            signum: The signal number.
            frame: Current stack frame (unused).
        """
        sig = signal.Signals(signum)
        self._handle_signal(sig)

    async def wait_for_shutdown(self) -> Optional[signal.Signals]:
        """Wait for a shutdown signal.

        Returns:
            The signal that triggered shutdown, or None if not triggered.
        """
        if self._shutdown_event:
            await self._shutdown_event.wait()
        return self._received_signal

    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_event is not None and self._shutdown_event.is_set()
