# -*- coding: utf-8 -*-
"""mjscore —— 天凤牌谱（mjlog）解析 / 回放 / 特征打点 / 数据库 工具包。

模块划分：
    mjlog         mjlog XML 解析（与 web/js/mjlog.js 行为一致）
    replay        逐帧回放（与 web/js/replay.js 行为一致）
    ai_models     AI 模型词汇层（naga_types 原名 -> 规范名 / 系列，用户 m04556 ②）
    feats         特征打点（第零类 7 项，按帧判定 + 第一类 17 项 + 第二类 17 项 + 第三类 1 项）
    store         SQLite 打点数据库（建库 / 写库 / 检索 / 导出）
    nodeharness   调用 Node 端 web/js/mjlog.js + web/js/replay.js 生成 JSONL 打点
    cli           命令行入口（tools/analyze.py 调用）
    server        本地静态服务 + /api 接口（server.py 调用）

软件版本见 __version__（当前 v1.4.4）。每次写库都会把该版本记进数据库（meta.app_version）。
**大版本 + 中版本相同**的库可以直接继续扩充 / 加载（补丁版本不同不影响，用户 m09354 ⑤）。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

import re

APP_NAME = "天凤牌谱分析"
__version__ = "1.4.4"
AUTHOR = "Zumma Crystal"
AUTHOR_EMAIL = "z1025zzsg@sohu.com"
__author__ = AUTHOR
__email__ = AUTHOR_EMAIL


def version_tuple(v):
    """把 '1.3.1' / 'v1.3' 解析成 (1, 3, 1)（忽略非数字部分）。"""
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def major_minor(v):
    """大版本 + 中版本：'1.3.1' -> (1, 3)。"""
    return version_tuple(v)[:2]


def version_compatible(recorded, current=None):
    """库记录的软件版本能否被当前软件（current，默认 __version__）使用。

    用户 m09354 ⑤：只要大版本 + 中版本相同即可；recorded 为空（第 22 轮以前建的库）按兼容处理。
    """
    if not str(recorded or "").strip():
        return True
    return major_minor(recorded) == major_minor(current if current is not None else __version__)
