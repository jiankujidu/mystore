#!/bin/bash
# MyStore NAS 侧安装器 CGI（fnOS 官方机制）
# 由 fnOS Web 网关执行，把指定 .fpk 直接装到 NAS，而不是下载到用户浏览器。
# 网页 JS: fetch("install.cgi?fpk=<url>") 调用。
#
# 安装命令用 fnOS 预装的 appcenter-cli：  appcenter-cli install-fpk <file>
# 也兜底探测 fpkg / fncgi 等历史包管理命令。
#
# 用法：GET /install.cgi?fpk=https://.../xxx.fpk
# 返回：JSON  {"ok":true,"msg":"..."} 或 {"ok":false,"error":"..."}

VAR_DIR="${TRIM_PKGVAR:-/var/apps/mystore/var}"
LOG="${VAR_DIR}/install.log"
mkdir -p "$VAR_DIR" 2>/dev/null
STAMP() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(STAMP) $*" >> "$LOG"; }

json_out() { # 打印并结束：$1 = 引号包裹的 JSON 体
    echo "Content-Type: application/json; charset=utf-8"
    echo ""
    echo "$1"
    exit 0
}
err() { log "ERROR: $1"; json_out "{\"ok\":false,\"error\":$(printf '%s' "$1" | sed 's/"/\\"/g' | sed 's/^/"'; echo '"')}"; }

# ---------- 只允许 GET ----------
[ "${REQUEST_METHOD}" = "GET" ] && true || { log "method not allowed"; json_out '{"ok":false,"error":"method not allowed"}'; }

# ---------- 解析 fpk 参数 ----------
QUERY="${QUERY_STRING:-${REQUEST_URI#*?}}"
FPK=""
if [ -n "$QUERY" ]; then
    while IFS='=' read -r k v; do
        [ "$k" = "fpk" ] && FPK="$v"
    done < <(printf '%s' "$QUERY" | tr '&' '\n')
fi
# 还原 %XX（仅处理 % 形式）
if printf '%s' "$FPK" | grep -q '%'; then
    FPK=$(printf '%s' "$FPK" | sed 's/%\([0-9A-Fa-f][0-9A-Fa-f]\)/\\x\1/g' | xargs -0 -r printf '%b' 2>/dev/null || true)
fi

[ -z "$FPK" ] && { log "missing fpk param"; json_out '{"ok":false,"error":"missing fpk param"}'; }

# ---------- 白名单：只允许 http/https 的 .fpk 或 /tmp 本地路径 ----------
case "$FPK" in
  http://*|https://*) ;;
  /tmp/*.fpk|/tmp/*.FPK|/tmp/*.tgz) ;;
  *) log "fpk source not allowed: $FPK"; json_out '{"ok":false,"error":"fpk source not allowed"}' ;;
esac
log "install request fpk=$FPK"

# ---------- 定位安装命令 ----------
find_cmd() {
  for c in "$@"; do
    if command -v "$c" >/dev/null 2>&1; then printf '%s' "$c"; return 0; fi
    if [ -x "$c" ]; then printf '%s' "$c"; return 0; fi
  done
  return 1
}

# 主：appcenter-cli（fnOS 官方），子命令 install-fpk
APPCLI="$(find_cmd /usr/bin/appcenter-cli /usr/local/bin/appcenter-cli /opt/trim/bin/appcenter-cli appcenter-cli)"
# 兜底：fpkg（旧版/其它命名），子命令多为 add
FPPKG="$(find_cmd /usr/bin/fpkg /usr/local/bin/fpkg /opt/trim/bin/fpkg fpkg)"

# ---------- 准备安装文件（下载到 NAS 本地） ----------
DL_DIR="${VAR_DIR}/download"
mkdir -p "$DL_DIR" 2>/dev/null
if [ "${FPK:0:8}" = "http://" ] || [ "${FPK:0:9}" = "https://" ]; then
    DL="$DL_DIR/pkg-$(printf '%s' "$FPK" | md5sum | cut -d' ' -f1).fpk"
    log "downloading -> $DL"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 3 -o "$DL" "$FPK" 2>>"$LOG" || { log "download failed (curl)"; err "download failed"; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$DL" "$FPK" 2>>"$LOG" || { log "download failed (wget)"; err "download failed"; }
    else
        log "no curl/wget on NAS"; err "no downloader available on NAS"
    fi
    [ -s "$DL" ] || { log "download empty"; err "downloaded file empty"; }
    PKG_PATH="$DL"
else
    PKG_PATH="$FPK"
fi

# ---------- 权限：尽量 root（sudo -n 免交互） ----------
SUDO=""
if [ "$(id -u)" != "0" ] && command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    SUDO="sudo"
    log "using sudo for install"
fi

# ---------- 判重：已装同 app 则不重复装 ----------
# 从 fpk 文件名推断 appname（mystore-1.1.7.fpk -> mystore）
APP_ID="$(basename "$FPK")"
APP_ID="${APP_ID%.fpk}"; APP_ID="${APP_ID%.FPK}"
APP_ID="${APP_ID##*-}"  # 去掉末尾 -版本号 留下 appname（若命名 app-x.y.z）
# 兜底：保留原始 basename 作为 appid
APP_NAME_GUESS="$APP_ID"
if [ -n "$APPCLI" ]; then
    LIST_OUT="$($SUDO "$APPCLI" list 2>>"$LOG" || true)"
    # 匹配 appname（忽略大小写）：列出的每行里含该 appname 即已装
    if printf '%s\n' "$LIST_OUT" | grep -qi "$APP_NAME_GUESS"; then
        log "app '$APP_NAME_GUESS' already present; skipping install"
        json_out "{\"ok\":true,\"msg\":\"已安装（检测到 NAS 上已有 $APP_NAME_GUESS），无需重复装\"}"
    fi
fi

# ---------- 执行安装 ----------
RC=0
if [ -n "$APPCLI" ]; then
    log "installing via $SUDO $APPCLI install-fpk $PKG_PATH"
    $SUDO "$APPCLI" install-fpk "$PKG_PATH" >>"$LOG" 2>&1; RC=$?
elif [ -n "$FPPKG" ]; then
    log "installing via $SUDO $FPPKG add $PKG_PATH"
    $SUDO "$FPPKG" add "$PKG_PATH" >>"$LOG" 2>&1; RC=$?
else
    log "no appcenter-cli/fpkg found"
    err "appcenter-cli not found on this NAS"
fi

# ---------- 清理远程下载的临时包 ----------
[ "$PKG_PATH" = "$DL" ] && rm -f "$DL" 2>/dev/null

if [ "$RC" -eq 0 ]; then
    log "install OK ($FPK)"
    json_out '{"ok":true,"msg":"已安装到飞牛 NAS"}'
else
    log "install FAILED rc=$RC ($FPK)"
    err "install failed (rc=$RC)"
fi
