#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""analyze.py —— 天凤牌谱分析命令行入口。

真正的实现在 mjscore/ 包内：
    mjlog.py      mjlog XML  -> 事件流
    replay.py     事件流     -> 逐帧状态（与 web/js/replay.js 同款）
    feats.py      逐帧状态   -> 16 个第一类特征打点（与 web/js/mjsfeat.js 同款）
    nodeharness.py 调 node 跑 js 一侧的同一套解析/打点
    store.py      SQLite 打点库（建库 / 写库 / 检索 / 导出）
    server.py     本地服务（前端 + /api）
用法见 `python tools/analyze.py --help`。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

import os
import sys

# 本脚本在 tools/ 下，项目根 = 上一级（mjscore/ 在项目根）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mjscore import cli

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))