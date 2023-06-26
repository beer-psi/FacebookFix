import re

HR_REGEX = re.compile(r"^[-_—-]{3,}$", re.MULTILINE)

def hd_width_height(width: int, height: int) -> tuple[int, int]:
    if width > 720:
        height = int(height * (720 / width))
        width = 720

    return width, height


def shorten_description(description: str) -> str:
    description = str(HR_REGEX.split(description)[0])
    if len(description) > 100:
        description = description.split("\n")[0]
    if len(description) > 100:
        description = description[:100] + "..."
    return description.strip()
