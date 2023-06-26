from typing import Any

from selectolax.parser import HTMLParser
from yarl import URL


def extract_embed(
    soup: HTMLParser, extraction_failed: bool
) -> dict[str, Any] | str | None:
    ctx = {}

    if (
        (tag := soup.css_first("a[href^='https://www.facebook.com/photo.php']"))
        is not None
        and (href := tag.attributes["href"]) is not None
        and not extraction_failed
    ):
        return URL(href).path

    if (tag := soup.css_first("div[data-testid='post_message']")) is not None:
        ctx["description"] = tag.text()
    if (tag := soup.css_first("span._2_79._50f7")) is not None:
        ctx["title"] = tag.text()
    if (tag := soup.css_first("img._1p6f._1p6g")) is not None:
        ctx["image"] = tag.attributes["src"]
        ctx["card"] = "summary_large_image"
        ctx["ttype"] = "photo"

    if (
        ctx.get("title") is None
        and ctx.get("description") is None
        and ctx.get("image") is None
    ):
        return None

    return ctx
