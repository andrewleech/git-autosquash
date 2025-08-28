"""UI management controllers for robust event-driven TUI coordination."""

import asyncio
from typing import Dict, List, Callable, TYPE_CHECKING
from enum import Enum, auto

from textual.widget import Widget

if TYPE_CHECKING:
    pass


class UIState(Enum):
    """UI lifecycle states."""

    INITIALIZING = auto()
    MOUNTED = auto()
    FOCUS_READY = auto()
    SCROLL_READY = auto()
    FULLY_READY = auto()


class FocusController:
    """Manages focus state coordination without timing dependencies."""

    def __init__(self, widget: Widget) -> None:
        self.widget = widget
        self.focus_ready = asyncio.Event()
        self.focus_targets: Dict[str, Widget] = {}
        self._cleanup_tasks: List[asyncio.Task] = []

    async def wait_for_focus_ready(self) -> None:
        """Wait for focus system to be ready."""
        await self.focus_ready.wait()

    def mark_focus_ready(self) -> None:
        """Mark focus system as ready."""
        self.focus_ready.set()

    def register_focus_target(self, target_id: str, widget: Widget) -> None:
        """Register a widget that can receive focus."""
        self.focus_targets[target_id] = widget

    async def set_focus_to_selected(self, radio_set_id: str) -> bool:
        """Set focus to the currently selected radio button in a RadioSet.

        Returns:
            True if focus was set successfully, False otherwise
        """
        try:
            if radio_set_id not in self.focus_targets:
                return False

            radio_set = self.focus_targets[radio_set_id]
            if not hasattr(radio_set, "query") or not hasattr(radio_set, "focus"):
                return False

            # Find selected button using Textual's query system
            try:
                selected_buttons = radio_set.query("RadioButton").filter(
                    lambda btn: getattr(btn, "value", False)
                )
                if selected_buttons:
                    selected_button = selected_buttons.first()
                    # Focus the RadioSet, then navigate to selected button
                    radio_set.focus()

                    # Use RadioSet's internal navigation to reach the selected button
                    all_buttons = radio_set.query("RadioButton").results()
                    selected_index = None

                    for i, button in enumerate(all_buttons):
                        if button is selected_button:
                            selected_index = i
                            break

                    if selected_index is not None and selected_index > 0:
                        # Navigate to the selected position
                        for _ in range(selected_index):
                            if hasattr(radio_set, "action_next_button"):
                                radio_set.action_next_button()

                    return True

            except Exception:
                # Fallback to just focusing the RadioSet
                radio_set.focus()
                return True

        except Exception:
            return False

        return False

    def cleanup(self) -> None:
        """Clean up resources and cancel pending tasks."""
        for task in self._cleanup_tasks:
            if not task.done():
                task.cancel()
        self._cleanup_tasks.clear()
        self.focus_targets.clear()


class ScrollManager:
    """Centralized scroll state management."""

    def __init__(self) -> None:
        self._target_position = (0, 0)
        self._scroll_lock = asyncio.Lock()
        self._scroll_targets: Dict[str, Widget] = {}
        self._scroll_ready = asyncio.Event()

    def register_scroll_target(self, target_id: str, widget: Widget) -> None:
        """Register a widget that can be scrolled."""
        self._scroll_targets[target_id] = widget

    def mark_scroll_ready(self) -> None:
        """Mark scroll system as ready."""
        self._scroll_ready.set()

    async def wait_for_scroll_ready(self) -> None:
        """Wait for scroll system to be ready."""
        await self._scroll_ready.wait()

    async def scroll_to_top(self, target_id: str) -> bool:
        """Scroll target widget to top position.

        Args:
            target_id: ID of the scroll target to move to top

        Returns:
            True if scroll was successful, False otherwise
        """
        async with self._scroll_lock:
            try:
                if target_id not in self._scroll_targets:
                    return False

                widget = self._scroll_targets[target_id]
                if hasattr(widget, "scroll_to"):
                    widget.scroll_to(0, 0, animate=False)
                    self._target_position = (0, 0)
                    return True

            except Exception:
                return False

        return False

    def cleanup(self) -> None:
        """Clean up scroll targets."""
        self._scroll_targets.clear()


class UILifecycleManager:
    """Coordinates UI lifecycle without timing dependencies."""

    def __init__(self, widget: Widget) -> None:
        self.widget = widget
        self.focus_controller = FocusController(widget)
        self.scroll_manager = ScrollManager()
        self.state = UIState.INITIALIZING
        self._ready_callbacks: List[Callable[[], None]] = []
        self._cleanup_callbacks: List[Callable[[], None]] = []

    def register_ready_callback(self, callback: Callable[[], None]) -> None:
        """Register callback to run when UI is fully ready."""
        if self.state == UIState.FULLY_READY:
            # Already ready, execute immediately
            try:
                callback()
            except Exception as e:
                # Log but don't crash
                if hasattr(self.widget, "log"):
                    self.widget.log.error(f"Ready callback failed: {e}")
        else:
            self._ready_callbacks.append(callback)

    def register_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """Register cleanup callback for unmount."""
        self._cleanup_callbacks.append(callback)

    def advance_to_mounted(self) -> None:
        """Advance to mounted state."""
        if self.state == UIState.INITIALIZING:
            self.state = UIState.MOUNTED
            self._check_ready_state()

    def advance_to_focus_ready(self) -> None:
        """Advance to focus ready state."""
        if self.state in (UIState.INITIALIZING, UIState.MOUNTED):
            self.state = UIState.FOCUS_READY
            self.focus_controller.mark_focus_ready()
            self._check_ready_state()

    def advance_to_scroll_ready(self) -> None:
        """Advance to scroll ready state."""
        if self.state in (UIState.INITIALIZING, UIState.MOUNTED, UIState.FOCUS_READY):
            self.state = UIState.SCROLL_READY
            self.scroll_manager.mark_scroll_ready()
            self._check_ready_state()

    def _check_ready_state(self) -> None:
        """Check if we can advance to fully ready."""
        if (
            self.state in (UIState.FOCUS_READY, UIState.SCROLL_READY)
            and self.focus_controller.focus_ready.is_set()
            and self.scroll_manager._scroll_ready.is_set()
        ):
            self.state = UIState.FULLY_READY
            self._execute_ready_callbacks()

    def _execute_ready_callbacks(self) -> None:
        """Execute all ready callbacks."""
        for callback in self._ready_callbacks:
            try:
                callback()
            except Exception as e:
                if hasattr(self.widget, "log"):
                    self.widget.log.error(f"Ready callback failed: {e}")
        self._ready_callbacks.clear()

    def cleanup(self) -> None:
        """Clean up all resources."""
        # Execute cleanup callbacks
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                if hasattr(self.widget, "log"):
                    self.widget.log.error(f"Cleanup callback failed: {e}")

        # Clean up controllers
        self.focus_controller.cleanup()
        self.scroll_manager.cleanup()

        # Clear callbacks
        self._ready_callbacks.clear()
        self._cleanup_callbacks.clear()
