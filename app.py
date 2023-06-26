import json
import re
from typing import Any

import aiohttp
import sanic
from bs4 import BeautifulSoup
from dotenv import dotenv_values
from sanic import HTTPResponse, NotFound, Request, Sanic, SanicException, redirect
from yarl import URL

from utils import hd_width_height


class ExtractorError(SanicException):
    pass


app = Sanic(__name__)
app.update_config(
    {
        "RESPONSE_TIMEOUT": 120,
    }
)


UA_REGEX = re.compile(
    r"bot|facebook|embed|got|firefox\/92|firefox\/38|curl|wget|go-http|yahoo|generator|whatsapp|preview|link|proxy|vkshare|images|analyzer|index|crawl|spider|python|cfnetwork|node|iframely",
    re.IGNORECASE,
)
REEL_DATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,({\"define\":\[\[\"VideoPlayerShakaPerformanceLoggerConfig\".+?)\);"
)
WATCH_METADATA_DATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,(.+?\"CometFeedStoryDefaultMessageRenderingStrategy\".+?)\);"
)
PHOTO_METADATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,(.+?\"__typename\":\"CometFeedStoryActorPhotoStrategy\".+?)\);"
)
PHOTO_DATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,(.+?(?<!\"preloaderID\":)\"adp_CometPhotoRootContentQueryRelayPreloader_[0-9a-f]{23}\".+?)\);"
)
headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-prefers-color-scheme": "dark",
    "sec-ch-ua": '"Microsoft Edge";v="111", "Not(A:Brand";v="8", "Chromium";v="111"',
    "sec-ch-ua-full-version-list": '"Microsoft Edge";v="111.0.1661.62", "Not(A:Brand";v="8.0.0.0", "Chromium";v="111.0.5563.149"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"15.0.0"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.62",
}


@app.listener("before_server_start")
def init(app, loop):
    app.ctx.session = aiohttp.ClientSession(loop=loop, headers=headers)
    app.ctx.cfg = dotenv_values()


@app.listener("after_server_stop")
def finish(app, loop):
    loop.run_until_complete(app.ctx.session.close())
    loop.close()


@app.on_request
async def check_ua(request: "Request"):
    url = URL(request.url)
    if url.path != "/oembed.json" and not UA_REGEX.search(
        request.headers.get("User-Agent", "")
    ):
        url = url.with_host("www.facebook.com").with_scheme("https").with_port(None)
        return redirect(str(url))


@app.on_request
async def fetch_response_text(request: "Request"):
    if request.url != "/oembed.json":
        post_url = str(
            URL(request.url)
            .with_host("www.facebook.com")
            .with_scheme("https")
            .with_port(None)
        )
        request.ctx.post_url = post_url

        async with app.ctx.session.get(post_url) as resp:
            if not resp.ok:
                return redirect(post_url)
            if not "/login/" in resp.url.path:
                request.ctx.resp_text = await resp.text()
            else:
                # We're being blocked by Facebook
                if (proxy := app.ctx.cfg.get("WORKER_PROXY")) is None:
                    return redirect(post_url)

                proxy = URL(proxy).update_query({"url": post_url})
                async with app.ctx.session.get(proxy) as resp:
                    if not resp.ok:
                        return redirect(post_url)
                    request.ctx.resp_text = await resp.text()


@app.exception(NotFound, ExtractorError)
@app.ext.template("base.html")
async def handle_404(request: Request, exception: SanicException):
    """Blanket handler for unimplemented paths, or paths with failed extractors"""

    post_url = request.ctx.post_url
    resp_text = request.ctx.resp_text

    soup = BeautifulSoup(resp_text, "lxml")

    ctx = {
        "url": post_url,
    }

    if (tag := soup.select_one("meta[name='twitter:player']")) is not None:
        player_url = URL(str(tag["content"]))
        video_url = player_url.query.get("href")

        if video_url is not None and not isinstance(exception, ExtractorError):
            return redirect(URL(video_url).path)
        else:
            ctx["player"] = str(player_url)
            ctx["width"] = player_url.query.get("width", "0")
            ctx["height"] = player_url.query.get("height", "0")

    if (tag := soup.select_one("meta[property='og:title']")) is not None:
        ctx["title"] = str(tag["content"])
    if (tag := soup.select_one("meta[property='og:description']")) is not None:
        ctx["description"] = str(tag["content"])
    if (tag := soup.select_one("meta[property='og:image']")) is not None:
        ctx["image"] = str(tag["content"])
        ctx["card"] = "summary_large_image"
        ctx["ttype"] = "photo"

    if (
        tag := soup.select_one("script[type='application/ld+json']")
    ) is not None and tag.string is not None:
        data = json.loads(tag.string)
        ctx["description"] = data["articleBody"]
        ctx["title"] = data["author"]["name"]

        if (image := data.get("image")) is not None:
            ctx["image"] = image["contentUrl"]
            ctx["card"] = "summary_large_image"
            ctx["ttype"] = "photo"

    if (
        ctx.get("title") is None
        and ctx.get("description") is None
        and ctx.get("image") is None
    ):
        return redirect(post_url)

    return ctx


@app.get("oembed.json")
async def oembed(request: "Request") -> "HTTPResponse":
    title = request.args.get("title", "")
    user = request.args.get("user", "")
    link = request.args.get("link", "")
    ttype = request.args.get("type", "link")
    return sanic.json(
        {
            "author_name": user,
            "author_url": link,
            "provider_name": "FacebookFix",
            "provider_url": "https://github.com/beerpiss/FacebookFix",
            "title": title,
            "type": ttype,
            "version": "1.0",
        }
    )


async def _get_video_data(resp_text: str):
    data = REEL_DATA_REGEX.search(resp_text)
    if not data:
        raise ExtractorError("Failed to get video data")

    data = json.loads(data.group(1))

    stream_cache = next(
        (x for x in data["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        raise ExtractorError("Failed to get video data")

    return stream_cache[3][1]["__bbox"]["result"]


@app.get("/reel/<id>")
@app.ext.template("base.html")
async def reel(request: "Request", id: str):
    post_url = request.ctx.post_url
    resp_text = request.ctx.resp_text

    result = await _get_video_data(resp_text)
    creation_story = result["data"]["video"]["creation_story"]
    short_form_video_context = creation_story["short_form_video_context"]

    url = short_form_video_context["playback_video"]["playable_url_quality_hd"]
    if url is None:
        url = short_form_video_context["playback_video"]["playable_url"]
    width = short_form_video_context["playback_video"]["width"]
    height = short_form_video_context["playback_video"]["height"]

    width, height = hd_width_height(width, height)

    ctx = {
        "id": id,
        "card": "player",
        "title": short_form_video_context["video_owner"]["name"],
        "url": post_url,
        "video": url,
        "width": width,
        "height": height,
        "ttype": "video",
    }

    if (message := creation_story.get("message")) is not None:
        ctx["description"] = message["text"]

    return ctx


async def _get_watch_metadata(resp_text: str) -> dict[str, Any]:
    metadata = WATCH_METADATA_DATA_REGEX.search(resp_text)
    if not metadata:
        raise ExtractorError("Failed to get metadata")

    metadata = json.loads(metadata.group(1))
    stream_cache = next(
        (x for x in metadata["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        raise ExtractorError("Failed to get metadata")
    return stream_cache[3][1]["__bbox"]["result"]["data"]["attachments"][0]["media"]


async def _common_watch_handler(request: "Request"):
    post_url = request.ctx.post_url
    resp_text = request.ctx.resp_text

    media = await _get_watch_metadata(resp_text)
    title = media["owner"]["name"]
    description = media["creation_story"]["comet_sections"]["message"]["story"][
        "message"
    ]["text"]

    video_data = await _get_video_data(resp_text)
    url = video_data["data"]["video"]["story"]["attachments"][0]["media"][
        "playable_url_quality_hd"
    ]
    if url is None:
        url = video_data["data"]["video"]["story"]["attachments"][0]["media"][
            "playable_url"
        ]
    width = video_data["data"]["video"]["story"]["attachments"][0]["media"]["width"]
    height = video_data["data"]["video"]["story"]["attachments"][0]["media"]["height"]

    width, height = hd_width_height(width, height)

    return {
        "card": "player",
        "title": title,
        "url": post_url,
        "description": description,
        "video": url,
        "width": width,
        "height": height,
        "ttype": "video",
    }


@app.get("/watch")
@app.ext.template("base.html")
async def watch(request: "Request"):
    id = request.args.get("v", "")
    if not id:
        raise NotFound
    return await _common_watch_handler(request)


@app.get("<username>/videos/<id>")
@app.ext.template("base.html")
async def videos(request: "Request", username: str, id: str):
    request.ctx.post_url = f"https://www.facebook.com/{username}/videos/{id}"
    return await _common_watch_handler(request)


@app.get("<username>/videos/<slug>/<id>")
@app.ext.template("base.html")
async def videos_with_slug(request: "Request", username: str, slug: str, id: str):
    request.ctx.post_url = f"https://www.facebook.com/{username}/videos/{slug}/{id}"
    return await _common_watch_handler(request)


async def _common_photo_handler(request: "Request"):
    post_url = request.ctx.post_url
    resp_text = request.ctx.resp_text

    photo_data = PHOTO_DATA_REGEX.search(resp_text)
    if not photo_data:
        raise ExtractorError

    photo_data = json.loads(photo_data.group(1))
    stream_cache = next(
        (x for x in photo_data["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        raise ExtractorError

    curr_media = stream_cache[3][1]["__bbox"]["result"]["data"]["currMedia"]

    photo_metadata = PHOTO_METADATA_REGEX.search(resp_text)
    if not photo_metadata:
        raise ExtractorError

    photo_metadata = json.loads(photo_metadata.group(1))
    stream_cache = next(
        (x for x in photo_metadata["require"] if x[0] == "RelayPrefetchedStreamCache"),
        None,
    )
    if not stream_cache:
        raise ExtractorError
    data = stream_cache[3][1]["__bbox"]["result"]["data"]

    ctx = {
        "card": "summary_large_image",
        "title": data["owner"]["name"],
        "url": post_url,
        "image": curr_media["image"]["uri"],
        "ttype": "photo",
    }

    if data["message"] is not None:
        ctx["description"] = data["message"]["text"]

    return ctx


@app.get("<username>/photos/<set>/<fbid>")
@app.ext.template("base.html")
async def photos(request: "Request", username: str, set: str, fbid: str):
    request.ctx.post_url = f"https://www.facebook.com/{username}/photos/{set}/{fbid}"
    return await _common_photo_handler(request)


@app.get("photo")
@app.get("photo.php", name="photo_php")
@app.ext.template("base.html")
async def photo(request: "Request"):
    fbid = request.args.get("fbid", "")
    if not fbid:
        raise NotFound

    return await _common_photo_handler(request)
