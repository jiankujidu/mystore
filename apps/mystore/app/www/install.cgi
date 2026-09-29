#!/bin/bash
# MyStore NAS 侧安装器 CGI
# 由 fnOS Web 网关执行（拥有系统权限），把指定 .fpk 直接装到 NAS，
# 而不是下载到用户浏览器。网页 JS fetch("install.cgi?fpk=<url>") 调用。
#
# 用法：GET /install.cgi?fpk=https://.../xxx.fpk
# 返回：JSON  {"ok":true,"msg":"..."} 或 {"ok":false,"error":"..."}

LOG="${TRIM_PKGVAR:-/var/apps/mystore/var}/install.log"
STAMP="$(date '+%Y-%m-%d %H:%M:%S')"

q() { printf '%s' "$1" | sed 's/&/\\&/g'; }
out_json() { # $1=key $2=raw-value(未转义)
    printf '{"%s":' "$1"
    if [ "$1" = "ok" ]; then
        [ "$2" = "true" ] && { echo "true"; exit 0; }
        [ "$2" = "false" ] && { echo "false"; exit 0; }
    fi
    # string value, escape backslash + quote
    v=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')
    echo "\"$v\""
    exit 0
}
fail() { echo "Content-Type: application/json"; echo ""; out_json "error" "$1"; }

echo "Content-Type: application/json"
echo ""

# 仅允许 GET
[ "${REQUEST_METHOD}" = "GET" ] || { echo '{"ok":false,"error":"method not allowed"}'; exit 0; }

# 解析 query（取 fpk= 值）
QUERY="${QUERY_STRING:-${REQUEST_URI#*?}}"
FPK=""
if [ -n "$QUERY" ]; then
    for pair in $(printf '%s' "$QUERY" | tr '&' ' '); do
        [ "${pair%%=*}" = "fpk" ] && FPK="${pair#*=}"
    done
fi

# URL 解码（只处理 % 形式，安全：白名单校验）
FPK_DECODED=$(printf '%s' "$FPK" | sed 's/%\([0-9A-Fa-f][0-9A-Fa-f]\)/\\x\1/g' | xargs -0 printf '%b' 2>/dev/null)
[ -n "$FPK_DECODED" ] && FPK="$FPK_DECODED"

[ -z "$FPK" ] && { echo '{"ok":false,"error":"missing fpk param"}'; exit 0; }

# 安全：只允许 http/https 的 .fpk / 或 NAS 本地路径 /tmp 下的 .fpk
case "$FPK" in
  http://*.fpk|https://*.fpk|http://*.FPK|https://*.FPK) ;;
  /tmp/*.fpk|/tmp/*.FPK) ;;
  *) { echo '{"ok":false,"error":"fpk source not allowed"}'; exit 0; }
esac

echo "$STAMP install.cgi fpk=$FPK" >> "$LOG"

# 定位 fpkg / 下载工具
FPKG=""
for c in /usr/bin/fpkg /usr/local/bin/fpkg /opt/trim/bin/fpkg fpkg; do
    command -v "$c" >/dev/null 2>&1 && { FPKG="$c"; break; }
done
[ -z "$FPKG" ] && {
    echo "$STAMP ERROR: fpkg not found" >> "$LOG"
    fail "fpkg not found on this NAS"
}

# 下载到 NAS 临时目录
TMP="${TRIM_PKGVAR:-/var/apps/mystore/var}/download"
mkdir -p "$TMP" 2>/dev/null
DL="$TMP/$(echo "$FPK" | md5sum | cut -d' ' -f1).fpk"

if [ "${FPK:0:8}" = "http://" ] || [ "${FPK:0:9}" = "https://" ]; then
    echo "$STAMP downloading -> $DL" >> "$LOG"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$DL" "$FPK" 2>>"$LOG" || { echo "$STAMP download failed(curl)" >> "$LOG"; fail "download failed"; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$DL" "$FPK" 2>>"$LOG" || { echo "$STAMP download failed(wget)" >> "$LOG"; fail "download failed"; }
    else
        echo "$STAMP no curl/wget" >> "$LOG"; fail "no downloader available"
    fi
    [ -s "$DL" ] || { echo "$STAMP empty download" >> "$LOG"; fail "downloaded file empty"; }
fi
TMP_PKG="$FPK"
[ -f "$FPK" ] && TMP_PKG="$FPK"

# 以 root 权限安装（CGI 由 fnOS 网关以 root 运行；若无 root 则原样执行）
INSTALLED_BY=""
INSTALLED_BY_OUT="$STAMP"
echo "$STAMP running install: $TMP_PKG" >> "$LOG"
if sudo -n true >/dev/null 2>&1; then
    sudo "$FPKG" add "$TMP_PKG" >>"$LOG" 2>&1 && INSTALLED_BY=ok || INSTALLED_BY=err
else
    "$FPKG" add "$TMP_PKG" >>"$LOG" 2>&1 && INSTALLED_BY=ok || INSTALLED_BY=err
fi
RC=$?

# 清理
[ "${FPK:0:8}" = "http://" ] || [ "${FPK:0:9}" = "https://" ] && rm -f "$DL" 2>/dev/null

if [ "$INSTALLED_BY" = "ok" ]; then
    echo "$STAMP install OK ($FPK)" >> "$LOG"
    echo '{"ok":true,"msg":"已安装到飞牛 NAS"}'
else
    echo "$STAMP install FAILED rc=$RC ($FPK)" >> "$LOG"
    fail "install failed (rc=$RC)"
fi
