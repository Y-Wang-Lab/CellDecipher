"""Progress indicator components."""

import streamlit as st
from contextlib import contextmanager
from typing import List, Optional


def show_progress(current: int, total: int, message: str = "") -> None:
    """Display a progress bar with optional message."""
    progress = current / total if total > 0 else 0
    st.progress(progress, text=message)


@contextmanager
def analysis_progress(steps: List[str], container=None):
    """Context manager for multi-step analysis progress tracking.

    Usage:
        with analysis_progress(["Step 1", "Step 2", "Step 3"]) as progress:
            # Do step 1
            progress.update(0)
            # Do step 2
            progress.update(1)
            # Do step 3
            progress.update(2)
    """
    if container is None:
        container = st.container()

    with container:
        progress_bar = st.progress(0)
        status_text = st.empty()

    class ProgressUpdater:
        def __init__(self):
            self.current = 0
            self.total = len(steps)

        def update(self, step_idx: int, extra_message: str = "") -> None:
            self.current = step_idx
            progress = (step_idx + 1) / self.total
            progress_bar.progress(progress)
            message = f"Step {step_idx + 1}/{self.total}: {steps[step_idx]}"
            if extra_message:
                message += f" - {extra_message}"
            status_text.text(message)

        def complete(self, message: str = "Analysis complete!") -> None:
            progress_bar.progress(1.0)
            status_text.text(message)

        def error(self, message: str) -> None:
            status_text.error(message)

    updater = ProgressUpdater()
    try:
        yield updater
        updater.complete()
    except Exception as e:
        updater.error(f"Error: {str(e)}")
        raise


def spinner_with_status(message: str = "Processing..."):
    """Simple spinner with status message."""
    return st.spinner(message)


class StepProgress:
    """Class for tracking multi-step progress in Streamlit."""

    def __init__(self, steps: List[str], container=None):
        self.steps = steps
        self.total = len(steps)
        self.current = 0

        if container is None:
            container = st.container()

        with container:
            self.progress_bar = st.progress(0)
            self.status = st.empty()
            self.details = st.empty()

    def start(self) -> None:
        """Start progress tracking."""
        self.current = 0
        self._update_display()

    def next(self, details: str = "") -> None:
        """Move to next step."""
        self.current += 1
        self._update_display(details)

    def set_step(self, step_idx: int, details: str = "") -> None:
        """Set current step explicitly."""
        self.current = step_idx
        self._update_display(details)

    def _update_display(self, details: str = "") -> None:
        """Update the progress display."""
        progress = min(self.current / self.total, 1.0)
        self.progress_bar.progress(progress)

        if self.current < self.total:
            self.status.markdown(f"**{self.steps[self.current]}** ({self.current + 1}/{self.total})")
        else:
            self.status.markdown("**Complete!**")

        if details:
            self.details.caption(details)
        else:
            self.details.empty()

    def complete(self, message: str = "All steps completed successfully!") -> None:
        """Mark as complete."""
        self.progress_bar.progress(1.0)
        self.status.success(message)
        self.details.empty()

    def error(self, message: str) -> None:
        """Show error state."""
        self.status.error(message)
