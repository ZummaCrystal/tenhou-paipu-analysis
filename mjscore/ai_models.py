# -*- coding: utf-8 -*-
"""AI 模型词汇层（用户 m04556）：把 NAGA 报告 ``naga_types`` 里的原始模型名规范化。

规范命名（用户 m04556 ③）：``<系列名称>-<版本号>-<风格>`` 或 ``<系列名称>-<风格>``；
系列名 = 第一个短横线之前的字符串（NAGA / Mortal），检索按系列聚合。
用户 m05806 ①：Mortal 的名字里不再带风格字母（``Mortal-4.1b-平衡`` → ``Mortal-4.1-平衡``），
风格一律由 ``-避四 / -平衡 / -争一`` 表示（4.1a 避四 / 4.1b 平衡 / 4.1c 争一）。

第 74 轮（用户 m09507）：新版 NAGA 报告的 naga_types 里出现「アナンタ / ウロボロス」，
分别命名为 NAGA-避四 / NAGA-争一（同属 NAGA 系列）；它们是「ニシキ」之外的两种 NAGA 形态，
打牌概率只给 `dahai_detail`（37 槽，含赤 5）而不给 `dahai_pred`，见 naga._collapse_dahai()。

官方 viewer（static/naga_report/1.1.3/js/index.js）**直接拿 naga_types 的值当模型显示名**，
源码与官网都没有「バランス / 超副露 / Mortal」这些字样，所以「ニシキ = 平衡形」「カガシ = 超副露形」
这组别名按用户 m04556 给出的口径写在这里（唯一的映射表）。
"""

import re

# 系列名（用户 m04556 ③ 的判定口径：取第一个短横线之前的字符串）
SERIES_NAGA = "NAGA"
SERIES_MORTAL = "Mortal"

# 规范名：报告 `naga_types` 的原始值 -> 对外名称
BALANCED = "NAGA-平衡"          # ニシキ：NAGA 的平衡（バランス）形
SUPER_HURO = "NAGA-超副露"      # カガシ：NAGA 的超副露形
NAGA_AVOID4 = "NAGA-避四"       # アナンタ：新版 NAGA 的避四形（用户 m09507）
NAGA_AGGRESSIVE = "NAGA-争一"   # ウロボロス：新版 NAGA 的争一形（用户 m09507）
# Mortal 4.1 的三种风格（用户 m05806 ①）：a = 避四、b = 平衡、c = 争一
MORTAL_41A = "Mortal-4.1-避四"
MORTAL_41B = "Mortal-4.1-平衡"
MORTAL_41C = "Mortal-4.1-争一"
MORTAL_TAG_TO_NAME = {"4.1a": MORTAL_41A, "4.1b": MORTAL_41B, "4.1c": MORTAL_41C}

ALIASES = {
    "ニシキ": BALANCED,
    "カガシ": SUPER_HURO,
    "アナンタ": NAGA_AVOID4,
    "ウロボロス": NAGA_AGGRESSIVE,
    "ヒバカリ": "NAGA-ヒバカリ",
    "オメガ": "NAGA-オメガ",
    "ガンマ": "NAGA-ガンマ",
    "ニュー": "NAGA-ニュー",
    "シグマ": "NAGA-シグマ",
    "4.1a": MORTAL_41A,
    "4.1b": MORTAL_41B,
    "4.1c": MORTAL_41C,
}

# 裸版本号（4.0 / 3.0 …）按 Mortal 的平衡形处理；带风格字母的按 4.1 的 a/b/c 映射
_MORTAL_STYLE_BY_CODE = {"a": "避四", "b": "平衡", "c": "争一"}
_VERSION_RE = re.compile(r"^\d+(?:\.\d+)?[a-z]?$", re.I)

# 第零类特征（用户 m04556 ② / m05937 ②）：(key, 显示名, SQLite 列名, 对应规范模型名)
CHOICES = [
    ("ai_balance", "NAGA-平衡 分析", "f_ai_balance", BALANCED),
    ("ai_superhuro", "NAGA-超副露 分析", "f_ai_superhuro", SUPER_HURO),
    ("ai_naga_avoid4", "NAGA-避四 分析", "f_ai_naga_avoid4", NAGA_AVOID4),
    ("ai_naga_aggressive", "NAGA-争一 分析", "f_ai_naga_aggressive", NAGA_AGGRESSIVE),
    ("ai_mortal41a", "Mortal-4.1-避四 分析", "f_ai_mortal41a", MORTAL_41A),
    ("ai_mortal41b", "Mortal-4.1-平衡 分析", "f_ai_mortal41b", MORTAL_41B),
    ("ai_mortal41c", "Mortal-4.1-争一 分析", "f_ai_mortal41c", MORTAL_41C),
]
CHOICE_KEYS = [c[0] for c in CHOICES]
CHOICE_NAMES = dict((c[0], c[1]) for c in CHOICES)
CHOICE_MODELS = dict((c[0], c[3]) for c in CHOICES)            # key -> 规范模型名
CHOICE_KEY_BY_MODEL = dict((c[3], c[0]) for c in CHOICES)      # 规范模型名 -> key

# 第零类的四种互斥检索方案（用户 m04556 ③）
MODES = [
    ("any", "任意AI决策"),
    ("naga", "NAGA决策"),
    ("mortal", "Mortal决策"),
    ("multi", "同时具有"),
]
MODE_KEYS = [m[0] for m in MODES]
MODE_NAMES = dict(MODES)


def normalize(raw):
    """原始模型名 -> 规范名（认不出来时原样返回）。"""
    name = str(raw or "").strip()
    if not name:
        return ""
    if name in ALIASES:
        return ALIASES[name]
    if _VERSION_RE.match(name):
        m = re.match(r"^(\d+(?:\.\d+)?)([a-z]?)$", name, re.I)
        style = _MORTAL_STYLE_BY_CODE.get((m.group(2) or "").lower())
        if style:
            return "%s-%s-%s" % (SERIES_MORTAL, m.group(1), style)
        return "%s-%s-平衡" % (SERIES_MORTAL, name)
    return name


def series_of(name):
    """规范名 -> 系列名（用户 m04556 ③：第一个短横线之前的字符串）。"""
    return str(name or "").split("-")[0]


def model_list(types):
    """``naga_types`` = ``{"0": "ニシキ", "1": "カガシ", "2": "4.1b"}`` ->
    ``[{"index", "raw", "name", "series"}, ...]``（按报告里的下标升序）。

    index = 报告里的模型下标（「每模型」字段的外层下标就是它）；
    name = 规范名；series = 系列名。
    """
    out = []
    for key, raw in (types or {}).items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            continue
        name = normalize(raw)
        if not name:
            continue
        out.append({"index": idx, "raw": str(raw), "name": name, "series": series_of(name)})
    out.sort(key=lambda m: m["index"])
    return out


def names_of(models):
    """模型规范名列表（按报告下标顺序）。"""
    return [m["name"] for m in (models or [])]


def series_of_models(models):
    """模型系列名列表（去重，按首次出现顺序）。"""
    out = []
    for m in (models or []):
        if m["series"] not in out:
            out.append(m["series"])
    return out


def value_map(models):
    """第零类特征 key -> 是否含该模型（布尔；用户 m04556 ②）。"""
    have = set(names_of(models))
    return dict((key, model in have) for key, _name, _col, model in CHOICES)