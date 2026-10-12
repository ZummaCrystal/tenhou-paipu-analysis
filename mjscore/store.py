# -*- coding: utf-8 -*-
"""SQLite 打点数据库：建库 / 写库 / 检索 / 导出。

表结构（star schema，压缩维度 = 40 个特征：5 个第零类 + 17 个第一类 + 17 个第二类 + 1 个第三类；
第零类 5 项 = **这一帧**有没有对应 AI 模型的决策概率表（按帧判定：这一帧做决策的那名玩家带该模型的数据
才是「是」；第 52 轮 / 用户 m04556 ②、第 59 轮 / m05937 ②、第 60 轮 / m06323 ① / m06560。模型名 =
NAGA-平衡 / NAGA-超副露 / Mortal-4.1-避四 / Mortal-4.1-平衡 / Mortal-4.1-争一，列 f_ai_balance /
f_ai_superhuro / f_ai_mortal41a / f_ai_mortal41b / f_ai_mortal41c；另有辅助列 ai_models / ai_series
供按系列聚合），天凤 / NAGA / Mortal 报告可混编进同一个库）：
    meta          库级元信息（schema 版本、软件版本、工具、口径说明、特征注册表）
    feature_def   40 个特征的注册表（key / 中文名 / 类型 / 值域 / 列名）
    source        每个已入库牌谱（特征码 / 原始文件路径 / 局数 / 打点数）
    round         每个已入库的局（局况 / 本场 / 供托 / 起家 / 分数）
    frame         **一行 = 一个打点帧**（kind=draw 非自摸的摸牌帧 / kind=chi|pon 吃碰后等待出牌的帧 /
                  kind=wait 鸣牌响应帧 —— 别人打出牌之后、**可能鸣牌**的那一家各一行，用户 m07289）：
                  定位列 + 40 个特征列（打点维度）+ ai_models / ai_series 辅助列
    frame_full   惰性维度：后续新增特征时按 key 逐列追加，无需改表结构（--full 时写原始数据）
检索：把用户填的特征条件编译成 WHERE 子句（枚举精确匹配 / 整数区间 / 比较），
      全部条件用 AND 组合（readme：「检索满足全部条件的帧」）；第零类特征不填取值，
      改用四种互斥方案（任意AI决策 / NAGA决策 / Mortal决策 / 同时具有，见 compile_ai()）；
      第三类特征「等待鸣牌」也不填取值，改用一个**必选**单选「出牌 / 鸣牌响应」（见 compile_wait()，
      用户 m07289 的补充要求）；这些方案与第一、二类条件都是 AND（用户 m04556 ③ / m07289）。
"""

import json
import os
import re
import sqlite3

from . import ai_models, feats, mjlog
from . import __version__ as APP_VERSION   # 软件本体版本，写进 meta.app_version

SCHEMA_VERSION = 10  # 10：第一类「等待鸣牌」改列**第三类特征**；打点行改为 kind='wait' 的「鸣牌响应」帧
                     #    （判据 = 可能被他家鸣牌〔吃 / 碰 / 杠，含食替禁止〕，每个可能鸣牌的家各一行；
                     #    用户 m07289）—— 行集与特征分类都变了 ⇒ schema 9 及以前的库不再支持（第 63 轮 / v1.3.0）；
                     # 9：新增第一类特征「等待鸣牌」列 f_meld_wait（用户 m06832）+ 打点行新增 kind='wait'
                     #    等待鸣牌决策帧（除出牌者外三家各一行，用户 m06801）—— 行数语义变了 ⇒
                     #    schema 8 及以前的库不再支持（第 62 轮 / v1.2.0）；
                     # 8：第零类 5 列改为「按帧判定」（列名与值域不变、语义变了 ⇒ schema 7 及以前的库不再支持，
                     #    第 60 轮 / v1.1.0，用户 m06323 ①）；
                     # 7：第零类 5 列（新增 f_ai_mortal41a / f_ai_mortal41c，`第 59 轮` / v1.0.0，用户 m05937 ②）；
                     # 6：第零类 3 列 f_ai_*（原第一类「NAGA决策」列 f_naga 改名移入）+ 辅助列
                     #    ai_models / ai_series（第 52 轮 / v0.3.0；v0.2.x 及以前的库不再支持，用户 m04556 ②）；
                     # 5：新增第一类特征「立直家（他家）一发巡」列 f_ippatsu（第 36 轮 / v0.2.0）；
                     # 4：新增第一类特征「NAGA决策」列 f_naga + 天凤/NAGA 混编（第 29 轮）；
                     # 3：新增 17 个第二类特征列（s_*，第 21 轮）；2 = frame.kind + 巡目按出牌计（第 13 轮）

META_KEYS = ("schema_version", "app_version", "created_at", "updated_at", "tool", "record_count",
             "source_count", "round_count", "full", "noted")

TABLES = [
    """CREATE TABLE IF NOT EXISTS meta (
        k TEXT PRIMARY KEY, v TEXT)""",
    """CREATE TABLE IF NOT EXISTS feature_def (
        key TEXT PRIMARY KEY, name TEXT, kind TEXT, col TEXT, values_json TEXT)""",
    """CREATE TABLE IF NOT EXISTS source (
        log_id TEXT PRIMARY KEY, path TEXT, rounds INTEGER, annotations INTEGER,
        tool TEXT, added_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS round (
        log_id TEXT, round_index INTEGER, kyoku INTEGER, honba INTEGER, kyotaku INTEGER,
        oya INTEGER, joukyoku TEXT, scores_json TEXT, events INTEGER,
        PRIMARY KEY (log_id, round_index))""",
    """CREATE TABLE IF NOT EXISTS frame (
        idx INTEGER PRIMARY KEY,
        log_id TEXT NOT NULL, url TEXT, round_index INTEGER NOT NULL, ev_index INTEGER NOT NULL,
        frame_index INTEGER NOT NULL, seat INTEGER NOT NULL, round INTEGER, honba INTEGER,
        kyotaku_raw INTEGER, kyotaku_total INTEGER, score INTEGER, oya INTEGER, dealer INTEGER,
        joukyoku TEXT, wind TEXT, junme INTEGER, rank INTEGER, drawn INTEGER, hand_size INTEGER,
        kind TEXT, ai_models TEXT, ai_series TEXT,
        %s,
        label TEXT, log_path TEXT, tool TEXT, added_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS frame_full (
        frame_idx INTEGER, key TEXT, value TEXT, PRIMARY KEY (frame_idx, key))""",
]


FEATURE_DDL_TYPES = {"int": "INTEGER", "float": "REAL", "enum": "TEXT"}


def _feature_columns_ddl():
    """frame 表的特征列声明（名字、顺序 = feats.FEATURES 注册表顺序；第 21 轮起含 17 个第二类特征）。"""
    return ", ".join("%s %s" % (f["col"], FEATURE_DDL_TYPES.get(f["kind"], "TEXT"))
                     for f in feats.FEATURES)


# 只有 frame 的 DDL 留了 %s 占位（特征列），其余照原样
TABLES = [sql % _feature_columns_ddl() if "%s" in sql else sql for sql in TABLES]

INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS frame_uniq ON frame (log_id, round_index, ev_index, seat)",
    "CREATE INDEX IF NOT EXISTS frame_dims ON frame (f_joukyoku, f_junme, f_kyotaku, f_rank, f_oyako)",
    "CREATE INDEX IF NOT EXISTS frame_flags ON frame (f_riichi_self, f_meld_self, f_meld_self_n)",
    "CREATE INDEX IF NOT EXISTS frame_others ON frame (f_riichi_others_n, f_meld_others_n, f_meld2_others_n, f_meld3_others_n)",
    "CREATE INDEX IF NOT EXISTS frame_oya ON frame (f_oya_riichi, f_oya_meld, f_oya_meld_n)",
    "CREATE INDEX IF NOT EXISTS frame_ai ON frame (f_ai_balance, f_ai_superhuro, f_ai_mortal41a, f_ai_mortal41b, f_ai_mortal41c)",
    # 第三类特征「等待鸣牌」（用户 m07289）：检索页「出牌 / 鸣牌响应」单选按它筛选
    "CREATE INDEX IF NOT EXISTS frame_wait ON frame (f_meld_wait)",
]

FRAME_FACT_COLS = ["log_id", "url", "round_index", "ev_index", "frame_index", "seat", "round",
                   "honba", "kyotaku_raw", "kyotaku_total", "score", "oya", "dealer", "joukyoku",
                   "wind", "junme", "rank", "drawn", "hand_size", "kind",
                   # 第零类的辅助列（用户 m04556 ③）：AI 模型规范名 / 系列名
                   "ai_models", "ai_series"]

DOUKOU = ("打点对象 = 决策帧，分两类（第三类特征「等待鸣牌」= 出牌/否、鸣牌响应/是）："
          "① 出牌帧 —— 非自摸的摸牌帧（kind=draw）+ 吃/碰之后等待出牌的帧（kind=chi/pon）；"
          "② 鸣牌响应帧 —— 别人打出牌之后、**可能鸣牌**的那一家各一行（kind=wait，用户 m07289 ①②）："
          "判据是「可能被他家鸣牌」而与牌谱里实际有没有鸣牌无关（碰 / 大明杠 = 同种 ≥2 张；吃 = 下家能凑"
          "顺子且吃后还剩至少一张可打的牌，即食替禁止；立直家不能鸣牌）。"
          "立直宣言按「打出立直宣言牌」这一次出牌处理，立直 / 杠的宣言帧、暗杠 / 加杠帧、自摸和了帧一律不出帧"
          "（用户 m07289 ③）；加杠/大明杠/暗杠不单独出帧（杠后的岭上摸牌帧就是 kind=draw）。"
          "视角：该家本人 = 当前决策者。巡目 = 该家本局第 N 次出牌（打牌 +1；暗杠/加杠视为出牌 +1；"
          "吃/碰/大明杠不算）+ 1；鸣牌响应帧的巡目 = 该家下一次出牌会是第几巡（用户 m06832）。"
          "副露 = 吃/碰/加杠/大明杠/暗杠 的组数（拔北不计）；供托 = 立直棒×1000 + 本场×300；"
          "顺位同分时按自风 東→南→西→北 排先；该家自己就是亲家时，亲家（他家）三项记 否/否/0。")
FULL_NOTE = ("--full（同时写入原始数据）：勾选时除了 40 个特征值，还把该帧的原始数据"
             "（手牌 / 副露 / 宝牌指示牌 / 分数 / 牌谱路径）写进 frame_full 表 —— "
             "以后新增特征时可以只按这些原始数据重算，不必重新解析 XML；"
"不勾选时只写 40 个特征值（库更小、写库略快），但后续新增特征只能重新分析全部牌谱。")


# ------------------------------------------------------------------ 连接与建库
def connect(db_path, create=True):
    if create:
        d = os.path.dirname(os.path.abspath(db_path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
    elif not os.path.isfile(os.path.abspath(db_path)):
        # create=False 时不顺手建库：检索/浏览不该凭空产生空库
        raise FileNotFoundError("数据库文件不存在：%s" % os.path.abspath(db_path))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        check_version(conn, db_path)
    except Exception:
        # 校验失败就要把连接关掉：否则 Windows 上这个 sqlite 文件会被一直占着，
        # 之后既删不掉（WinError 32）也覆盖不了。
        conn.close()
        raise
    return conn


def check_version(conn, db_path=""):
    """校验这个库能不能被当前软件使用。

    ① 结构版本（meta.schema_version）必须等于 SCHEMA_VERSION，否则提示重建；
    ② 软件版本（meta.app_version，第 22 轮起）：记录生成该库的软件本体版本。
       有记录就必须与当前 __version__ 一致，否则拒绝使用（格式可能已变）；
       没有记录（第 22 轮之前生成的库）按兼容处理，返回 False。

    返回 True = 有版本记录且匹配；False = 全新库 / 没有版本记录的库。
    """
    try:
        row = conn.execute("SELECT v FROM meta WHERE k = 'schema_version'").fetchone()
    except sqlite3.Error:
        return False          # 全新库（还没有 meta 表）
    if row is None:
        return False
    ver = int(row["v"])
    if ver != SCHEMA_VERSION:
        raise ValueError(
            "数据库版本过低（库的结构版本 %d，当前软件需要 %d；v0.2.x 及以前的库在 v0.3.0 起不再支持），"
            "请删除后重新分析：python analyze.py <牌谱路径> --delete-db <库名>（%s）"
            % (ver, SCHEMA_VERSION, os.path.abspath(db_path)))
    row = conn.execute("SELECT v FROM meta WHERE k = 'app_version'").fetchone()
    if row is None or not str(row["v"]).strip():
        return False          # 第 22 轮之前生成的库：没有软件版本记录
    recorded = str(row["v"]).strip()
    if recorded != APP_VERSION:
        raise ValueError(
            "数据库版本不匹配（库由软件版本 %s 生成，当前软件版本 %s），"
            "请删除后重新分析：python analyze.py <牌谱路径> --delete-db <库名>（%s）"
            % (recorded, APP_VERSION, os.path.abspath(db_path)))
    return True


def create_schema(conn):
    cur = conn.cursor()
    for sql in TABLES:
        cur.execute(sql)
    for sql in INDEXES:
        cur.execute(sql)
    conn.commit()


def set_meta(conn, k, v):
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, str(v)))


def get_meta(conn):
    return {r["k"]: r["v"] for r in conn.execute("SELECT k, v FROM meta")}


def app_version_of(conn):
    """该库记录的软件版本（没有记录时返回空串）。"""
    return str(get_meta(conn).get("app_version") or "")


def source_ids(conn):
    """已入库的全部牌谱特征码（扩充数据库时用来跳过重复牌谱）。"""
    return {r["log_id"] for r in conn.execute("SELECT log_id FROM source")}


def totals(conn):
    """库内的总行数（frame / source / round），扩充后重新统计用。"""
    cur = conn.cursor()
    return {"frames": cur.execute("SELECT COUNT(*) c FROM frame").fetchone()["c"],
            "sources": cur.execute("SELECT COUNT(*) c FROM source").fetchone()["c"],
            "rounds": cur.execute("SELECT COUNT(*) c FROM round").fetchone()["c"]}


def write_feature_defs(conn):
    for f in feats.FEATURES:
        conn.execute("INSERT OR REPLACE INTO feature_def (key, name, kind, col, values_json) VALUES (?,?,?,?,?)",
                     (f["key"], f["name"], f["kind"], f["col"], json.dumps(f.get("values"), ensure_ascii=False)))
    conn.commit()


def open_db(db_path):
    conn = connect(db_path)
    create_schema(conn)
    return conn


# ------------------------------------------------------------------ 写库
def _json(v):
    return json.dumps(v, ensure_ascii=False)


def insert_rounds(conn, game, tool):
    log_id = game["log_id"]
    for ri, rnd in enumerate(game["rounds"]):
        init = rnd["init"]
        conn.execute("INSERT OR REPLACE INTO round (log_id, round_index, kyoku, honba, kyotaku, oya,"
                     " joukyoku, scores_json, events) VALUES (?,?,?,?,?,?,?,?,?)",
                     (log_id, ri, init["round"], init["combo"], init["kyotaku"], init["oya"],
                      mjlog.joukyoku_label(init["round"]), _json(init["scores"]), len(rnd["events"])))


FRAME_INSERT = ("INSERT OR REPLACE INTO frame ("
                + ", ".join(FRAME_FACT_COLS + [f["col"] for f in feats.FEATURES]
                            + ["label", "log_path", "tool", "added_at"])
                + ") VALUES (" + ", ".join(["?"] * (len(FRAME_FACT_COLS) + len(feats.FEATURES) + 4)) + ")")


def insert_records(conn, records, tool="", log_path="", added_at="", full=False):
    n = 0
    for rec in records:
        vals = [rec.get(c) for c in FRAME_FACT_COLS]
        # 第二类特征（第 21 轮）与第一类一起写入；老 fixture 缺列时记 NULL 而不是 KeyError
        vals += [rec["feats"].get(f["key"]) for f in feats.FEATURES]
        vals += [feats.row_label(rec), log_path or rec.get("path", ""), tool, added_at]
        cur = conn.execute(FRAME_INSERT, vals)
        idx = cur.lastrowid
        n += 1
        if full:
            for key, value in (("tiles", rec.get("tiles")), ("melds", rec.get("melds")),
                               ("dora", rec.get("dora")), ("scores", rec.get("scores")),
                               ("names", rec.get("names"))):
                if value is not None:
                    conn.execute("INSERT OR REPLACE INTO frame_full (frame_idx, key, value) VALUES (?,?,?)",
                                 (idx, key, _json(value)))
    return n


def insert_source(conn, game, annotations, tool, added_at):
    conn.execute("INSERT OR REPLACE INTO source (log_id, path, rounds, annotations, tool, added_at)"
                 " VALUES (?,?,?,?,?,?)",
                 (game["log_id"], game.get("path", ""), len(game["rounds"]), annotations, tool, added_at))


def prune_frame_full(conn):
    """清掉 frame_full 里指向已不存在帧的原始数据。

    frame 的唯一键是 (log_id, round_index, ev_index, seat)：重新分析同一个牌谱时
    `INSERT OR REPLACE` 会先删旧行、再插入**新的 idx**；frame_full 是按 frame_idx 存的，
    不清就会留下永远取不到的孤儿行（--full 重分析 N 次就多 N 份垃圾，实测 1 次多 13930 行）。
    返回删除的行数。
    """
    cur = conn.execute("DELETE FROM frame_full WHERE frame_idx NOT IN (SELECT idx FROM frame)")
    return cur.rowcount


# ------------------------------------------------------------------ 检索
NUM_RE = re.compile(r"^\s*(-?\d+)\s*$")
RANGE_RE = re.compile(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*$")
CMP_RE = re.compile(r"^\s*(<=|>=|<|>)\s*(-?\d+)\s*$")
# 实数（kind=float 的 12 个期望特征）：0 / 0.5 / -1.25 / .5 / 3.
FLOAT_RE = re.compile(r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
FRANGE_RE = re.compile(r"^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*-\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
FCMP_RE = re.compile(r"^\s*(<=|>=|<|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$")


def parse_cond(feature, expr):
    """把用户的检索条件文本编译成 (sql, params)。

    支持：`3`（精确）、`1,2,3`（多值）、`1-3`（区间）、`>=3` / `<=2` / `>1` / `<4`（比较）；
    实数特征（kind=float）同样支持 `0.5` / `0,1.5` / `0-1.5` / `>=2.5`。
    """
    if expr is None or str(expr).strip() == "":
        raise ValueError("「%s」的条件没有填写" % feature["name"])
    text = str(expr).strip()
    col = feature["col"]
    if feature["kind"] == "int":
        m = NUM_RE.match(text)
        if m:
            return "%s = ?" % col, [int(m.group(1))]
        m = RANGE_RE.match(text)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return "%s BETWEEN ? AND ?" % col, [lo, hi]
        m = CMP_RE.match(text)
        if m:
            return "%s %s ?" % (col, m.group(1)), [int(m.group(2))]
        parts = [p.strip() for p in text.split(",") if p.strip() != ""]
        if parts and all(NUM_RE.match(p) for p in parts):
            return "%s IN (%s)" % (col, ", ".join(["?"] * len(parts))), [int(p) for p in parts]
        raise ValueError("「%s」的可接受条件：整数 / 区间(1-3) / 列表(1,2,3) / 比较(>=3)，收到「%s」"
                         % (feature["name"], text))
    if feature["kind"] == "float":
        m = FLOAT_RE.match(text)
        if m:
            return "%s = ?" % col, [float(m.group(1))]
        m = FRANGE_RE.match(text)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return "%s BETWEEN ? AND ?" % col, [lo, hi]
        m = FCMP_RE.match(text)
        if m:
            return "%s %s ?" % (col, m.group(1)), [float(m.group(2))]
        parts = [p.strip() for p in text.split(",") if p.strip() != ""]
        if parts and all(FLOAT_RE.match(p) for p in parts):
            return "%s IN (%s)" % (col, ", ".join(["?"] * len(parts))), [float(p) for p in parts]
        raise ValueError("「%s」的可接受条件：实数 / 区间(0-1.5) / 列表(0,1,2.5) / 比较(>=3)，收到「%s」"
                         % (feature["name"], text))
    # 枚举：精确或多值
    allowed = feature.get("values") or []
    parts = [p.strip() for p in text.split(",") if p.strip() != ""]
    if not parts:
        raise ValueError("「%s」的条件为空" % feature["name"])
    for p in parts:
        if allowed and p not in allowed:
            raise ValueError("「%s」不接受「%s」，可选值：%s"
                             % (feature["name"], p, " / ".join(allowed)))
    if len(parts) == 1:
        return "%s = ?" % col, [parts[0]]
    return "%s IN (%s)" % (col, ", ".join(["?"] * len(parts))), parts


RESULT_COLS = ("idx", "log_id", "url", "round_index", "ev_index", "frame_index", "seat", "joukyoku",
               "honba", "wind", "junme", "score", "rank", "kyotaku_total", "kind", "label", "log_path")


# ---------------------------------------------------- 第三类特征：出牌 / 鸣牌响应（用户 m07289 的补充要求）
# 检索页新增一个**必选**单选：「出牌」（f_meld_wait = 否）/「鸣牌响应」（f_meld_wait = 是），
# 与第零类方案、第一/二类特征条件同时满足（AND）；缺省 = 「出牌」。
WAIT_OUT = "出牌"
WAIT_CALL = "鸣牌响应"
WAIT_MODES = (WAIT_OUT, WAIT_CALL)


def compile_wait(wait):
    """「出牌 / 鸣牌响应」-> (where_sql, params, 显示名)。缺省 / 空 = 「出牌」。"""
    w = (wait or "").strip() or WAIT_OUT
    col = feats.BY_KEY[feats.THIRD_KEYS[0]]["col"]
    if w in (WAIT_OUT, feats.NO):
        return "%s = ?" % col, [feats.NO], WAIT_OUT
    if w in (WAIT_CALL, feats.YES):
        return "%s = ?" % col, [feats.YES], WAIT_CALL
    raise ValueError("未知的局面选项（只支持「%s」/「%s」）：%s" % (WAIT_OUT, WAIT_CALL, w))


def compile_ai(ai):
    """第零类特征的检索方案 -> (where_sql, params, 用到的方案名)。

    方案（用户 m04556 ③，四种互斥）：
        any     任意AI决策    —— 牌谱里有任意一种 AI 模型的分析结果（ai_models 非空）
        naga    NAGA决策      —— 含任意一种 NAGA 系列模型（ai_series 里有 NAGA）
        mortal  Mortal决策    —— 含任意一种 Mortal 系列模型（ai_series 里有 Mortal）
        multi   同时具有      —— 勾选的第零类特征必须全为「是」（picks 为空 = 不限）
    返回 (None, [], None) 表示不筛选。
    """
    if not ai:
        return None, [], None
    mode = (ai.get("mode") or "").strip()
    if not mode:
        return None, [], None
    if mode not in ai_models.MODE_KEYS:
        raise ValueError("未知的第零类检索方案：%s" % mode)
    name = ai_models.MODE_NAMES[mode]      # MODE_NAMES 是 {key: 中文名} 的字典（第 52 轮）
    if mode == "any":
        return "ai_models IS NOT NULL AND ai_models <> ''", [], name
    if mode == "naga":
        return "ai_series LIKE ?", ["%NAGA%"], name
    if mode == "mortal":
        return "ai_series LIKE ?", ["%Mortal%"], name
    picks = [p for p in (ai.get("picks") or []) if p]
    if not picks:
        return None, [], None        # 「同时具有」但一个都没勾 = 不限（保持旧行为）
    clauses, params = [], []
    for key in picks:
        feature = feats.BY_KEY.get(key)
        if feature is None or key not in feats.AI_KEYS:
            raise ValueError("未知的第零类特征：%s" % key)
        clauses.append("%s = ?" % feature["col"])
        params.append(feats.YES)
    return " AND ".join(clauses), params, name


def compile_query(conds, ai=None, wait=None):
    """conds = [{'key': 'kyotaku', 'expr': '1000'}, ...]（第一/二类特征条件）
    + ai = 第零类方案（见 compile_ai）+ wait = 第三类「出牌 / 鸣牌响应」（见 compile_wait）
    -> (where_sql, params, 用到的特征名)。

    三类条件用 AND 组合；只有第零类方案（不带第一/二类条件）也是合法检索（用户 m04556 ③）；
    wait 缺省 = 「出牌」（用户 m07289 的补充要求），但 wait 单独一项不算「有筛选条件」。
    """
    conds = conds or []
    clauses, params, used = [], [], []
    if not conds and not ai:
        raise ValueError("请至少添加一条牌谱特征条件或选择一个第零类检索方案")
    for c in conds:
        key = c.get("key")
        feature = feats.BY_KEY.get(key)
        if feature is None:
            raise ValueError("未知的牌谱特征：%s" % key)
        if key in feats.AI_KEYS:
            raise ValueError("第零类特征不走「特征词条」方式，请改用第零类检索方案：%s" % feature["name"])
        if key in feats.THIRD_KEYS:
            raise ValueError("第三类特征（%s）不走「特征词条」方式，请改用「出牌 / 鸣牌响应」单选"
                             % feature["name"])
        sql, ps = parse_cond(feature, c.get("expr"))
        clauses.append(sql)
        params.extend(ps)
        used.append(feature["name"])
    ai_sql, ai_params, ai_name = compile_ai(ai)
    if ai_sql:
        clauses.append(ai_sql)
        params.extend(ai_params)
        used.append(ai_name)
    wait_sql, wait_params, wait_name = compile_wait(wait)
    if wait_sql:
        clauses.append(wait_sql)
        params.extend(wait_params)
        used.append(wait_name)
    return " AND ".join(clauses), params, used


def query(conn, conds, limit=200, offset=0, order="log_id, round_index, ev_index, seat", ai=None, wait=None):
    where, params, used = compile_query(conds, ai, wait)
    total = conn.execute("SELECT COUNT(*) c FROM frame WHERE " + where, params).fetchone()["c"]
    rows = conn.execute("SELECT %s FROM frame WHERE %s ORDER BY %s LIMIT ? OFFSET ?"
                        % (", ".join(RESULT_COLS), where, order),
                        params + [limit, offset]).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "used": used,
            "rows": [dict(r) for r in rows]}


def query_detail(conn, idx):
    row = conn.execute("SELECT * FROM frame WHERE idx = ?", (idx,)).fetchone()
    if row is None:
        raise ValueError("没有 idx = %s 的打点行" % idx)
    d = dict(row)
    d["feats"] = {f["key"]: d[f["col"]] for f in feats.FEATURES}
    d["full"] = {r["key"]: json.loads(r["value"])
                 for r in conn.execute("SELECT key, value FROM frame_full WHERE frame_idx = ?", (idx,))}
    return d


def frame_feats(conn, log_id, round_index, frame_index, seat=None):
    """按 (log_id, round_index, frame_index[, seat]) 取一帧的全部 40 个特征值。

    前端「当前帧特征面板」用：Python 的 frame_index = ev_index + 1，
    与 web/js/replay.js buildFrames() 的帧号同口径，所以前端可直接把播放位置传进来。
    库里没有这一帧时返回 None（例如手动播放到的帧不是打点帧）。
    """
    if log_id is None or round_index is None or frame_index is None:
        raise ValueError("需要 log_id / round_index / frame_index")
    sql = "SELECT idx FROM frame WHERE log_id=? AND round_index=? AND frame_index=?"
    params = [str(log_id), int(round_index), int(frame_index)]
    if seat is not None and str(seat) != "":
        sql += " AND seat=?"
        params.append(int(seat))
    sql += " LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return query_detail(conn, int(row["idx"]))


def round_frames(conn, log_id, round_index):
    rows = conn.execute("SELECT idx, ev_index, frame_index, seat, junme, kind, label FROM frame"
                        " WHERE log_id=? AND round_index=? ORDER BY ev_index", (log_id, round_index)).fetchall()
    return [dict(r) for r in rows]


def export_json(conn, limit=None):
    out = {"meta": get_meta(conn), "features": feats.FEATURES,
           "source": [dict(r) for r in conn.execute("SELECT * FROM source ORDER BY log_id")],
           "frames": []}
    sql = "SELECT * FROM frame ORDER BY log_id, round_index, ev_index, seat"
    if limit:
        sql += " LIMIT %d" % int(limit)
    for r in conn.execute(sql):
        d = dict(r)
        d["feats"] = {f["key"]: d[f["col"]] for f in feats.FEATURES}
        out["frames"].append(d)
    return out


def list_feature_values(conn, key):
    f = feats.BY_KEY.get(key)
    if f is None:
        raise ValueError("未知的牌谱特征：%s" % key)
    rows = conn.execute("SELECT %s v, COUNT(*) c FROM frame GROUP BY %s ORDER BY v" % (f["col"], f["col"])).fetchall()
    return [{"value": r["v"], "count": r["c"]} for r in rows]