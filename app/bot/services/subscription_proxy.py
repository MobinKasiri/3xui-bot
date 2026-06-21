"""Fetch panel subscription body and inject per-user Profile-Title."""
from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import aiohttp
from aiohttp import web

from app.bot.utils.sub_profile import profile_title_from_userinfo, profile_title_header_value

logger = logging.getLogger(__name__)

_PASS_HEADERS = frozenset({
    "subscription-userinfo",
    "profile-update-interval",
    "support-url",
    "profile-web-page-url",
    "announce",
    "routing-enable",
    "routing",
    "content-type",
    "content-disposition",
})

def _split_content_type(raw: str) -> tuple[str, str | None]:
    """aiohttp wants mime and charset as separate args."""
    parts = [p.strip() for p in (raw or "text/plain").split(";")]
    mime = parts[0] or "text/plain"
    charset: str | None = None
    for part in parts[1:]:
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip('"\'')
    return mime, charset


def _upstream_fetch_headers(client_headers: dict[str, str] | None) -> dict[str, str]:
    """3X-UI returns an HTML info page when Accept includes text/html — VPN apps need raw sub."""
    headers: dict[str, str] = {"Accept": "*/*"}
    if client_headers:
        ua = client_headers.get("User-Agent", "").strip()
        if ua:
            headers["User-Agent"] = ua
    return headers


def _looks_like_html(body: bytes) -> bool:
    start = body.lstrip()[:128].lower()
    return start.startswith(b"<!doctype") or start.startswith(b"<html")


def _strip_html_query(url: str) -> str:
    """Remove ?html=1 so panel returns base64 subscription, not the info page."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() != "html"]
    query = urlencode(kept)
    return urlunparse(parsed._replace(query=query))


async def _fetch_upstream(
    http: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
) -> tuple[bytes, int, dict[str, str], str]:
    async with http.get(url, allow_redirects=True, headers=headers) as upstream:
        body = await upstream.read()
        return (
            body,
            upstream.status,
            _forward_headers(upstream.headers),
            upstream.headers.get("Subscription-Userinfo", ""),
        )


async def proxy_subscription_response(
    upstream_url: str,
    *,
    service_name: str,
    client_headers: dict[str, str] | None = None,
) -> web.Response:
    fetch_url = _strip_html_query(upstream_url)
    fetch_headers = _upstream_fetch_headers(client_headers)

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            body, status, passthrough, userinfo = await _fetch_upstream(
                http, fetch_url, fetch_headers
            )
    except aiohttp.ClientError as exc:
        logger.warning("Subscription upstream failed %s: %s", fetch_url, exc)
        return web.Response(status=502, text="subscription upstream unavailable")

    if status >= 400:
        content_type_raw = passthrough.get("content-type", passthrough.get("Content-Type", "text/plain"))
        mime, charset = _split_content_type(content_type_raw)
        return web.Response(status=status, body=body, headers=passthrough, content_type=mime, charset=charset)

    # HTML info page — return unchanged (browser); do not inject or alter body.
    if _looks_like_html(body):
        content_type_raw = passthrough.get("content-type", passthrough.get("Content-Type", "text/html"))
        mime, charset = _split_content_type(content_type_raw)
        return web.Response(status=200, body=body, headers=passthrough, content_type=mime, charset=charset)

    title = profile_title_from_userinfo(service_name, userinfo)
    title_value = profile_title_header_value(title)
    headers = dict(passthrough)
    headers["Profile-Title"] = title_value
    headers["profile-title"] = title_value
    if userinfo:
        headers["Subscription-Userinfo"] = userinfo
        headers["subscription-userinfo"] = userinfo

    content_type_raw = headers.pop("content-type", headers.pop("Content-Type", "text/plain; charset=utf-8"))
    mime, charset = _split_content_type(content_type_raw)
    return web.Response(status=200, body=body, headers=headers, content_type=mime, charset=charset)


def _forward_headers(upstream_headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in upstream_headers.items():
        if key.lower() in _PASS_HEADERS:
            out[key] = val
    return out
