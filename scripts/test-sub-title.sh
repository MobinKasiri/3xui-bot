#!/usr/bin/env bash
# Verify Profile-Title on a subscription URL (local sub-proxy or public CDN).
set -euo pipefail

URL="${1:?Usage: $0 <subscription-url>}"
echo "GET $URL"
curl -sS -D - -o /dev/null "$URL" | grep -iE '^(HTTP/|profile-title|subscription-userinfo|content-disposition)'
