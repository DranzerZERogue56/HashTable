import pytest

from gogame.layout import (
    HIT_RADIUS_DP,
    column_label,
    compute_layout,
    pixel_at_point,
    point_at_pixel,
    row_label,
)

# (width, height, density) of the board area on phones this has to fit on,
# i.e. the screen minus the panel band.
BOARD_AREAS = [
    (1080, 1880, 2.75),  # Galaxy S21 / mid-range A-series, portrait
    (1440, 2400, 4.0),  # QHD+ flagship, portrait
    (720, 1280, 2.0),  # budget A-series, portrait
    (1780, 1080, 2.75),  # landscape, panel down the right
]
BOARD_SIZES = [9, 13, 19]


def test_column_label_skips_i():
    assert column_label(0) == "A"
    assert column_label(7) == "H"
    assert column_label(8) == "J"


def test_row_label_counts_from_bottom():
    assert row_label(0, 19) == 19
    assert row_label(18, 19) == 1


@pytest.mark.parametrize("width,height,density", BOARD_AREAS)
@pytest.mark.parametrize("size", BOARD_SIZES)
def test_board_is_square_centred_and_inside_the_area(width, height, density, size):
    layout = compute_layout(size, width, height, density)
    box = layout.board_box
    assert box.width == box.height
    assert box.x >= 0 and box.y >= 0
    assert box.right <= width and box.bottom <= height
    # centred within the area, to within a pixel of rounding
    assert abs(box.x - (width - box.width) // 2) <= 1
    assert abs(box.y - (height - box.height) // 2) <= 1


@pytest.mark.parametrize("width,height,density", BOARD_AREAS)
@pytest.mark.parametrize("size", BOARD_SIZES)
def test_every_intersection_lands_inside_the_board_box(width, height, density, size):
    layout = compute_layout(size, width, height, density)
    box = layout.board_box
    for row in range(size):
        for col in range(size):
            x, y = pixel_at_point((row, col), layout)
            assert box.x <= x <= box.right
            assert box.y <= y <= box.bottom


@pytest.mark.parametrize("width,height,density", BOARD_AREAS)
@pytest.mark.parametrize("size", BOARD_SIZES)
def test_pixel_point_round_trip_for_every_intersection(width, height, density, size):
    layout = compute_layout(size, width, height, density)
    for row in range(size):
        for col in range(size):
            x, y = pixel_at_point((row, col), layout)
            assert point_at_pixel(x, y, layout) == (row, col)


@pytest.mark.parametrize("width,height,density", BOARD_AREAS)
def test_hit_radius_respects_the_dp_floor(width, height, density):
    layout = compute_layout(19, width, height, density)
    assert layout.hit_radius >= int(HIT_RADIUS_DP * density)
    assert layout.hit_radius >= layout.cell // 2


@pytest.mark.parametrize("width,height,density", BOARD_AREAS)
def test_stones_leave_a_gap_between_neighbours(width, height, density):
    layout = compute_layout(19, width, height, density)
    assert 0 < layout.stone_radius * 2 < layout.cell + 2


def test_tap_just_outside_the_edge_still_reaches_the_corner():
    layout = compute_layout(19, 1080, 1880, 2.75)
    corner_x, corner_y = pixel_at_point((0, 0), layout)
    # a thumb landing in the margin, past the outermost line
    assert point_at_pixel(corner_x - 8, corner_y - 8, layout) == (0, 0)


def test_tap_far_outside_the_board_is_rejected():
    layout = compute_layout(9, 1080, 1880, 2.75)
    corner_x, corner_y = pixel_at_point((0, 0), layout)
    off = layout.hit_radius * 3
    assert point_at_pixel(corner_x - off, corner_y - off, layout) is None
    # below the board entirely, e.g. a tap that fell through from the panel
    _bx, by = pixel_at_point((8, 4), layout)
    assert point_at_pixel(corner_x, by + off, layout) is None


def test_bigger_boards_get_smaller_cells():
    area = (1080, 1880, 2.75)
    assert compute_layout(9, *area).cell > compute_layout(19, *area).cell


def test_desktop_window_still_produces_a_sane_layout():
    layout = compute_layout(19, 760, 700, 1.0)
    assert layout.cell > 10
    assert point_at_pixel(*pixel_at_point((9, 9), layout), layout) == (9, 9)
