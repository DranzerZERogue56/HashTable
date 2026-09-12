"""Tests for the system-bar inset helper.

Only the part that can be tested off a phone: the value type, and that
every path is inert when there is no Android underneath. The JNI reads
themselves need a device, and are written so that any failure returns
None and the app carries on exactly as it did before the module existed.
"""

from gogame import safearea
from gogame.safearea import Insets


def test_insets_default_to_nothing_in_the_way():
    insets = Insets()
    assert (insets.left, insets.top, insets.right, insets.bottom) == (0, 0, 0, 0)
    assert insets.is_zero


def test_any_nonzero_edge_stops_it_being_zero():
    assert not Insets(bottom=144).is_zero
    assert not Insets(top=96).is_zero
    assert not Insets(left=48).is_zero
    assert not Insets(right=48).is_zero


def test_padding_is_in_kivys_order():
    """Kivy wants [left, top, right, bottom]; Android reports the same
    four edges, and getting the order wrong would pad the top by the
    navigation bar."""
    assert Insets(1, 2, 3, 4).padding() == [1, 2, 3, 4]


def test_insets_compare_by_value():
    """SafeArea only re-lays-out when the value changes, so this is what
    stops it thrashing on every poll."""
    assert Insets(0, 96, 0, 144) == Insets(0, 96, 0, 144)
    assert Insets(0, 96, 0, 144) != Insets(0, 96, 0, 0)


def test_not_android_in_a_test_run():
    assert safearea.is_android() is False


def test_nothing_is_in_the_way_off_android():
    assert safearea.current().is_zero


def test_start_and_refresh_are_inert_off_android():
    """They must not raise where there is no jnius to import: the desktop
    CLI runs this same code."""
    safearea.start()
    safearea.refresh()
    assert safearea.current().is_zero
