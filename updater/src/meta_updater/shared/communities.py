import html
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .feeds import fetch
from .images import favicon, image_url, meta_values
from .provenance import track_provenance

HEADERS = {
    "User-Agent": "cpp.social metadata updater (+https://cpp.social/contributing/)",
    "Accept-Language": "en-US,en;q=0.8",
}


def discord(key: str, timeout: float) -> dict[str, Any]:
    url = f"https://discord.com/api/v10/invites/{key}?with_counts=true"
    invite = json.loads(fetch(url, timeout, HEADERS))
    guild = invite["guild"]
    guild_id = guild["id"]
    icon = guild.get("icon")
    banner = guild.get("banner")
    return {
        "description": (guild.get("description") or "").strip(),
        "avatar_url": f"https://cdn.discordapp.com/icons/{guild_id}/{icon}.png?size=512"
        if icon
        else "",
        "banner_url": f"https://cdn.discordapp.com/banners/{guild_id}/{banner}.jpg?size=1024"
        if banner
        else "",
        "member_count": invite.get("approximate_member_count"),
        "source_url": url,
    }


def _reddit_image(page: str, subreddit_id: str, name: str) -> str:
    pattern = (
        rf"https?://styles\.redditmedia\.com/{re.escape(subreddit_id)}"
        rf"/styles/{name}[^\"' <>]+"
    )
    match = re.search(pattern, page, re.IGNORECASE)
    if not match:
        return ""
    value = html.unescape(match.group(0))
    return re.split(r"[\"' <>]", value, maxsplit=1)[0].rstrip(");")


def reddit(key: str, timeout: float) -> dict[str, Any]:
    url = f"https://www.reddit.com/r/{key}/"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def request(target: str) -> urllib.request.Request:
        return urllib.request.Request(target, headers=HEADERS)

    page = opener.open(request(url), timeout=timeout).read().decode("utf-8", "replace")
    track_provenance(url)
    if 'name="js_challenge"' in page:
        challenge = re.search(r'\)\("([0-9a-f]+)"\)', page)
        token = re.search(r'name="token" value="([^"]+)"', page)
        if not challenge or not token:
            raise ValueError(f"could not solve Reddit verification for r/{key}")
        query = urllib.parse.urlencode(
            {
                "solution": challenge.group(1) * 2,
                "js_challenge": "1",
                "token": token.group(1),
                "jsc_orig_r": "",
            }
        )
        page = (
            opener.open(request(f"{url}?{query}"), timeout=timeout)
            .read()
            .decode("utf-8", "replace")
        )
    header = re.search(r"<shreddit-subreddit-header\s+([^>]+)>", page)
    if not header:
        raise ValueError(f"missing Reddit community metadata for r/{key}")
    data = dict(re.findall(r"([\w-]+)=[\"']([^\"']*)[\"']", header.group(1)))
    subreddit_id = data.get("subreddit-id", "")
    avatar = (
        data.get("icon-url")
        or data.get("community-icon")
        or _reddit_image(page, subreddit_id, "communityIcon")
    )
    banner = (
        data.get("banner-background-image")
        or data.get("banner-img")
        or data.get("mobile-banner-image")
        or _reddit_image(page, subreddit_id, "bannerBackgroundImage")
        or ""
    )

    return {
        "description": html.unescape(data.get("description", "")).strip(),
        "avatar_url": html.unescape(avatar),
        "banner_url": html.unescape(banner),
        "member_count": None,
        "weekly_visitors": data.get("weekly-active-users"),
        "weekly_contributions": data.get("weekly-contributions"),
        "source_url": url,
    }


def web(url: str, timeout: float) -> dict[str, Any]:
    page = fetch(url, timeout, HEADERS).decode("utf-8", "replace")
    values = meta_values(page)
    return {
        "description": values.get(
            "og:description", values.get("description", "")
        ).strip(),
        "avatar_url": image_url(url, values.get("og:logo", "")) or favicon(page, url),
        "banner_url": image_url(url, values.get("og:image", "")),
        "member_count": None,
        "source_url": url,
    }


def stackoverflow(key: str, timeout: float) -> dict[str, Any]:
    url = f"https://api.stackexchange.com/2.3/tags/{key}/info?site=stackoverflow"
    items = json.loads(fetch(url, timeout, HEADERS)).get("items", [])
    if not items:
        raise ValueError("Stack Overflow returned no tag metadata")
    return {
        "description": items[0].get("excerpt", "").strip(),
        "avatar_url": "https://cdn.sstatic.net/Sites/stackoverflow/Img/apple-touch-icon.png",
        "banner_url": "",
        "member_count": None,
        "source_url": url,
    }


HANDLERS: dict[str, Callable[[str, float], dict[str, Any]]] = {
    "discord": discord,
    "reddit": reddit,
    "stackoverflow": stackoverflow,
    "web": web,
}


def metadata(source: str, key: str, timeout: float) -> dict[str, Any]:
    try:
        handler = HANDLERS[source]
    except KeyError as error:
        raise ValueError(f"unsupported community metadata source: {source}") from error
    return handler(key, timeout)
