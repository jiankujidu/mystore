#!/usr/bin/env bash
# build.sh — 构建所有应用 FPK + 生成 fnpack.json
# 用法:  ./build.sh [--base-url https://yourname.github.io/fn-repo]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 自动查找 fnpack
if [ -n "$FNPACK_BIN" ]; then
    FNPACK="$FNPACK_BIN"
elif command -v fnpack &>/dev/null; then
    FNPACK="fnpack"
elif [ -f "$SCRIPT_DIR/../bin/fnpack.exe" ]; then
    FNPACK="$SCRIPT_DIR/../bin/fnpack.exe"
else
    echo "[ERROR] 找不到 fnpack，请设置 FNPACK_BIN 环境变量"
    exit 1
fi

echo "fnpack: $FNPACK"

# 仓库源名称/作者（可通过环境变量覆盖）
FN_STORE_NAME="${FN_STORE_NAME:-我的飞牛应用仓库}"
FN_STORE_AUTHOR="${FN_STORE_AUTHOR:-fn-store-owner}"

# 解析 --base-url 参数
BASE_URL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-url)
            BASE_URL="$2"; shift 2 ;;
        *)
            shift ;;
    esac
done
FN_STORE_BASE_URL="${BASE_URL:-$FN_STORE_BASE_URL}"

python3 "$SCRIPT_DIR/build.py" \
    --fnpack "$FNPACK" \
    --source-name "$FN_STORE_NAME" \
    --source-author "$FN_STORE_AUTHOR" \
    --base-url "$FN_STORE_BASE_URL"
