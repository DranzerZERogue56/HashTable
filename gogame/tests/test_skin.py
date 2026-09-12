"""Tests for the procedural textures.

skin.py imports no UI framework, so these run without a display and
without Kivy -- which is the reason the pixel arithmetic lives there
rather than inside app.py.
"""

import pytest

from gogame import skin


def _rgba(pixels, width, x, y):
    i = (y * width + x) * 4
    return tuple(pixels[i:i + 4])


def _alpha(pixels, width, x, y):
    return _rgba(pixels, width, x, y)[3]


def _luma(pixel):
    r, g, b, _a = pixel
    return 0.299 * r + 0.587 * g + 0.114 * b


# -- stones ---------------------------------------------------------------


def test_stone_buffer_is_rgba_of_the_requested_size():
    pixels, width, height = skin.stone_pixels(32, skin.BLACK_STONE)
    assert (width, height) == (32, 32)
    assert len(pixels) == 32 * 32 * 4


def test_stone_is_opaque_in_the_middle_and_clear_at_the_corners():
    pixels, width, _h = skin.stone_pixels(64, skin.WHITE_STONE)
    assert _alpha(pixels, width, 32, 32) == 255
    for corner in ((0, 0), (63, 0), (0, 63), (63, 63)):
        assert _alpha(pixels, width, *corner) == 0


def test_stone_edge_is_antialiased_rather_than_a_hard_cutoff():
    """The whole reason for a texture instead of a GL Ellipse.

    Somewhere along a radius there have to be partially covered texels; a
    hard edge would jump 255 -> 0.
    """
    pixels, width, _h = skin.stone_pixels(64, skin.BLACK_STONE)
    row = [_alpha(pixels, width, x, 32) for x in range(width)]
    assert any(0 < a < 255 for a in row)


def test_stone_is_lit_from_the_upper_left():
    """Which is also what pins down the row order skin.py documents.

    If app.py stopped flipping the texture, or these rows were emitted
    bottom-first, the stones would be lit from below and look like holes.
    """
    pixels, width, _h = skin.stone_pixels(64, skin.WHITE_STONE)
    upper_left = _luma(_rgba(pixels, width, 22, 22))
    lower_right = _luma(_rgba(pixels, width, 42, 42))
    assert upper_left > lower_right


def test_gloss_brightens_the_highlight_without_moving_it():
    dull, width, _h = skin.stone_pixels(64, skin.BLACK_STONE, gloss=0.0)
    shiny, _w, _h2 = skin.stone_pixels(64, skin.BLACK_STONE, gloss=0.9)
    assert _luma(_rgba(shiny, width, 22, 22)) > _luma(_rgba(dull, width, 22, 22))


def test_stone_rejects_a_size_too_small_to_shade():
    with pytest.raises(ValueError):
        skin.stone_pixels(2, skin.BLACK_STONE)


# -- flat marks -----------------------------------------------------------


def test_disc_is_solid_in_the_middle_and_clear_outside():
    pixels, width, _h = skin.disc_pixels(32, skin.MARKER)
    assert _alpha(pixels, width, 16, 16) == 255
    assert _alpha(pixels, width, 0, 0) == 0


def test_disc_carries_the_colour_it_was_given():
    pixels, width, _h = skin.disc_pixels(32, (1.0, 0.0, 0.0))
    assert _rgba(pixels, width, 16, 16) == (255, 0, 0, 255)


def test_ring_is_hollow():
    pixels, width, _h = skin.ring_pixels(64, skin.MARKER, thickness=0.2)
    centre = _alpha(pixels, width, 32, 32)
    band = _alpha(pixels, width, 32, 2)  # just inside the top edge
    assert centre == 0
    assert band > 0


def test_cross_covers_its_diagonals_and_not_the_axes():
    pixels, width, _h = skin.cross_pixels(64, skin.MARKER, thickness=0.2)
    assert _alpha(pixels, width, 32, 32) > 0  # centre, where the arms meet
    assert _alpha(pixels, width, 20, 20) > 0  # along one arm
    assert _alpha(pixels, width, 44, 20) > 0  # along the other
    assert _alpha(pixels, width, 32, 8) == 0  # straight up: between arms


def test_shadow_fades_outward_and_is_clear_at_the_rim():
    pixels, width, _h = skin.soft_shadow_pixels(64, strength=0.5)
    middle = _alpha(pixels, width, 32, 32)
    partway = _alpha(pixels, width, 32, 12)
    assert middle > partway > 0
    assert _alpha(pixels, width, 0, 0) == 0


def test_shadow_strength_scales_the_darkest_point():
    faint, width, _h = skin.soft_shadow_pixels(64, strength=0.2)
    heavy, _w, _h2 = skin.soft_shadow_pixels(64, strength=0.8)
    assert _alpha(heavy, width, 32, 32) > _alpha(faint, width, 32, 32)


# -- wood -----------------------------------------------------------------


def test_wood_fills_the_buffer_opaquely():
    pixels, width, height = skin.wood_pixels(24, 24)
    assert (width, height) == (24, 24)
    assert len(pixels) == 24 * 24 * 4
    assert all(pixels[i] == 255 for i in range(3, len(pixels), 4))


def test_wood_is_deterministic_for_a_seed():
    """The board has to look the same every launch, not reshuffle."""
    first, _w, _h = skin.wood_pixels(24, 24, seed=3)
    again, _w2, _h2 = skin.wood_pixels(24, 24, seed=3)
    assert first == again


def test_wood_grain_differs_between_seeds():
    first, _w, _h = skin.wood_pixels(24, 24, seed=3)
    other, _w2, _h2 = skin.wood_pixels(24, 24, seed=4)
    assert first != other


def test_wood_actually_varies_rather_than_being_a_flat_fill():
    pixels, width, _h = skin.wood_pixels(32, 32)
    reds = {_rgba(pixels, width, x, y)[0] for x in range(32) for y in range(32)}
    assert len(reds) > 8


def test_wood_edges_are_darker_than_the_middle():
    """The vignette is what gives the slab apparent thickness."""
    pixels, width, _h = skin.wood_pixels(64, 64, vignette=0.3, sheen=0.0, grain=0.0,
                                        speckle=0.0)
    assert _luma(_rgba(pixels, width, 32, 32)) > _luma(_rgba(pixels, width, 1, 1))


def test_wood_rejects_a_degenerate_size():
    with pytest.raises(ValueError):
        skin.wood_pixels(1, 10)


# -- palette --------------------------------------------------------------


def test_palette_entries_are_normalised_rgb_triples():
    names = [
        "SLAB_WOOD", "TABLE_WOOD", "GRID_LINE", "BLACK_STONE", "WHITE_STONE",
        "MARKER", "PANEL_BG", "PANEL_EDGE", "TEXT", "TEXT_MUTED",
        "BUTTON_BG", "BUTTON_TEXT",
    ]
    for name in names:
        color = getattr(skin, name)
        assert len(color) == 3, name
        assert all(0.0 <= channel <= 1.0 for channel in color), name


def test_stone_colours_are_far_enough_apart_to_tell_apart():
    assert _luma((*[c * 255 for c in skin.WHITE_STONE], 255)) - _luma(
        (*[c * 255 for c in skin.BLACK_STONE], 255)
    ) > 150
