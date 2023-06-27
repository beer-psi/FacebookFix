import re

from selectolax.parser import Node

HR_REGEX = re.compile(r"^[-_—-]{3,}$", re.MULTILINE)

def hd_width_height(width: int, height: int) -> tuple[int, int]:
    if width > 720:
        height = int(height * (720 / width))
        width = 720

    return width, height


def shorten_description(description: str, limit: int = 100) -> str:
    description = str(HR_REGEX.split(description)[0])
    if len(description) > limit:
        splits = description.split("\n")
        description = splits[0]
        for split in splits[1:]:
            if len(description) + len(split) > limit:
                description = description.strip()
                description += "..."
                break
            description += "\n" + split
    if len(description) > limit:
        description = description[:limit] + "..."
    return description.strip()


def text_with_newlines(node: Node) -> str:
    for br in node.css("br"):
        br.insert_after("\\n")
    for p in node.css("p"):
        p.insert_after("\\n")
    return node.text().replace("\\n", "\n").replace("\n ", "\n").strip()
