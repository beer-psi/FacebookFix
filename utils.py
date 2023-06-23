def hd_width_height(width: int, height: int) -> tuple[int, int]:
    if width > 720:
        height = int(height * (720 / width))
        width = 720

    return width, height
