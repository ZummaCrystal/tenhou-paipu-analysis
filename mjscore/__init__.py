# -*- coding: utf-8 -*-
"""mjscore —— 天凤牌谱（mjlog）解析 / 回放 / 特征打点 / 数据库 工具包。

模块划分：
    mjlog         mjlog XML 解析（与 web/js/mjlog.js 行为一致）
    replay        逐帧回放（与 web/js/replay.js 行为一致）
    ai_models     AI 模型词汇层（naga_types 原名 -> 规范名 / 系列，用户 m04556 ②）
    feats         特征打点（第零类 5 项，按帧判定 + 第一类 17 项 + 第二类 17 项 + 第三类 1 项）
    store         SQLite 打点数据库（建库 / 写库 / 检索 / 导出）
    nodeharness   调用 Node 端 web/js/mjlog.js + web/js/replay.js 生成 JSONL 打点
    cli           命令行入口（tools/analyze.py 调用）
    server        本地静态服务 + /api 接口（server.py 调用）

软件版本见 __version__（当前 v1.3.0）。每次写库都会把该版本记进数据库（meta.app_version），
版本不一致的数据库不允许继续扩充 / 加载。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

APP_NAME = "天凤牌谱分析"
__version__ = "1.3.0"
AUTHOR = "Zumma Crystal"
AUTHOR_EMAIL = "z1025zzsg@sohu.com"
__author__ = AUTHOR
__email__ = AUTHOR_EMAIL