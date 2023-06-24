import json
import re
from typing import Any

import aiohttp
import sanic
from sanic import BadRequest, HTTPResponse, Request, Sanic, redirect
from yarl import URL

from utils import hd_width_height

UA_REGEX = re.compile(
    r"bot|facebook|embed|got|firefox\/92|firefox\/38|curl|wget|go-http|yahoo|generator|whatsapp|preview|link|proxy|vkshare|images|analyzer|index|crawl|spider|python|cfnetwork|node|iframely"
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
    "authority": "www.facebook.com",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "sec-fetch-mode": "navigate",
    "upgrade-insecure-requests": "1",
    "referer": "https://www.facebook.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    "viewport-width": "1280",
}
app = Sanic(__name__)


@app.listener("before_server_start")
def init(app, loop):
    app.ctx.session = aiohttp.ClientSession(loop=loop, headers=headers)


@app.listener("after_server_stop")
def finish(app, loop):
    loop.run_until_complete(app.ctx.session.close())
    loop.close()


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


@app.on_request
async def check_ua(request: "Request"):
    url = URL(request.url)
    if not UA_REGEX.search(request.headers.get("User-Agent", ""), re.IGNORECASE):
        url = url.with_host("www.facebook.com")
        return redirect(str(url))


async def _get_video_data(resp_text: str):
    data = REEL_DATA_REGEX.search(resp_text)
    if not data:
        raise Exception("Failed to get video data")

    data = json.loads(data.group(1))

    stream_cache = next(
        (x for x in data["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        raise Exception("Failed to get video data")

    return stream_cache[3][1]["__bbox"]["result"]


@app.get("/reel/<id>")
@app.ext.template("base.html")
async def reel(request: "Request", id: str):
    post_url = f"https://facebook.com/reel/{id}"

    async with app.ctx.session.get(post_url) as resp:
        if not resp.ok:
            raise Exception("Failed to get video data")
        resp_text = await resp.text()

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
        raise Exception("Failed to get metadata")

    metadata = json.loads(metadata.group(1))
    stream_cache = next(
        (x for x in metadata["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        raise Exception("Failed to get metadata")
    return stream_cache[3][1]["__bbox"]["result"]["data"]["attachments"][0]["media"]


async def _common_watch_handler(post_url: str):
    async with app.ctx.session.get(post_url) as resp:
        if not resp.ok:
            return redirect(post_url)
        resp_text = await resp.text()

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
        "id": id,
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
        return redirect("https://facebook.com/watch")

    post_url = f"https://facebook.com/watch/?v={id}"

    return await _common_watch_handler(post_url)


@app.get("<username>/videos/<id>")
@app.ext.template("base.html")
async def videos(request: "Request", username: str, id: str):
    post_url = f"https://facebook.com/{username}/videos/{id}"
    
    return await _common_watch_handler(post_url)


async def _common_photo_handler(post_url: str):
    async with app.ctx.session.get(post_url) as resp:
        if not resp.ok:
            return redirect(post_url)
        resp_text = await resp.text()

    photo_data = PHOTO_DATA_REGEX.search(resp_text)
    if not photo_data:
        return redirect(post_url)
    
    photo_data = json.loads(photo_data.group(1))
    stream_cache = next(
        (x for x in photo_data["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        return redirect(post_url)
    
    curr_media = stream_cache[3][1]["__bbox"]["result"]["data"]["currMedia"]

    photo_metadata = PHOTO_METADATA_REGEX.search(resp_text)
    if not photo_metadata:
        return redirect(post_url)
    
    photo_metadata = json.loads(photo_metadata.group(1))
    stream_cache = next(
        (x for x in photo_metadata["require"] if x[0] == "RelayPrefetchedStreamCache"), None
    )
    if not stream_cache:
        return redirect(post_url)
    data = stream_cache[3][1]["__bbox"]["result"]["data"]

    return {
        "card": "summary_large_image",
        "title": data["owner"]["name"],
        "url": post_url,
        "description": data["message"]["text"],
        "image": curr_media["image"]["uri"],
        "ttype": "photo",
    }


@app.get("<username>/photos/<set>/<fbid>")
@app.ext.template("base.html")
async def photos(request: "Request", username: str, set: str, fbid: str):
    post_url = f"https://facebook.com/{username}/photos/{set}/{fbid}"

    return await _common_photo_handler(post_url)


@app.get("photo")
@app.ext.template("base.html")
async def photo(request: "Request"):
    fbid = request.args.get("fbid", "")

    if not fbid:
        url = URL(request.url)
        url = url.with_host("www.facebook.com")
        return redirect(str(url))
    
    post_url = f"https://facebook.com/photo/?fbid={fbid}"

    return await _common_photo_handler(post_url)

