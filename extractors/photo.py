import json
import re
from typing import Any

from exceptions import ExtractorError

from utils import shorten_description

PHOTO_METADATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,(.+?\"__typename\":\"CometFeedStoryActorPhotoStrategy\".+?)\);"
)
PHOTO_DATA_REGEX = re.compile(
    r"\(ScheduledApplyEach,(.+?(?<!\"preloaderID\":)\"adp_CometPhotoRootContentQueryRelayPreloader_[0-9a-f]{23}\".+?)\);"
)


async def extract_photo(post_url: str, resp_text: str) -> dict[str, Any]:
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
        ctx["description"] = shorten_description(data["message"]["text"], 347)

    return ctx
