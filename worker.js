addEventListener("fetch", event => {
    event.respondWith(stream(event.request))
});

async function stream(request) {
    const {
        searchParams
    } = new URL(request.url)

    const url = searchParams.get('url');
    const referer = searchParams.get('referer') ?? "https://www.facebook.com/";

    const resp = await fetch(url, {
        headers: {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": referer,
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
        },
    });

    return new Response(resp.body, {
        headers: resp.headers
    });
}
