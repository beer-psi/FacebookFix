import re
from typing import TYPE_CHECKING

from selectolax.parser import Node
from yarl import URL

from exceptions import FetchException

if TYPE_CHECKING:
    from aiohttp import ClientSession

HR_REGEX = re.compile(r"^[-_—-]{3,}$", re.MULTILINE)

def hd_width_height(width: int, height: int) -> tuple[int, int]:
    if width > 720:
        height = int(height * (720 / width))
        width = 720

    return width, height


def shorten_description(description: str, limit: int = 100) -> str:
    description = str(HR_REGEX.split(description)[0]).strip()
    if len(description) > limit:
        splits = description.split("\n")
        description = splits[0]
        for split in splits[1:]:
            if len(description) + len(split) > limit:
                description = description.strip().rstrip(".")
                description += "..."
                break
            description += "\n" + split
    if len(description) > limit:
        description = description[:limit].rstrip(".") + "..."
    return description.strip()


def text_with_newlines(node: Node) -> str:
    for br in node.css("br"):
        br.insert_after("\\n")
    for p in node.css("p"):
        p.insert_after("\\n")
    return node.text().replace("\\n", "\n").replace("\n ", "\n").strip()


async def fetch_text(session: "ClientSession", url: str | URL, *, worker_proxy: str | None = None) -> str:
    async with session.get(url) as resp:
        if not resp.ok:
            raise FetchException
        if not "/login/" in resp.url.path:
            return await resp.text()
        else:
            # We're being blocked by Facebook
            if worker_proxy is None:
                raise FetchException

            proxy = URL(worker_proxy).update_query({"url": str(url)})
            async with session.get(proxy) as resp:
                if not resp.ok:
                    raise FetchException
                return await resp.text()
