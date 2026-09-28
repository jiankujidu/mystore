#!/usr/bin/env python3
"""
fn-store 构建脚本
=================
遍历 apps/ 下所有应用目录，逐个调用 fnpack build 生成 .fpk，
计算 SHA256/size，生成 V2 规范的 fnpack.json 到 dist/ 目录。

用法:
    python build.py [--fnpack /path/to/fnpack] [--source-name 名称] [--source-author 作者]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 使用 CWD 而非 __file__，避免 Windows Git Bash E: 盘挂载路径混淆
ROOT = Path.cwd()
APPS_DIR = ROOT / "apps"
DIST_DIR = ROOT / "dist"
FNPACK_JSON = DIST_DIR / "fnpack.json"

# 飞牛 9 大固定分类（不可自定义）
VALID_CATEGORIES = {
    "影音娱乐", "系统工具", "编程开发", "AI赋能",
    "生活服务", "智能智控", "教育学习", "游戏地带", "硬件驱动",
}

# 合法 platform
VALID_PLATFORMS = {"all", "x86", "arm"}


def parse_args():
    p = argparse.ArgumentParser(description="fn-store 构建器")
    p.add_argument("--fnpack", default=os.environ.get("FNPACK_BIN", "fnpack"),
                   help="fnpack 可执行文件路径或名称")
    p.add_argument("--source-name", default=os.environ.get("FN_STORE_NAME", "我的飞牛应用仓库"))
    p.add_argument("--source-author", default=os.environ.get("FN_STORE_AUTHOR", "fn-store-owner"))
    p.add_argument("--homepage", default=os.environ.get("FN_STORE_HOMEPAGE", ""))
    p.add_argument("--base-url", default=os.environ.get("FN_STORE_BASE_URL", ""),
                   help="GitHub Pages 的根 URL（用于拼接 FPK 下载地址）")
    return p.parse_args()


def load_app_meta(app_dir: Path) -> dict:
    """从 app/app.json 读取应用元数据"""
    meta_file = app_dir / "app.json"
    if not meta_file.exists():
        sys.exit(f"[ERROR] {app_dir.name}: 缺少 app.json（应用元数据文件）")
    with open(meta_file, encoding="utf-8") as f:
        return json.load(f)


def parse_manifest(manifest: Path) -> dict:
    """解析 fnpack manifest（key=value 格式）"""
    m = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        m[k.strip()] = v.strip()
    return m


def run_fnpack(fnpack_bin: str, app_dir: Path) -> Path:
    """调用 fnpack build（需 cd 到 app 目录执行），返回 .fpk 文件路径"""
    # fnpack build 输出固定在当前目录，文件名 = appname.fpk
    # 先清理旧的
    for old_fpk in app_dir.glob("*.fpk"):
        old_fpk.unlink()

    print(f"  → fnpack build ...")
    r = subprocess.run(
        [fnpack_bin, "build"],
        cwd=str(app_dir),
        capture_output=True, text=True,
    )
    # 打印 fnpack 输出便于调试
    if r.stdout.strip():
        print("  [fnpack]", r.stdout.strip()[:500])
    if r.stderr.strip():
        print("  [fnpack stderr]", r.stderr.strip()[:500])
    if r.returncode != 0:
        sys.exit(f"[ERROR] fnpack build 失败: {app_dir.name}")

    fpk_files = list(app_dir.glob("*.fpk"))
    if not fpk_files:
        # 兜底：递归搜索
        fpk_files = list(app_dir.rglob("*.fpk"))
    if not fpk_files:
        sys.exit(f"[ERROR] 未生成 FPK: {app_dir.name}（目录内容: {[p.name for p in app_dir.iterdir()]}）")
    return fpk_files[0]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_one(app_dir: Path, fnpack_bin: str, base_url: str, now: str) -> dict:
    app_name = app_dir.name
    print(f"\n[构建] {app_name}")

    meta = load_app_meta(app_dir)
    manifest_dir = app_dir  # manifest 直接放在 app_dir 下
    manifest = manifest_dir / "manifest"
    mdata = parse_manifest(manifest)

    version = mdata.get("version", "1.0.0")
    fpk = run_fnpack(fnpack_bin, app_dir)

    # 复制到 dist/fpk/
    fpk_out_dir = DIST_DIR / "fpk"
    fpk_out_dir.mkdir(parents=True, exist_ok=True)
    fpk_out = fpk_out_dir / f"{app_name}-{version}.fpk"
    shutil.copy2(fpk, fpk_out)

    sha = sha256_file(fpk_out)
    size = fpk_out.stat().st_size
    print(f"  FPK: {fpk_out.name}  size={size}  sha256={sha[:16]}...")

    # 复制图标和预览图
    icons_dir = app_dir / "icons"
    if icons_dir.is_dir():
        dist_icons = DIST_DIR / "icons" / app_name
        dist_icons.mkdir(parents=True, exist_ok=True)
        for f in icons_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, dist_icons / f.name)

    previews_dir = app_dir / "previews"
    if previews_dir.is_dir():
        dist_prev = DIST_DIR / "previews" / app_name
        dist_prev.mkdir(parents=True, exist_ok=True)
        for f in sorted(previews_dir.iterdir()):
            if f.is_file():
                shutil.copy2(f, dist_prev / f.name)

    # 构建 apps 条目
    platforms = meta.get("platform", [mdata.get("platform", "all")])
    if isinstance(platforms, str):
        platforms = [platforms]
    for p in platforms:
        if p not in VALID_PLATFORMS:
            sys.exit(f"[ERROR] 非法 platform: {p}（允许: {VALID_PLATFORMS}）")

    categories = meta.get("categories", ["系统工具"])
    for c in categories:
        if c not in VALID_CATEGORIES:
            sys.exit(f"[ERROR] 非法分类: {c}（允许: {VALID_CATEGORIES}）")

    icon_file = "icon.png"
    icon_src = app_dir / "icons" / icon_file
    if not icon_src.exists():
        icon_src = app_dir / "ICON_256.PNG"
    if icon_src.exists():
        dist_icon = DIST_DIR / "icons" / app_name / "icon.png"
        dist_icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon_src, dist_icon)
        icon_url = f"icons/{app_name}/icon.png"
    else:
        icon_url = ""
        print(f"  [WARN] 未找到图标，icon_url 留空")

    preview_files = sorted((DIST_DIR / "previews" / app_name).glob("*")) \
        if (DIST_DIR / "previews" / app_name).exists() else []
    preview_urls = [f"previews/{app_name}/{f.name}" for f in preview_files][:8]

    # FPK 下载 URL
    if base_url:
        download_url = f"{base_url}/fpk/{app_name}-{version}.fpk"
    else:
        download_url = f"fpk/{app_name}-{version}.fpk"

    app_entry = {
        "display_name": meta.get("display_name", mdata.get("display_name", app_name)),
        "desc": meta.get("desc", mdata.get("desc", "")),
        "platform": platforms,
        "categories": categories,
        "icon_url": icon_url,
        "preview_urls": preview_urls,
        "run_as": meta.get("run_as", "package"),
        "install_type": meta.get("install_type", ""),
        "is_docker": meta.get("is_docker", False),
        "maintainer": meta.get("maintainer", mdata.get("maintainer", "")),
        "releases": {
            version: {
                "updated_at": now,
                "changelog": meta.get("changelog", "首次发布"),
                "packages": {
                    "all": {
                        "download_url": download_url,
                        "sha256": sha,
                        "size": size,
                    }
                },
            }
        },
    }

    # 多架构包
    extra_packages = {}
    arch_fpk_map = {
        "x86": f"{app_name}-{version}-x86.fpk",
        "arm": f"{app_name}-{version}-arm.fpk",
    }
    for arch in platforms:
        if arch == "all":
            continue
        fpk_path = DIST_DIR / "fpk" / arch_fpk_map[arch]
        if fpk_path.exists():
            extra_packages[arch] = {
                "download_url": f"{base_url}/fpk/{arch_fpk_map[arch]}" if base_url else f"fpk/{arch_fpk_map[arch]}",
                "sha256": sha256_file(fpk_path),
                "size": fpk_path.stat().st_size,
            }
    if extra_packages:
        app_entry["releases"][version]["packages"].update(extra_packages)

    return app_entry


def main():
    args = parse_args()
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    if not APPS_DIR.exists():
        sys.exit(f"[ERROR] 找不到 apps 目录: {APPS_DIR}")

    app_dirs = [d for d in APPS_DIR.iterdir() if d.is_dir() and (d / "manifest").exists()]
    if not app_dirs:
        sys.exit("[ERROR] apps/ 下没有有效应用（需要包含 manifest 文件）")

    print(f"发现 {len(app_dirs)} 个应用")
    print(f"fnpack: {args.fnpack}")

    apps = {}
    for app_dir in sorted(app_dirs):
        apps[app_dir.name] = build_one(app_dir, args.fnpack, args.base_url, now)

    # 组装 fnpack.json
    fnpack_json = {
        "schema_version": "2",
        "source_info": {
            "name": args.source_name,
            "author": args.source_author,
            **({"homepage": args.homepage} if args.homepage else {}),
        },
        "apps": apps,
    }

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with open(FNPACK_JSON, "w", encoding="utf-8") as f:
        json.dump(fnpack_json, f, ensure_ascii=False, indent=2)

    print(f"\n✅ fnpack.json 已生成: {FNPACK_JSON}")
    print(f"   共 {len(apps)} 个应用")

    # 打印摘要
    for name, entry in apps.items():
        ver = list(entry["releases"].keys())[0]
        pk = entry["releases"][ver]["packages"]
        archs = list(pk.keys())
        print(f"   - {entry['display_name']} ({name})  v{ver}  架构: {archs}")


if __name__ == "__main__":
    main()
