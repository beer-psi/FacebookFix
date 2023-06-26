import json
import re
from typing import Any

from selectolax.parser import HTMLParser
from yarl import URL

from utils import shorten_description

IMAGE_EXTENSION_REGEX = re.compile(r"\.(?:jpg|jpeg|png)$")


def extract_meta(
    soup: HTMLParser, extraction_failed: bool
) -> dict[str, Any] | str | None:
    ctx = {}

    if (
        (tag := soup.css_first("meta[property='og:description'], meta[name='twitter:description'], meta[name='description']")) is not None
        and (content := tag.attributes.get("content")) is not None
    ):
        ctx["description"] = shorten_description(content, 347)

    if (tag := soup.css_first("meta[name='twitter:player']")) is not None:
        player_url = URL(str(tag.attributes["content"]))
        video_url = player_url.query.get("href")

        if video_url is not None and not extraction_failed:
            return URL(video_url).path
        else:
            ctx["player"] = str(player_url)
            ctx["width"] = player_url.query.get("width", "0")
            ctx["height"] = player_url.query.get("height", "0")

            if "description" in ctx:
                ctx["description"] = shorten_description(ctx["description"])

    if (tag := soup.css_first("meta[property='og:title'], meta[name='twitter:title']")) is not None:
        ctx["title"] = str(tag.attributes["content"])
    if (
        (tag := soup.css_first("meta[property='og:image'], meta[name='twitter:image']")) is not None
        and (image := str(tag.attributes.get("content"))) is not None
        and IMAGE_EXTENSION_REGEX.search(image) is not None
    ):
        ctx["image"] = image
        ctx["card"] = "summary_large_image"
        ctx["ttype"] = "photo"

    if (tag := soup.css_first("script[type='application/ld+json']")) is not None and (
        script := tag.text()
    ) is not None:
        data = json.loads(script)
        ctx["description"] = shorten_description(data["articleBody"], 347)
        ctx["title"] = data["author"]["name"]

        if (image := data.get("image")) is not None:
            ctx["image"] = image["contentUrl"]
            ctx["card"] = "summary_large_image"
            ctx["ttype"] = "photo"

    if (
        ctx.get("title") is None
        and ctx.get("description") is None
        and ctx.get("image") is None
        and ctx.get("player") is None
    ):
        return None

    return ctx
