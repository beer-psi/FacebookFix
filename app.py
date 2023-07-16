import re
from asyncio import AbstractEventLoop

import aiohttp
import sanic
from dotenv import dotenv_values
from sanic import HTTPResponse, NotFound, Request, Sanic, SanicException, redirect
from selectolax.parser import HTMLParser
from yarl import URL

from exceptions import ExtractorError, FetchException
from extractors import (
    extract_embed,
    extract_meta,
    extract_photo,
    extract_reel,
    extract_video,
)
from utils import fetch_text

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
    # "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.62",
    "user-agent": "facebookexternalhit/1.1",
}


@app.listener("before_server_start")
def init(app: Sanic, loop: AbstractEventLoop):
    app.ctx.session = aiohttp.ClientSession(loop=loop, headers=headers)
    app.ctx.cfg = dotenv_values()


@app.listener("after_server_stop")
def finish(app, loop):
    loop.run_until_complete(app.ctx.session.close())
    loop.close()


@app.on_request
async def check_ua(request: "Request"):
    url = URL(request.url)
    if url.path not in ["/oembed.json", "/rendercombined.jpg"] and not UA_REGEX.search(
        request.headers.get("User-Agent", "")
    ):
        url = url.with_host("www.facebook.com").with_scheme("https").with_port(None)
        return redirect(str(url))


@app.exception(NotFound, ExtractorError)
@app.ext.template("base.html")
async def handle_404(request: Request, exception: SanicException):
    """Blanket handler for unimplemented paths, or paths with failed extractors"""

    post_url = request.ctx.post_url
    resp_text = request.ctx.resp_text

    soup = HTMLParser(resp_text)

    ctx = {
        "url": post_url,
    }

    metadata_or_redirect_url = extract_meta(soup, isinstance(exception, ExtractorError))
    if isinstance(metadata_or_redirect_url, str):
        return redirect(metadata_or_redirect_url)
    elif metadata_or_redirect_url is not None:
        ctx.update(metadata_or_redirect_url)
        return ctx

    # Use their embed iframe as a last resort
    url = URL("https://www.facebook.com/plugins/post.php").update_query(
        {"href": post_url, "show_text": "true"}
    )
    async with app.ctx.session.get(url) as resp:
        if not resp.ok:
            return redirect(post_url)
        resp_text = await resp.text()

    soup = HTMLParser(resp_text)

    metadata_or_redirect_url = extract_embed(
        soup, isinstance(exception, ExtractorError)
    )
    if isinstance(metadata_or_redirect_url, str):
        return redirect(metadata_or_redirect_url)
    elif metadata_or_redirect_url is not None:
        ctx.update(metadata_or_redirect_url)
        return ctx

    return redirect(post_url)


@app.exception(FetchException)
async def handle_fetch_exception(request: "Request", exception: FetchException):
    return redirect(request.ctx.post_url)


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


@app.get("/reel/<id>")
@app.ext.template("base.html")
async def reel(request: "Request", id: str):
    request.ctx.post_url = f"https://www.facebook.com/reel/{id}"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_reel(request.ctx.post_url, request.ctx.resp_text)


@app.get("/watch")
@app.ext.template("base.html")
async def watch(request: "Request"):
    id = request.args.get("v", "")
    if not id:
        raise NotFound
    request.ctx.post_url = f"https://www.facebook.com/watch/?v={id}"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_video(request.ctx.post_url, request.ctx.resp_text)


@app.get("<username>/videos/<id>")
@app.ext.template("base.html")
async def videos(request: "Request", username: str, id: str):
    request.ctx.post_url = f"https://www.facebook.com/{username}/videos/{id}"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_video(request.ctx.post_url, request.ctx.resp_text)


@app.get("<username>/videos/<slug>/<id>")
@app.ext.template("base.html")
async def videos_with_slug(request: "Request", username: str, slug: str, id: str):
    request.ctx.post_url = f"https://www.facebook.com/{username}/videos/{slug}/{id}"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_video(request.ctx.post_url, request.ctx.resp_text)


@app.get("<username>/photos/<set>/<fbid>")
@app.ext.template("base.html")
async def photos(request: "Request", username: str, set: str, fbid: str):
    request.ctx.post_url = f"https://www.facebook.com/{username}/photos/{set}/{fbid}"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_photo(request.ctx.post_url, request.ctx.resp_text)


@app.get("photo")
@app.get("photo.php", name="photo_php")
@app.ext.template("base.html")
async def photo(request: "Request"):
    fbid = request.args.get("fbid", "")
    if not fbid:
        raise NotFound
    request.ctx.post_url = f"https://www.facebook.com/photo.php?fbid={fbid}"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_photo(request.ctx.post_url, request.ctx.resp_text)

# https://fb.watch/lPjwDfimA4/
@app.get(r"/<video:[0-9A-Za-z]{10}>/")
@app.ext.template("base.html")
async def watch_video(request: "Request", video: str):
    request.ctx.post_url = f"https://fb.watch/{video}/"
    request.ctx.resp_text = await fetch_text(app.ctx.session, request.ctx.post_url, worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
    return await extract_video(request.ctx.post_url, request.ctx.resp_text)


# @app.get("story.php")
# @app.ext.template("base.html")
# async def story(request: "Request"):
#     story_fbid = request.args.get("story_fbid", "")
#     fbid = request.args.get("id", "")
#     if not story_fbid or not fbid:
#         raise NotFound
#     request.ctx.post_url = f"https://www.facebook.com/story.php?story_fbid={story_fbid}&id={fbid}"
#     request.ctx.resp_text = await fetch_text(app.ctx.session, URL(request.ctx.post_url).with_host("m.facebook.com"), worker_proxy=app.ctx.cfg.get("WORKER_PROXY"))
#     return sanic.text(request.ctx.resp_text)
#     return await extract_story(request.ctx.post_url, request.ctx.resp_text)
