"""Fetch panel subscription body and inject per-user Profile-Title."""
from __future__ import annotations

import base64
import logging
import re

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

_SAFE_FILENAME_RE = re.compile(r'[^\w\s\-—\.]+', re.UNICODE)


async def proxy_subscription_response(
    upstream_url: str,
    *,
    service_name: str,
    client_headers: dict[str, str] | None = None,
) -> web.Response:
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(
                upstream_url,
                allow_redirects=True,
                headers=client_headers or {},
            ) as upstream:
                body = await upstream.read()
                status = upstream.status
                passthrough = _forward_headers(upstream.headers)
                userinfo = upstream.headers.get("Subscription-Userinfo", "")
    except aiohttp.ClientError as exc:
        logger.warning("Subscription upstream failed %s: %s", upstream_url, exc)
        return web.Response(status=502, text="subscription upstream unavailable")

    if status >= 400:
        return web.Response(status=status, body=body, headers=passthrough)

    title = profile_title_from_userinfo(service_name, userinfo)
    title_value = profile_title_header_value(title)
    body = _inject_body_profile_title(body, title_value)
    headers = dict(passthrough)
    headers["Profile-Title"] = title_value
    headers["profile-title"] = title_value
    if userinfo:
        headers["Subscription-Userinfo"] = userinfo
        headers["subscription-userinfo"] = userinfo
    safe_name = _SAFE_FILENAME_RE.sub("", title).strip() or "NC VPN"
    headers["Content-Disposition"] = f'attachment; filename="{safe_name}.txt"'

    content_type = headers.pop("content-type", headers.pop("Content-Type", "text/plain; charset=utf-8"))
    return web.Response(status=200, body=body, headers=headers, content_type=content_type)


def _inject_body_profile_title(body: bytes, title_value: str) -> bytes:
    """v2Box / v2RayTun also read ``#profile-title`` inside decoded subscription body."""
    if not body or b"#profile-title" in body.lower():
        return body

    header_line = f"#profile-title: {title_value}\n".encode()

    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return body

    try:
        padding = "=" * (-len(text) % 4)
        decoded = base64.b64decode(text + padding, validate=False)
    except Exception:
        decoded = None

    if decoded and (b"://" in decoded or decoded.startswith(b"#")):
        if b"#profile-title" in decoded.lower():
            return body
        return base64.b64encode(header_line + decoded)

    if b"://" in body:
        return header_line + body

    return body


def _forward_headers(upstream_headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in upstream_headers.items():
        if key.lower() in _PASS_HEADERS:
            out[key] = val
    return out
