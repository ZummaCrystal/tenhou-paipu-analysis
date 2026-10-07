# -*- coding: utf-8 -*-
"""Node 端打点驱动。

调用 mjscore/node_harness.js —— 它 require 的是**前端同一份** web/js/mjlog.js + web/js/replay.js
+ web/js/mjsfeat.js，所以 Node 这一路和浏览器里跑的代码完全一致。

Node 与 Python 两个工具的分工：
    * node   : 解析 XML（web/js/mjlog.js）+ 逐帧回放（web/js/replay.js）+ 16 特征打点（web/js/mjsfeat.js）
    * python : 解析 XML（mjscore/mjlog.py）+ 逐帧回放（mjscore/replay.py）+ 打点（mjscore/feats.py）
两路对同一批牌谱的打点结果必须逐字段相同（test/mjscore_test.py 交叉校验）。

为什么用 subprocess 而不是自己写 JSON：本仓库既有前端 JS 解析器又有 Python 解析器，
两条路互为参照；Node 负责把 JS 一侧的结果以 JSONL 吐出，Python 负责入库 / 检索 / 服务。
"""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, "mjscore", "node_harness.js")

NODE_CANDIDATES = (
    os.environ.get("MJSCORE_NODE"),
    r"D:\Program Files\nodejs\node.exe",
    r"C:\Program Files\nodejs\node.exe",
    r"D:\Program Files (x86)\nodejs\node.exe",
)


class NodeMissing(RuntimeError):
    pass


class NodeFailed(RuntimeError):
    pass


def find_node():
    for c in NODE_CANDIDATES:
        if c and os.path.isfile(c):
            return c
    w = shutil.which("node")
    return w if w and os.path.isfile(w) else None


def available():
    return find_node() is not None


def run(mode, files, node=None, timeout=900, out_path=None):
    """跑一次 node_harness.js，返回 (jsonl 对象列表, stderr)。

    mode: records / frames / summary / invariants
    out_path: 给定则让 node 写文件再读回（也用于 --capture 生成 fixture）
    """
    node = node or find_node()
    if not node:
        raise NodeMissing("找不到 node.exe：请改用 --tool python，或设置环境变量 MJSCORE_NODE 指向 node")
    files = [os.path.abspath(f) for f in files]
    argv = [node, HARNESS, "--" + mode]
    if out_path:
        argv += ["--out", os.path.abspath(out_path)]
    argv += files
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise NodeFailed("node 打点失败（exit %d）：%s"
                         % (proc.returncode, (proc.stderr or proc.stdout or "").strip()[-1200:]))
    if out_path:
        with open(out_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = proc.stdout
    return parse_jsonl(text), (proc.stderr or "")


def parse_jsonl(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _with_paths(files, records):
    """给打点行补上原始文件路径（按牌谱特征码对应）。"""
    by_id = {os.path.splitext(os.path.basename(f))[0]: os.path.abspath(f) for f in files}
    for r in records:
        r["path"] = by_id.get(r.get("log_id"), "")
        r["tool"] = "node"
    return records


def node_records(files, node=None, out_path=None):
    recs, _ = run("records", files, node=node, out_path=out_path)
    return _with_paths(files, recs)


def node_frames(files, node=None, out_path=None):
    recs, _ = run("frames", files, node=node, out_path=out_path)
    return _with_paths(files, recs)


def node_invariants(files, node=None):
    recs, err = run("invariants", files, node=node)
    return recs, err


def node_summary(files, node=None):
    recs, _ = run("summary", files, node=node)
    return recs