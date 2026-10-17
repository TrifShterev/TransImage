def fit_image(
    image_w: int,
    image_h: int,
    viewport_w: int,
    viewport_h: int,
) -> tuple[int, int, int, int]:
    if image_w <= 0 or image_h <= 0 or viewport_w <= 0 or viewport_h <= 0:
        return (0, 0, 0, 0)
    scale = min(viewport_w / image_w, viewport_h / image_h)
    display_w = min(viewport_w, max(1, round(image_w * scale)))
    display_h = min(viewport_h, max(1, round(image_h * scale)))
    offset_x = (viewport_w - display_w) // 2
    offset_y = (viewport_h - display_h) // 2
    return (display_w, display_h, offset_x, offset_y)
