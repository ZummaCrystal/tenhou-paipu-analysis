# -*- coding: utf-8 -*-
"""mjscore —— 天凤牌谱（mjlog）解析 / 回放 / 特征打点 / 数据库 工具包。

模块划分：
    mjlog         mjlog XML 解析（与 web/js/mjlog.js 行为一致）
    replay        逐帧回放（与 web/js/replay.js 行为一致）
    feats         第一类特征打点（16 个特征）+ 特征注册表
    store         SQLite 打点数据库（建库 / 写库 / 检索 / 导出）
    nodeharness   调用 Node 端 web/js/mjlog.js + web/js/replay.js 生成 JSONL 打点
    cli           命令行入口（tools/analyze.py 调用）
    server        本地静态服务 + /api 接口（server.py 调用）

软件版本见 __version__（当前 v0.1.0）。每次写库都会把该版本记进数据库（meta.app_version），
版本不一致的数据库不允许继续扩充 / 加载。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

APP_NAME = "天凤牌谱分析"
__version__ = "0.1.0"
AUTHOR = "Zumma Crystal"
AUTHOR_EMAIL = "z1025zzsg@sohu.com"
__author__ = AUTHOR
__email__ = AUTHOR_EMAIL