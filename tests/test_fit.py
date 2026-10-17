import pytest

from transimage.fit import fit_image


def test_wide_image_scales_to_viewport_width() -> None:
    assert fit_image(100, 50, 200, 200) == (200, 100, 0, 50)


def test_tall_image_scales_to_viewport_height() -> None:
    assert fit_image(50, 100, 200, 200) == (100, 200, 50, 0)


def test_large_wide_image_scales_down() -> None:
    assert fit_image(400, 200, 200, 200) == (200, 100, 0, 50)


def test_square_image_fills_square_viewport() -> None:
    assert fit_image(100, 100, 200, 200) == (200, 200, 0, 0)
    assert fit_image(80, 80, 80, 80) == (80, 80, 0, 0)


def test_non_positive_viewport_returns_zeros() -> None:
    assert fit_image(100, 50, 0, 200) == (0, 0, 0, 0)
    assert fit_image(100, 50, 200, -1) == (0, 0, 0, 0)


def test_does_not_stretch_axes_independently() -> None:
    display_w, display_h, offset_x, offset_y = fit_image(100, 50, 300, 100)
    assert (display_w, display_h, offset_x, offset_y) == (200, 100, 50, 0)


@pytest.mark.parametrize(
    ("image_w", "image_h", "viewport_w", "viewport_h"),
    [
        (100, 50, 200, 200),
        (50, 100, 200, 200),
        (400, 200, 200, 200),
        (100, 100, 200, 200),
        (17, 13, 640, 480),
        (320, 240, 800, 600),
        (3, 1, 10, 10),
    ],
)
def test_displayed_ratio_matches_source_within_one_pixel(
    image_w: int,
    image_h: int,
    viewport_w: int,
    viewport_h: int,
) -> None:
    display_w, display_h, offset_x, offset_y = fit_image(
        image_w, image_h, viewport_w, viewport_h
    )
    scale = min(viewport_w / image_w, viewport_h / image_h)
    assert abs(display_w - image_w * scale) <= 1
    assert abs(display_h - image_h * scale) <= 1
    assert 1 <= display_w <= viewport_w
    assert 1 <= display_h <= viewport_h
    assert offset_x == (viewport_w - display_w) // 2
    assert offset_y == (viewport_h - display_h) // 2
