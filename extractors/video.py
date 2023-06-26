import json
import re
from typing import Any

from exceptions import ExtractorError
from utils import hd_width_height

REEL_DATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,({\"define\":\[\[\"VideoPlayerShakaPerformanceLoggerConfig\".+?)\);"
)
WATCH_METADATA_DATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,(.+?\"CometFeedStoryDefaultMessageRenderingStrategy\".+?)\);"
)


async def get_video_data(resp_text: str):
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


async def get_watch_metadata(resp_text: str) -> dict[str, Any]:
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


async def extract_video(post_url: str, resp_text: str):
    media = await get_watch_metadata(resp_text)
    title = media["owner"]["name"]
    description = media["creation_story"]["comet_sections"]["message"]["story"][
        "message"
    ]["text"]
    if len(description) > 100:
        description = description[:100] + "..."

    video_data = await get_video_data(resp_text)
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


async def extract_reel(post_url: str, resp_text: str) -> dict[str, Any]:
    result = await get_video_data(resp_text)
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
        if len(ctx["description"]) > 100:
            ctx["description"] = ctx["description"][:100] + "..."

    return ctx
