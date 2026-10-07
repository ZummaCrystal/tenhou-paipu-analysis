#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Download Tenhou (天凤) mahjong log files.

第 21 轮起核心逻辑搬进 ``mjscore/download.py``（前端「牌谱下载」走同一个实现），
本文件保留同样的命令行用法：

    python tools/download_tenhou.py <url> [<url> ...]
    python tools/download_tenhou.py --url-file tenhou-url.txt
    python tools/download_tenhou.py            # 不给输入时回退到 ./tenhou-url.txt
    python tools/download_tenhou.py <url> -o data/paipu/20260920-1530

作者：Zumma Crystal <z1025zzsg@sohu.com>。

支持的输入形式（每行一个，互不干扰）：
    http://tenhou.net/0/?log=2026082919gm-00a9-0000-4e40cd3e&tw=0
    http://tenhou.net/0/log/?2026082919gm-00a9-0000-4e40cd3e
    2026082919gm-00a9-0000-4e40cd3e            （裸特征码）

文件名 = 特征码 + ``.xml``；默认输出目录仍是项目根的 ``data/``；
界面上的「牌谱下载」默认写到 ``data/paipu/<时间戳目录名>/``。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 本脚本在 tools/ 下，项目根 = 上一级（tenhou-url.txt / data/ 都在项目根）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mjscore import download as _dl  # noqa: E402  （要在 sys.path 调整之后）

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data"
DEFAULT_URL_FILE = PROJECT_ROOT / "tenhou-url.txt"

# 兼容旧名字：核心实现都在 mjscore/download.py
DownloadError = _dl.DownloadError
extract_log_id = _dl.extract_log_id
build_download_url = _dl.build_download_url
fetch_log = _dl.fetch_log
looks_like_mjlog = _dl.looks_like_mjlog
save_log = _dl.save_log
read_url_file = _dl.read_url_file


def collect_inputs(cli_urls, url_file=None):
    """合并命令行 URL 与文本文件里的 URL，去重保序。"""
    items = list(cli_urls or [])
    if url_file is not None:
        items.extend(read_url_file(url_file))
    return _dl.collect_urls(items)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Download Tenhou mahjong logs into the project's data/ directory.",
    )
    parser.add_argument("urls", nargs="*", help="Tenhou log URLs, or bare log ids.")
    parser.add_argument(
        "-f", "--url-file", type=Path, default=None,
        help="File containing one URL per line (comments with '#' allowed).",
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory to store downloads (default: %s)." % DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--no-overwrite", action="store_true",
        help="Do not overwrite files that already exist.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    url_file = args.url_file
    if not args.urls and url_file is None and DEFAULT_URL_FILE.is_file():
        url_file = DEFAULT_URL_FILE
        print("* No URLs given; using default file: %s" % url_file)

    try:
        inputs = collect_inputs(args.urls, url_file)
    except FileNotFoundError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    if not inputs:
        print("ERROR: no URLs provided. Pass URLs as arguments or use --url-file.",
              file=sys.stderr)
        return 2

    output_dir = args.output_dir
    print("* Output directory: %s" % output_dir)
    print("* %d URL(s) to process." % len(inputs))

    total = len(inputs)

    def on_item(entry):
        index = entry.get("_index")
        print("[%d/%d] %s" % (index, total, entry["input"]))
        if entry["ok"]:
            name = os.path.basename(entry["path"] or "")
            if entry["written"]:
                print("  -> saved %s (%d bytes)" % (name, entry["bytes"]))
            else:
                print("  = skipped (already exists) %s" % name)
        else:
            print("  x %s" % entry["error"], file=sys.stderr)

    ordered = list(inputs)
    counter = {"i": 0}

    def on_item_counted(entry):
        counter["i"] += 1
        entry["_index"] = counter["i"]
        on_item(entry)

    res = _dl.run_download(ordered, str(output_dir), overwrite=not args.no_overwrite,
                           on_item=on_item_counted)

    print("-" * 60)
    print("* Done: %d succeeded, %d failed." % (res["saved"], res["failed"]))
    if res["failed"]:
        for entry in res["results"]:
            if not entry["ok"]:
                print("  x %s: %s" % (entry["input"], entry["error"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())