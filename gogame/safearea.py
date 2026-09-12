"""System-bar insets, so nothing important sits under Android's own UI.

A Samsung phone puts the status bar across the top and either three
navigation buttons or a gesture bar across the bottom. Whether those
overlap the app depends on the Android version:

- Up to Android 14 the framework shrinks the app window to fit between
  them, and an app that does nothing is already correct.
- Android 15 (API 35) forces *edge-to-edge* on any app targeting SDK 35
  or above. buildozer.spec sets `android.api = 36`, so this app qualifies:
  the window covers the whole screen and the bars are drawn on top of it.
  The bottom row of buttons ends up underneath the navigation bar.

p4a does nothing about this -- there is no inset handling anywhere in the
bootstrap, and its `KivySupportCutout` theme only sets `windowNoTitle`
unless `android.display_cutout` is turned on, which it is not here.

So this module asks Android for the bar sizes and app.py keeps the UI
clear of them. It is deliberately the only Android-specific code in the
package, it imports no UI framework, and every failure path returns zero
insets -- which is exactly the behaviour the app had before it existed.

The window is only switched to edge-to-edge *after* the insets have been
read successfully. Doing it the other way round would mean that a failed
read on Android 12 to 14 left the buttons under the navigation bar on
devices where they are fine today.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

__all__ = ["Insets", "current", "start", "refresh", "is_android"]

# WindowInsets.getInsets() and setDecorFitsSystemWindows() are both API 30.
# Below that the framework fits the window itself and there is nothing to do.
_MIN_SDK = 30


@dataclass(frozen=True)
class Insets:
    """How far the system bars intrude on each edge, in pixels."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @property
    def is_zero(self) -> bool:
        return not (self.left or self.top or self.right or self.bottom)

    def padding(self) -> List[int]:
        """Kivy's padding order: left, top, right, bottom."""
        return [self.left, self.top, self.right, self.bottom]


def is_android() -> bool:
    """p4a sets ANDROID_ARGUMENT; checking it keeps this module free of
    any UI framework import."""
    return "ANDROID_ARGUMENT" in os.environ


_current = Insets()
_started = False


def current() -> Insets:
    """The last insets read. Zero everywhere that is not Android, and zero
    until the first successful read."""
    return _current


def start() -> None:
    """Read the insets and, if that worked, take the window edge-to-edge."""
    global _started
    if _started or not is_android():
        return
    _started = True
    _on_ui_thread(_configure)


def refresh() -> None:
    """Re-read after a rotation, a resume, or a change of navigation mode."""
    if is_android():
        _on_ui_thread(_store_insets)


# -- Android internals ----------------------------------------------------
#
# Everything below runs on Android's UI thread: setDecorFitsSystemWindows
# triggers a layout pass, and View getters are not promised to be safe from
# the SDL thread Kivy's loop runs on.


def _on_ui_thread(function) -> None:
    try:
        from android.runnable import run_on_ui_thread
    except ImportError:  # pragma: no cover - only importable on Android
        return
    run_on_ui_thread(function)()


def _configure() -> None:  # pragma: no cover - needs a device
    insets = _read_insets()
    if insets is None:
        return  # leave the window exactly as the framework set it up
    _set_edge_to_edge()
    _set_current(_read_insets() or insets)


def _store_insets() -> None:  # pragma: no cover - needs a device
    insets = _read_insets()
    if insets is not None:
        _set_current(insets)


def _set_current(insets: Insets) -> None:
    global _current
    _current = insets


def _read_insets() -> Optional[Insets]:  # pragma: no cover - needs a device
    """Bar sizes from Android, or None if they cannot be had.

    None rather than zero on failure, because the two mean different
    things here: zero is "there is nothing in the way", while None is
    "do not touch the window, we cannot compensate".
    """
    try:
        from jnius import autoclass

        if autoclass("android.os.Build$VERSION").SDK_INT < _MIN_SDK:
            return None
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return None
        root = activity.getWindow().getDecorView().getRootWindowInsets()
        if root is None:
            return None  # the view is not attached yet; a later refresh will get it
        types = autoclass("android.view.WindowInsets$Type")
        # The cutout as well as the bars: in portrait the notch sits inside
        # the status bar, but rotate the phone and it moves to a side edge
        # that systemBars() says nothing about.
        measured = root.getInsets(types.systemBars() | types.displayCutout())
        return Insets(
            left=int(measured.left),
            top=int(measured.top),
            right=int(measured.right),
            bottom=int(measured.bottom),
        )
    except Exception:
        return None


def _set_edge_to_edge() -> None:  # pragma: no cover - needs a device
    """Opt in explicitly, so every version from 30 up behaves the same.

    Android 15 does this to us regardless. Asking for it means there is
    one case to reason about instead of two, and that the insets read
    above are always the ones still left to apply rather than ones the
    framework may already have consumed.
    """
    try:
        from jnius import autoclass

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        activity.getWindow().setDecorFitsSystemWindows(False)
    except Exception:
        pass
