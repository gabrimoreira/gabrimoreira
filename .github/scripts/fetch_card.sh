#!/usr/bin/env bash
# Usage: fetch_card.sh URL DEST EXPECTED_TEXT [SED_SCRIPT]
#
# Downloads an SVG card and replaces DEST only if the result is valid. These services
# can answer an error card with status 200, so the status code alone proves nothing.
# On failure DEST keeps the last good version and the script exits non-zero.
set -euo pipefail

url=$1
dest=$2
expected=$3
rewrite=${4:-}

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

curl --fail --silent --show-error --location --retry 3 --retry-all-errors --max-time 60 \
  --output "$tmp" "$url"

if ! grep --quiet --fixed-strings "$expected" "$tmp"; then
  echo "::error::$dest: response does not contain '$expected'"
  exit 1
fi

if [ -n "$rewrite" ]; then
  sed -i -E "$rewrite" "$tmp"
fi

python3 -c 'import sys, xml.dom.minidom as dom; dom.parse(sys.argv[1])' "$tmp"
mv "$tmp" "$dest"
