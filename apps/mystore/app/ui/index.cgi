#!/bin/bash

BASE_PATH="/var/apps/hello-fn/target/www"
URI_NO_QUERY="${REQUEST_URI%%\?*}"
REL_PATH="/"

case "$URI_NO_QUERY" in
  *index.cgi*)
    REL_PATH="${URI_NO_QUERY#*index.cgi}"
    ;;
esac

if [ -z "$REL_PATH" ] || [ "$REL_PATH" = "/" ]; then
  REL_PATH="/index.html"
fi

TARGET_FILE="${BASE_PATH}${REL_PATH}"

if echo "$TARGET_FILE" | grep -q '\.\.'; then
  echo "Status: 400 Bad Request"
  echo "Content-Type: text/plain; charset=utf-8"
  echo ""
  echo "Bad Request"
  exit 0
fi

if [ ! -f "$TARGET_FILE" ]; then
  echo "Status: 404 Not Found"
  echo "Content-Type: text/plain; charset=utf-8"
  echo ""
  echo "404 Not Found"
  exit 0
fi

case "${TARGET_FILE##*.}" in
  html|htm) mime="text/html; charset=utf-8" ;;
  css) mime="text/css; charset=utf-8" ;;
  js) mime="application/javascript; charset=utf-8" ;;
  json) mime="application/json; charset=utf-8" ;;
  png) mime="image/png" ;;
  jpg|jpeg) mime="image/jpeg" ;;
  gif) mime="image/gif" ;;
  svg) mime="image/svg+xml" ;;
  ico) mime="image/x-icon" ;;
  woff|woff2) mime="font/woff2" ;;
  *) mime="application/octet-stream" ;;
esac

echo "Content-Type: $mime"
echo ""
cat "$TARGET_FILE"
