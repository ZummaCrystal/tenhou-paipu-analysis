# -*- coding: utf-8 -*-
r"""mjscore 正式测试。

覆盖：
  1. 解析口径（牌谱数 / 局数 / 帧数 / 逐帧牌张不变量）
  2. 打点口径（非自摸摸牌帧 + 吃/碰副露帧、巡目按出牌计、33 个特征 = 16 第一类 + 17 第二类、条目名格式）
  3. 写库 + 检索（analyze / query / 条件错误提示 / 特征值域）
  4. 双工具交叉校验（node 与 python 打点全字段逐项一致 —— readme 硬约束）
  5. 本地服务接口（server.py 的 GET/POST 路由与错误码）
  6. 第 21 轮：17 个第二类特征、帧特征接口、分析与下载进度、下载模块（离线）
  7. 第 22 轮：软件版本 v0.1.0（meta.app_version + 库版本校验）、扩充现有数据库（按特征码跳过已有牌谱）

运行：
  & 'D:\coding\anaconda3\envs\py314_null\python.exe' test\mjscore_test.py
"""
import glob
import json
import os
import re
import time
import shutil
import socket
import sqlite3
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mjscore import cli, download, feats, mjlog, nodeharness, replay, server, store  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OK = [0]
BAD = [0]
MSGS = []


def check(cond, label):
    if cond:
        OK[0] += 1
        print("  OK   %s" % label)
    else:
        BAD[0] += 1
        print("  FAIL %s" % label)
    return bool(cond)


def eq(got, want, label):
    return check(got == want, "%s（got %r / want %r）" % (label, got, want))


def note(counter, label, msg):
    """聚合式断言：counter 是 [n, 'first msg']，n 必须为 0。"""
    if counter[0] == 0:
        check(True, "%s（全 0 违规）" % label)
    else:
        check(False, "%s：%d 处不符，首例 %s" % (label, counter[0], counter[1]))


DATA = os.path.join(ROOT, "data")
# 牌谱默认下载到 data/paipu/<时间戳>/ 下，所以语料要递归找；本文件只取固定的 5 个
# 基础牌谱（按特征码 = 文件名去扩展名），保证下面的行数 / 局数断言与目录布局无关。
SUBSET_IDS = ("2026082919gm-00a9-0000-4e40cd3e", "2026082920gm-00a9-0000-5db954e6",
              "2026082921gm-00a9-0000-d2e544e6", "2026083020gm-00a9-0000-e9ce1efe",
              "2026083021gm-00a9-0000-d0810acf")


def corpus():
    """data 下（含 data/paipu/<子目录>/）的全部牌谱 + 可选的 data_extra。"""
    out = sorted(glob.glob(os.path.join(DATA, "**", "*.xml"), recursive=True))
    out += sorted(glob.glob(os.path.join(ROOT, "data_extra", "*.xml")))
    return out


FILES = [p for p in corpus() if mjlog.log_id_of(p) in SUBSET_IDS]
GAMES = [mjlog.game_from_file(p) for p in FILES]
LABEL_RE = re.compile(
    r"^(\d{10}gm-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8})"
    r" (東|南|西|北)(一|二|三|四)局 (\d+)本場 (\d+)巡目 (東|南|西|北)家$")

# 沙箱只允许在项目目录内创建文件，SQLite 的临时库也放在项目里
TMP = os.path.join(ROOT, "test", "_tmp")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
print("临时目录：%s" % TMP)

# ------------------------------------------------------------------ 1
print("=== 1. 解析口径 ===")
eq(len(FILES), 5, "基础牌谱文件数（按特征码选取 5 个，与存放目录无关）")
eq(sum(len(g["rounds"]) for g in GAMES), 58, "总对局数")
eq(sum(len(r["events"]) for g in GAMES for r in g["rounds"]), 5766, "事件帧总数")
for p, g in zip(FILES, GAMES):
    eq(g["log_id"], mjlog.log_id_of(p), "log_id 还原：%s" % os.path.basename(p))
errs_all = []
n_all = 0
for g in GAMES:
    for ri in range(len(g["rounds"])):
        errs, n = replay.check_invariants(g, ri)
        errs_all.extend(errs)
        n_all += n
eq(n_all, 5766, "逐帧校验覆盖帧数")
eq(len(errs_all), 0, "逐帧牌张不变量错误数（首例：%s）" % (errs_all[0] if errs_all else "-"))

# ------------------------------------------------------------------ 2
print("=== 2. 打点口径 ===")
ALL = []
for g in GAMES:
    ALL.extend(feats.records_for_game(g))
eq(len(ALL), 2786, "打点行总数（摸牌帧 2679 + 吃碰副露帧 107）")
KINDS = {}
for _r in ALL:
    KINDS[_r["kind"]] = KINDS.get(_r["kind"], 0) + 1
eq(KINDS, {"draw": 2679, "chi": 50, "pon": 57}, "打点行 kind 分布")
per_file = sorted(len(feats.records_for_game(g)) for g in GAMES)
eq(per_file, [364, 530, 531, 576, 785], "各牌谱打点行数（升序）")

# --- 2c. 第 21 轮：17 个第二类特征 -----------------------------------------
print("=== 2c. 第二类特征（第 21 轮） ===")
eq(len(feats.FEATURES), 33, "特征注册表 33 项（16 第一类 + 17 第二类）")
eq(len(feats.SECOND_KEYS), 17, "第二类特征 17 项")
eq([f["key"] for f in feats.FEATURES][16:], list(feats.SECOND_KEYS), "后 17 项就是第二类特征（顺序一致）")
eq(sorted(f["col"] for f in feats.FEATURES if f["col"].startswith("s_")),
   sorted("s_" + k for k in feats.SECOND_KEYS), "第二类列名 = s_<key>")
eq(sorted(set(f["kind"] for f in feats.FEATURES[16:])), ["float", "int"], "第二类特征只有 int / float")
miss_keys = [(feats.row_label(r), k) for r in ALL for k in feats.SECOND_KEYS if k not in r["feats"]]
eq(len(miss_keys), 0, "每行都带 17 个第二类特征（首例 %s）" % (miss_keys[0] if miss_keys else "-"))
nulls = [(feats.row_label(r), k) for r in ALL for k in feats.SECOND_KEYS if r["feats"][k] is None]
eq(len(nulls), 0, "第二类特征没有 None（首例 %s）" % (nulls[0] if nulls else "-"))
_badint = [(feats.row_label(r), k) for r in ALL for k in feats.SECOND_KEYS
           if feats.BY_KEY[k]["kind"] == "int"
           and (isinstance(r["feats"][k], bool) or not isinstance(r["feats"][k], int))]
eq(len(_badint), 0, "整数类第二类特征都是 int（首例 %s）" % (_badint[0] if _badint else "-"))
_noriichi = [r for r in ALL if r["feats"]["riichi_others_n"] == 0]
eq(sum(1 for r in _noriichi if r["feats"]["riichi_others_danger_suji"] != -1
       or r["feats"]["riichi_others_danger_ryanmen"] != -1), 0,
   "其他家无人立直时两个危险特征都是 -1（%d 帧）" % len(_noriichi))
eq(sum(1 for r in ALL if r["feats"]["riichi_others_n"] > 0
       and (r["feats"]["riichi_others_danger_suji"] < 0
            or r["feats"]["riichi_others_danger_ryanmen"] < 0)), 0,
   "有他家立直时两个危险特征都 >= 0")
eq(sum(1 for r in ALL if not (-1 <= r["feats"]["riichi_others_danger_suji"] <= 18)), 0, "危险筋组数量 -1..18")
eq(sum(1 for r in ALL for k in ("shanten_kokushi", "shanten_chiitoi", "shanten_mentsu")
       if not (-1 <= r["feats"][k] <= 3)), 0, "三个向听数取值 -1..3")
_open = [r for r in ALL if any(m[0] in replay.OPEN_CALLS for m in r["melds"])]
eq(len(_open) > 0, True, "样本里含吃/碰/杠（明）副露的帧 %d 个" % len(_open))
eq(sum(1 for r in _open if r["feats"]["menzen_tenpai_expect"] != 0
       or r["feats"]["menzen_tenpai_abs"] != 0), 0, "明副露帧的门清枚数项都是 0")
eq(sum(1 for r in _open if r["feats"]["riichi_ron_score"] or r["feats"]["riichi_tsumo_score"]
       or r["feats"]["damaten_ron_score"] or r["feats"]["damaten_tsumo_score"]), 0,
   "明副露帧的立直/默听打点项都是 0")
eq(sum(1 for r in ALL if r["feats"]["furo_tsumo_tenpai_abs"] < r["feats"]["furo_tsumo_tenpai_expect"] - 1e-9), 0,
   "绝对枚数 >= 期望枚数（副露自摸）")
eq(sum(1 for r in ALL if r["feats"]["menzen_tenpai_abs"] < r["feats"]["menzen_tenpai_expect"] - 1e-9), 0,
   "绝对枚数 >= 期望枚数（门清）")
eq(sum(1 for r in ALL for k in feats.SECOND_KEYS
       if feats.BY_KEY[k]["kind"] == "float" and r["feats"][k] < -1e-9), 0, "实数类第二类特征 >= 0")
_pos = [r for r in ALL if r["feats"]["furo_ron_score"] > 0]
check(len(_pos) > 0, "存在副露荣和期望打点 > 0 的帧（%d 个，例如 %s）"
      % (len(_pos), feats.row_label(_pos[0]) if _pos else "-"))
_check_second = feats.second_class.__doc__ or ""
check("17 个第二类特征" in _check_second, "second_class 文档说明 17 项")

draws = 0
tsumo = 0
for g in GAMES:
    for rnd in g["rounds"]:
        evs = rnd["events"]
        for i, ev in enumerate(evs):
            if ev["type"] != "draw":
                continue
            draws += 1
            nxt = evs[i + 1] if i + 1 < len(evs) else None
            if (nxt and nxt["type"] == "agari" and nxt["winner"] == ev["player"]
                    and nxt["fromWho"] == ev["player"]):
                tsumo += 1
eq(draws, 2701, "摸牌帧总数（含自摸和了）")
eq(tsumo, 22, "自摸和了帧数（打点排除）")
eq(draws - tsumo + 107, len(ALL), "摸牌帧 − 自摸和了 + 吃碰副露帧 = 打点行数")
chi_pon = 0
for _g in GAMES:
    for _rnd in _g["rounds"]:
        for _ev in _rnd["events"]:
            if _ev["type"] == "call" and _ev["callType"] in ("chi", "pon"):
                chi_pon += 1
eq(chi_pon, 107, "吃/碰副露帧数（chi 50 + pon 57）")

# --- 2b. 第 13 轮：副露帧 + 巡目按出牌计 -----------------------------------
print("=== 2b. 副露帧 / 巡目口径 ===")
expect = {}
for _g in GAMES:
    for _ri in range(len(_g["rounds"])):
        for _i, _ev, _st in replay.iter_events(_g, _ri):
            if _ev["type"] == "draw":
                expect[(_g["log_id"], _ri, _i)] = _st["players"][_ev["player"]]["turns"] + 1
            elif _ev["type"] == "call" and _ev["callType"] in ("chi", "pon"):
                expect[(_g["log_id"], _ri, _i)] = _st["players"][_ev["player"]]["turns"] + 1
eq(len(expect), draws + 107, "独立重算表 = 摸牌帧 %d + 吃碰帧 107" % draws)
miss = [r for r in ALL
        if expect.get((r["log_id"], r["round_index"], r["ev_index"])) != r["junme"]]
eq(len(miss), 0, "巡目独立重算全部一致（首例 %s）"
   % (feats.row_label(miss[0]) if miss else "-"))

# turns 增量语义：discard/暗杠/加杠 +1；draw/吃/碰/大明杠 +0
delta_bad = []
for _g in GAMES:
    for _ri in range(len(_g["rounds"])):
        _st = replay.initial_state(_g, _ri)
        for _ev in _g["rounds"][_ri]["events"]:
            _b = [_st["players"][s]["turns"] for s in range(4)]
            replay.apply_event(_st, _ev)
            _a = [_st["players"][s]["turns"] for s in range(4)]
            _w = [0, 0, 0, 0]
            if _ev["type"] == "discard" or (_ev["type"] == "call"
                                            and _ev["callType"] in ("ankan", "kakan")):
                _w[_ev["player"]] = 1
            if [_a[s] - _b[s] for s in range(4)] != _w:
                delta_bad.append((_g["log_id"][-8:], _ri, _ev.get("type"), _ev.get("callType")))
eq(len(delta_bad), 0, "turns 增量语义（首例 %s）" % (delta_bad[0] if delta_bad else "-"))

# 构造用例：本批样本里没有大明杠
_s3 = replay.clone_state(replay.initial_state(GAMES[0], 0))
_t0 = _s3["players"][2]["turns"]


def _mk(ct, p):
    return {"type": "call", "player": p, "callee": (p + 1) % 4, "rel": 1, "m": 0,
            "callType": ct, "tiles": []}


replay.apply_call(_s3, _mk("daiminkan", 1))
eq(_s3["players"][1]["turns"], _t0, "构造：大明杠不增加巡目")
replay.apply_call(_s3, _mk("ankan", 2))
eq(_s3["players"][2]["turns"], _t0 + 1, "构造：暗杠 +1 巡目")
replay.apply_call(_s3, {"type": "call", "player": 2, "callee": 3, "rel": 1, "m": 0,
                        "callType": "kakan", "tiles": [0]})
eq(_s3["players"][2]["turns"], _t0 + 2, "构造：加杠 +1 巡目")

calls = [r for r in ALL if r["kind"] != "draw"]
eq(len(calls), 107, "副露帧行数")
eq(sorted(set(r["kind"] for r in calls)), ["chi", "pon"], "副露帧 kind 只有 chi/pon")
eq(sorted(set(r["drawn"] for r in calls)), [None], "副露帧没有摸到的牌（drawn=None）")
eq(sum(1 for r in calls if r["frame_index"] != r["ev_index"] + 1), 0,
   "副露帧 frame_index = ev_index + 1")
eq(sum(1 for r in calls if not LABEL_RE.match(feats.row_label(r))), 0, "副露帧条目名格式一致")
eq(sum(1 for r in calls if not (5 <= r["hand_size"] <= 11)), 0, "副露帧手牌数 5..11")
eq(sum(1 for r in ALL if r["kind"] == "draw" and r["hand_size"] > 14), 0, "摸牌帧手牌数 <= 14")

bad = {}
def bump(key, msg):
    c = bad.setdefault(key, [0, ""])
    c[0] += 1
    if not c[1]:
        c[1] = msg
for rec in ALL:
    f = rec["feats"]
    tag = "%s 局%d 帧%d" % (rec["log_id"][-8:], rec["round_index"], rec["frame_index"])
    if not (f["joukyoku"] == rec["joukyoku"] == mjlog.joukyoku_label(rec["round"])):
        bump("joukyoku", "%s 局况 %r/%r" % (tag, f["joukyoku"], rec["joukyoku"]))
    if f["minami3"] != ("是" if rec["round"] >= 6 else "否"):
        bump("minami3", "%s round=%d minami3=%r" % (tag, rec["round"], f["minami3"]))
    if f["junme"] != rec["junme"] or f["junme"] < 1:
        bump("junme", "%s 巡目 %r/%r" % (tag, f["junme"], rec["junme"]))
    if f["kyotaku"] != rec["kyotaku_raw"] * 1000 + rec["honba"] * 300:
        bump("kyotaku", "%s 供托 %r raw=%d honba=%d" % (tag, f["kyotaku"], rec["kyotaku_raw"], rec["honba"]))
    if f["oyako"] != ("亲家" if rec["seat"] == rec["oya"] else "子家"):
        bump("oyako", "%s 自家 %r seat=%d oya=%d" % (tag, f["oyako"], rec["seat"], rec["oya"]))
    if f["rank"] != feats.calc_rank(rec["scores"], rec["oya"])[rec["seat"]]:
        bump("rank", "%s 顺位 %r scores=%r" % (tag, f["rank"], rec["scores"]))
    if rec["seat"] == rec["oya"] and (f["oya_riichi"], f["oya_meld"], f["oya_meld_n"]) != ("否", "否", 0):
        bump("oya_self", "%s 自家是亲家却 %r/%r/%r" % (tag, f["oya_riichi"], f["oya_meld"], f["oya_meld_n"]))
    open_n = sum(1 for m in rec["melds"] if m[0] in replay.OPEN_CALLS or m[0] == "ankan")
    if f["meld_self_n"] != open_n:
        bump("meld_self_n", "%s 自家副露数量 %r melds=%r" % (tag, f["meld_self_n"], rec["melds"]))
    if f["meld_self"] != ("是" if open_n > 0 else "否"):
        bump("meld_self", "%s 自家副露状态 %r" % (tag, f["meld_self"]))
    if rec["wind"] != replay.seat_wind(rec["seat"], rec["oya"]):
        bump("wind", "%s 风位 %r" % (tag, rec["wind"]))
    if rec["frame_index"] != rec["ev_index"] + 1:
        bump("frame_index", "%s frame_index %r ev_index %r" % (tag, rec["frame_index"], rec["ev_index"]))
    if rec["hand_size"] != len(rec["tiles"]) or not (1 <= rec["hand_size"] <= 14):
        bump("hand_size", "%s hand_size %r tiles %d" % (tag, rec["hand_size"], len(rec["tiles"])))
    if not rec["url"].endswith("log=%s&tw=0" % rec["log_id"]):
        bump("url", "%s url %r" % (tag, rec["url"]))
    if feats.row_label(rec) != "%s %s %d本場 %d巡目 %s家" % (
            rec["log_id"], rec["joukyoku"], rec["honba"], rec["junme"], rec["wind"]):
        bump("label", "%s 条目名 %r" % (tag, feats.row_label(rec)))
    if not LABEL_RE.match(feats.row_label(rec)):
        bump("label_re", "%s 条目名不合格式 %r" % (tag, feats.row_label(rec)))
    for spec in feats.FEATURES:
        v = f[spec["key"]]
        if spec["kind"] == "enum":
            if v not in spec["values"]:
                bump("domain:" + spec["key"], "%s %r 不在 %r" % (tag, v, spec["values"]))
        elif spec["kind"] == "float":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                bump("domain:" + spec["key"], "%s %r 不是实数" % (tag, v))
            elif not (float(spec["min"]) <= float(v) <= float(spec["max"])):
                bump("domain:" + spec["key"], "%s %r 越界 %r..%r" % (tag, v, spec["min"], spec["max"]))
        elif not (isinstance(v, int) and not isinstance(v, bool)
                  and spec["min"] <= v <= spec["max"]):
            bump("domain:" + spec["key"], "%s %r 越界 %r..%r" % (tag, v, spec["min"], spec["max"]))
for key in sorted(bad):
    note(bad[key], "口径：" + key)
print("  -- 打点抽查：%d 行，违规类别 %d 个" % (len(ALL), len(bad)))

# ------------------------------------------------------------------ 3
print("=== 3. 写库 + 检索 ===")
py_db = os.path.join(TMP, "py.sqlite")
res = cli.analyze(FILES, db=py_db, tool="python", full=True)
eq(res["ok"], True, "analyze 返回 ok")
eq(res["tool"], "python", "指定 --tool python")
eq(res["logs"], 5, "analyze 牌谱数")
eq(res["annotations"], 2786, "本次打点数")
eq(res["db_total"], 2786, "库内总行数")
eq((res.get("rows_draw"), res.get("rows_call")), (2679, 107), "analyze 返回摸牌帧/副露帧拆分")
eq(res["rounds"], 58, "库内对局数")
eq(res["warnings"], [], "analyze 无警告")
eq(len(res["detail"]), 5, "detail 每条牌谱一项")
eq(sorted(d["annotations"] for d in res["detail"]), [364, 530, 531, 576, 785], "detail 打点数")

conn = store.connect(py_db, create=False)
_m = store.get_meta(conn)
check(len(_m) >= 5, "meta 可读（%d 项）" % len(_m))
eq(store.get_meta(conn).get("schema_version"), str(store.SCHEMA_VERSION), "meta schema_version")
eq(store.SCHEMA_VERSION, 3, "结构版本 = 3（第 21 轮新增 17 个第二类特征列）")
conn.execute("UPDATE meta SET v = '1' WHERE k = 'schema_version'")
conn.commit()
try:
    store.connect(py_db, create=False)
    check(False, "旧结构版本库应拒绝打开")
except ValueError as _exc:
    check("请删除后重新分析" in str(_exc), "旧结构版本提示：%s" % _exc)
conn.execute("UPDATE meta SET v = ? WHERE k = 'schema_version'", (str(store.SCHEMA_VERSION),))
conn.commit()
eq(store.get_meta(conn).get("app_version"), store.APP_VERSION, "meta 记录生成该库的软件版本")
eq(store.app_version_of(conn), store.APP_VERSION, "app_version_of")
eq(store.APP_VERSION, "0.1.0", "软件版本 = 0.1.0（第 22 轮起写进 meta.app_version）")
conn.execute("UPDATE meta SET v = '0.0.9' WHERE k = 'app_version'")
conn.commit()
conn.close()
try:
    store.connect(py_db, create=False)
    check(False, "软件版本不匹配的库应拒绝打开")
except ValueError as _exc:
    check("数据库由软件版本" in str(_exc) and "0.0.9" in str(_exc), "软件版本不匹配提示：%s" % _exc)
_raw = sqlite3.connect(py_db)
_raw.execute("UPDATE meta SET v = ? WHERE k = 'app_version'", (store.APP_VERSION,))
_raw.commit()
_raw.close()
conn = store.connect(py_db, create=False)
_raw = sqlite3.connect(py_db)
_raw.execute("DELETE FROM meta WHERE k = 'app_version'")
_raw.commit()
_raw.close()
try:
    store.connect(py_db, create=False)
    check(True, "没有 app_version 记录的老库按兼容处理")
except ValueError as _exc:
    check(False, "没有 app_version 的老库应兼容：%s" % _exc)
_raw = sqlite3.connect(py_db)
_raw.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('app_version', ?)", (store.APP_VERSION,))
_raw.commit()
_raw.close()
conn = store.connect(py_db, create=False)
try:
    cli.analyze(FILES, db=py_db, tool="python", full=True, extend=True)
    check(False, "扩充一个已含全部牌谱的库应报错")
except FileNotFoundError as _exc:
    check("都已经在数据库里了" in str(_exc), "扩充全部重复提示：%s" % _exc)
try:
    cli.analyze(FILES, db=os.path.join(TMP, "nope.sqlite"), tool="python", extend=True)
    check(False, "扩充不存在的库应报错")
except FileNotFoundError as _exc:
    check("请先新建数据库" in str(_exc), "扩充缺库提示：%s" % _exc)
try:
    cli.analyze([], db=py_db, extend=True, fixture=os.path.join(TMP, "x.jsonl"))
    check(False, "fixture 与扩充同时用应报错")
except ValueError as _exc:
    check("fixture 入库不能与扩充模式同时使用" in str(_exc), "fixture + 扩充冲突提示：%s" % _exc)
ver_db = os.path.join(cli.DB_DIR, "__mjtest_ver__.sqlite")
if os.path.isfile(ver_db):
    os.remove(ver_db)
_vc = store.open_db(ver_db)
# 只写 app_version 不够：check_version 先看 schema_version，缺了它会被当成全新库直接放行。
# 两个都写，才是「被旧版本软件生成过」的库。
store.set_meta(_vc, "schema_version", str(store.SCHEMA_VERSION))
store.set_meta(_vc, "app_version", "0.0.9")
_vc.commit()
_vc.close()
_rawv = sqlite3.connect(ver_db)
eq(_rawv.execute("SELECT v FROM meta WHERE k = 'app_version'").fetchone()[0], "0.0.9",
   "人为造一个版本不匹配的库（__mjtest_ver__；这里用 raw sqlite3 读，因为 store.connect 对不匹配库会直接抛错）")
_rawv.close()
check(any(x["name"] == "__mjtest_ver__.sqlite" and not x["compatible"] for x in cli.list_dbs()),
      "list_dbs 把版本不匹配的库标为不兼容")
check(all(x["compatible"] for x in cli.list_dbs() if x["name"] == "20261007_test.sqlite"),
      "用户库（无 app_version 记录）按兼容处理")
eq([x["value"] for x in store.list_feature_values(conn, "junme")], list(range(1, 20)),
   "巡目取值 1..19（带命中数）")
eq(len(store.list_feature_values(conn, "joukyoku")), 8, "本批数据出现过 8 种局况")
eq(feats.BY_KEY["kyotaku"]["key"] in [k for k in feats.BY_KEY], True, "特征注册表可查")
q = store.query(conn, [
    {"key": "junme", "expr": "3"},
    {"key": "kyotaku", "expr": ">=1000"},
    {"key": "riichi_self", "expr": "是"},
], limit=200)
eq(q["total"], 1, "检索 巡目=3 且 供托>=1000 且 自家立直状态=是")
if q["rows"]:
    row = q["rows"][0]
    eq(row["idx"], 2167, "命中行 idx")
    eq(row["log_id"], "2026083021gm-00a9-0000-d0810acf", "命中行牌谱")
    eq(row["joukyoku"], "東三局", "命中行局况")
    eq(row["ev_index"], 22, "命中行事件下标")
    eq(row["frame_index"], 23, "命中行帧下标 = ev_index+1")
    eq(row["label"], feats.row_label(row), "命中行条目名")
    eq(row["log_path"].endswith("d0810acf.xml"), True, "命中行 log_path")
eq(q["used"], ["巡目", "供托", "自家立直状态"], "compile_query 用到的特征名")
allq = store.query(conn, [{"key": "junme", "expr": ">=1"}], limit=5000)
eq(allq["total"], 2786, "巡目>=1 覆盖全部打点行")
eq(sum(1 for r in allq["rows"] if r["label"] == feats.row_label(r)), 2786, "全部行的 label 与条目名格式一致")
eq(sorted(set(r["kind"] for r in allq["rows"])), ["chi", "draw", "pon"], "检索结果行带 kind")
_chi = [r for r in allq["rows"] if r["kind"] == "chi"][0]
eq(_chi["kind"], "chi", "副露帧行 kind：%s" % _chi["label"])
one = store.query_detail(conn, allq["rows"][0]["idx"])
eq(len(one["feats"]), 33, "query_detail 展开 33 个特征（16 + 17）")
rf = store.round_frames(conn, allq["rows"][0]["log_id"], 0)
eq(len(rf) > 0, True, "round_frames 返回本局帧")
check("kind" in rf[0], "round_frames 行含 kind")
_exp = store.export_json(conn, limit=3)
eq((len(_exp["frames"]), len(_exp["features"]), len(_exp["source"])), (3, 33, 5),
   "export_json 结构 meta/features/source/frames")
conn.close()

for bad_cond, frag in [([{"key": "junme", "expr": "boom"}], "可接受条件"),
                       ([{"key": "nope", "expr": "1"}], "未知的牌谱特征"),
                       ([{"key": "joukyoku", "expr": "東九局"}], "可选值")]:
    try:
        cli.run_query(py_db, bad_cond)
        check(False, "坏条件应报错：%r" % bad_cond)
    except ValueError as exc:
        check(frag in str(exc), "坏条件提示（%s）：%s" % (frag, exc))
try:
    cli.resolve_feature("巡目")
    check(True, "resolve_feature 支持中文名")
except Exception as exc:
    check(False, "resolve_feature 中文名失败：%s" % exc)
eq(cli.resolve_feature("junme")["col"], "f_junme", "resolve_feature 支持 key")
ex_db = os.path.join(TMP, "ex.sqlite")
_r0 = cli.analyze(FILES[:2], db=ex_db, tool="python")
eq((_r0["logs"], _r0["db_total"] > 0), (2, True), "扩充测试：先建只有 2 个牌谱的库")
_r1 = cli.analyze(FILES[:3], db=ex_db, tool="python", extend=True)
eq(_r1["extend"], True, "扩充模式返回 extend=True")
eq((_r1["logs"], sorted(_r1["skipped"])), (1, sorted(mjlog.log_id_of(f) for f in FILES[:2])),
   "扩充只分析新牌谱、跳过已入库的 2 个牌谱")
eq(_r1["db_total"] > _r0["db_total"], True, "扩充后库内行数增加（%d -> %d）" % (_r0["db_total"], _r1["db_total"]))
_eqconn = store.connect(ex_db, create=False)
eq(len(store.source_ids(_eqconn)), 3, "扩充后 source 表共 3 个牌谱")
_eqconn.close()
empty_db = os.path.join(TMP, "empty.sqlite")
_e0 = store.open_db(empty_db)
_e0.close()
_e1 = cli.analyze(FILES[:1], db=empty_db, tool="python", extend=True)
check(any("还没有任何牌谱记录" in w for w in _e1["warnings"]), "空库扩充给出「按新建处理」警告：%r" % _e1["warnings"])
eq((_e1["logs"], len(_e1["skipped"])), (1, 0), "空库扩充按新建处理")
eq(cli.parse_condition_lines("巡目=3\n供托>=1000\n# 注释\n自家立直状态: 是"),
   [{"key": "junme", "expr": "3"}, {"key": "kyotaku", "expr": ">=1000"},
    {"key": "riichi_self", "expr": "是"}], "条件行解析")
eq(sorted(os.path.basename(d["name"]) for d in cli.list_dbs()
          if d["name"].startswith("__mjtest") and d["name"] != "__mjtest_ver__.sqlite"), [],
   "list_dbs 读得到目录（__mjtest_ver__ 是本段特意造的版本不匹配库，收尾统一清理）")

# ------------------------------------------------------------------ 4
print("=== 4. 双工具交叉校验 ===")
eq(nodeharness.available(), True, "检测到 node 运行时")
node_db = os.path.join(TMP, "node.sqlite")
res_n = cli.analyze(FILES, db=node_db, tool="node", full=True)
eq(res_n["tool"], "node", "指定 --tool node")
eq(res_n["annotations"], 2786, "node 打点数与 python 一致")
auto_db = os.path.join(TMP, "auto.sqlite")
res_a = cli.analyze([FILES[0]], db=auto_db, tool="auto")
eq(res_a["tool"], "node", "--tool auto 优先 node")


def dump(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    cols = [r[1] for r in c.execute("PRAGMA table_info(frame)")]
    skip = {"tool", "added_at"}
    keep = [x for x in cols if x not in skip]
    rows = c.execute("SELECT * FROM frame ORDER BY log_id, round_index, ev_index, seat").fetchall()
    out = [tuple(r[x] for x in keep) for r in rows]
    full = c.execute("SELECT COUNT(*) c FROM frame_full").fetchone()[0]
    c.close()
    return keep, out, full


keep, rows_n, full_n = dump(node_db)
_, rows_p, full_p = dump(py_db)
eq(len(rows_n), 2786, "node 库 frame 行数")
eq(len(rows_p), 2786, "python 库 frame 行数")
eq(sum(1 for c in keep if c.startswith("s_")), 17, "交叉校验覆盖 17 个第二类特征列")
diffs = 0
first = ""
for i, (a, b) in enumerate(zip(rows_n, rows_p)):
    if a != b:
        diffs += 1
        if not first:
            first = "第 %d 行 %s" % (i, [c for c, x, y in zip(keep, a, b) if x != y])
eq(diffs, 0, "全字段逐项一致（%d 列 × %d 行，首例 %s）" % (len(keep), len(rows_n), first or "-"))
eq(full_n, full_p, "frame_full 行数一致（%d）" % full_n)
eq(full_n > 0, True, "full=True 写了 frame_full")

# --- 4b. 第 14 轮：同一牌谱重分析不留孤儿 frame_full ------------------------
res_re = cli.analyze(FILES, db=py_db, tool="python", full=True)
eq(res_re["db_total"], 2786, "重分析后库内总行数不变")
_, rows_re, full_re = dump(py_db)
eq(len(rows_re), 2786, "重分析后 frame 行数不变")
eq(full_re, full_p, "重分析后 frame_full 行数不膨胀（%d）" % full_re)
_c = sqlite3.connect(py_db)
_orph = _c.execute("SELECT COUNT(*) c FROM frame_full WHERE frame_idx NOT IN"
                   " (SELECT idx FROM frame)").fetchone()[0]
_c.close()
eq(_orph, 0, "frame_full 无孤儿行")

# --- 4c. CLI --delete-db 退出码 -------------------------------------------
_del = os.path.join(TMP, "del.sqlite")
cli.analyze([FILES[0]], db=_del)
eq(os.path.isfile(_del), True, "临时库已生成")
eq(cli.main(["--delete-db", _del]), 0, "--delete-db 成功后返回 0")
eq(os.path.isfile(_del), False, "--delete-db 删掉了文件")
eq(cli.main(["--delete-db", _del]), 1, "--delete-db 文件不存在返回 1")

# ------------------------------------------------------------------ 4d
print("=== 4d. 牌谱下载模块（离线：解析 / 目录 / 文本） ===")
LOGID = "2026082919gm-00a9-0000-4e40cd3e"
eq(download.extract_log_id(LOGID), LOGID, "裸特征码")
eq(download.extract_log_id("http://tenhou.net/0/?log=%s&tw=0" % LOGID), LOGID, "带 log= 参数的 URL")
eq(download.extract_log_id("http://tenhou.net/0/log/?%s" % LOGID), LOGID, "/log/?<id> 形式")
eq(download.extract_log_id("牌谱：%s 谢谢" % LOGID), LOGID, "文本里夹带特征码")
try:
    download.extract_log_id("https://example.com/nope")
    check(False, "无法解析的输入应报错")
except ValueError as exc:
    check("无法从" in str(exc), "解析失败提示：%s" % exc)
eq(download.build_download_url(LOGID), "http://tenhou.net/0/log/?%s" % LOGID, "下载地址")
eq(re.match(r"^\d{8}-\d{6}$", download.default_subdir()) is not None, True,
   "默认子目录 = 时间戳（%s）" % download.default_subdir())
eq(download.resolve_out_dir("mytest"), os.path.join(download.paipu_root(), "mytest"), "自定义子目录")
eq(download.resolve_out_dir("data/paipu/mytest"), os.path.join(download.paipu_root(), "mytest"),
   "允许带 data/paipu/ 前缀")
eq(download.resolve_out_dir(download.default_subdir()).startswith(download.paipu_root()), True,
   "存储位置固定在 data/paipu 下")
for _bad in ("../evil", "C:\\tmp\\x", "a/b", "a\\b"):
    try:
        download.resolve_out_dir(_bad)
        check(False, "非法存储地址应报错：%r" % _bad)
    except ValueError as exc:
        check("data/paipu" in str(exc), "非法存储地址提示（%r）：%s" % (_bad, exc))
eq(download.read_url_lines("# 注释\n\n%s\nhttp://tenhou.net/0/?log=%s\n" % (LOGID, LOGID)),
   [LOGID, "http://tenhou.net/0/?log=%s" % LOGID], "文本逐行读取（跳过空行 / # 注释）")
eq(download.collect_urls(["A", "B", "A", " "]), ["A", "B"], "URL 去重保序")
eq(download.looks_like_mjlog(b'<mjloggm ver="2.3"></mjloggm>'), True, "mjlog 内容识别")
eq(download.looks_like_mjlog(b"<html>nope</html>"), False, "非牌谱内容识别")
_dl_tmp = os.path.join(TMP, "dl")
_p1, _w1 = download.save_log(LOGID, b'<mjloggm ver="2.3"></mjloggm>', _dl_tmp, overwrite=True)
eq((os.path.isfile(_p1), _w1), (True, True), "save_log 写入 <log_id>.xml")
_p2, _w2 = download.save_log(LOGID, b"second", _dl_tmp, overwrite=False)
eq((_p2, _w2), (_p1, False), "save_log overwrite=False 时跳过")
eq(open(_p1, "rb").read().startswith(b"<mjloggm"), True, "overwrite=False 保留原内容")
eq(isinstance(download.download_snapshot(), dict), True, "下载进度快照可读")

# ------------------------------------------------------------------ 5
print("=== 5. 本地服务接口 ===")
s = socket.socket()
s.bind(("127.0.0.1", 0))
PORT = s.getsockname()[1]
s.close()
srv = server.make_server(PORT)
th = threading.Thread(target=srv.serve_forever, daemon=True)
th.start()
BASE = "http://127.0.0.1:%d" % PORT


def http(path, payload=None, timeout=15):
    """timeout：/api/analyze 要跑完整个目录（含 17 个第二类特征），必须给足。"""
    url = BASE + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


try:
    st, d = http("/api/health")
    eq((st, d.get("root")), (200, ROOT), "GET /api/health")
    eq((d.get("version"), bool(d.get("name"))), (store.APP_VERSION, True), "health 带软件版本与名称")
    eq((d.get("author"), d.get("author_email")), ("Zumma Crystal", "z1025zzsg@sohu.com"),
       "health 带作者信息（m04115③）")
    st, d = http("/api/features")
    eq((st, len(d.get("features") or [])), (200, 33), "GET /api/features 33 项（16 + 17）")
    eq(d.get("schema_version"), store.SCHEMA_VERSION, "features 带 schema_version")
    eq(d.get("version"), store.APP_VERSION, "features 带软件版本")
    check(bool(d.get("name")), "features 带软件名：%s" % d.get("name"))
    eq((d.get("author"), d.get("author_email")), ("Zumma Crystal", "z1025zzsg@sohu.com"),
       "features 带作者信息（m04115③）")
    eq(bool(d.get("doukou")), True, "features 带口径说明")
    _enums = [f for f in (d.get("features") or []) if f.get("kind") == "enum"]
    eq((len(_enums), all(bool(f.get("values")) for f in _enums)), (7, True),
       "7 个互斥取值特征都带 values（前端据此渲染下拉）")
    eq(feats.BY_KEY["oya_meld"]["name"], "亲家（他家）副露状态", "特征 15 显示名已修正")
    # --- 第 23 轮：向听数对外显示 >=3（显示口径；检索仍按内部整数匹配，见第 6 节 5 条）---
    eq(cli.feat_value_text("shanten_mentsu", 3), ">=3", "向听数内部值 3 显示为 >=3")
    eq(cli.feat_value_text("shanten_chiitoi", 3), ">=3", "七対子向听数 3 显示为 >=3")
    eq(cli.feat_value_text("shanten_mentsu", 2), "2", "向听数 2 原样显示")
    eq(cli.feat_value_text("junme", 3), "3", "非向听数特征不受影响")
    # --- 第 23 轮：库名解析要容忍带 .sqlite 后缀（扩充报「数据库不存在」的根因）---
    eq(cli.db_path_of(None, "x.sqlite"), cli.db_path_of(None, "x"), "库名带 .sqlite 与不带等价")
    check(cli.db_path_of(None, "x").endswith(os.path.join("data", "db", "x.sqlite")),
          "库名解析到 data/db/<name>.sqlite：%s" % cli.db_path_of(None, "x"))
    st, d = http("/api/analyze", {"paths": [], "db_name": "__mjtest_none__.sqlite", "extend": True})
    check(st == 400 and ".sqlite.sqlite" not in (d.get("error") or ""),
          "扩充不存在的库：报错不重复后缀（%s）" % (d.get("error") or "")[:90])
    st, d = http("/api/dbs")
    eq((st, d.get("dir")), (200, cli.DB_DIR), "GET /api/dbs")
    check(all("app_version" in x and "compatible" in x for x in (d.get("dbs") or [])),
          "/api/dbs 每项带 app_version / compatible")
    check(any(x["name"] == "__mjtest_ver__.sqlite" and not x["compatible"] for x in (d.get("dbs") or [])),
          "不兼容的库被标 compatible=false")
    st, d = http("/api/scan?dir=" + urllib.parse.quote(DATA))
    _scanned = {os.path.basename(p) for p in (d.get("files") or [])}
    check(st == 200 and (d.get("count") or 0) >= 5,
          "GET /api/scan 扫到 %r 个牌谱（data 下递归）" % d.get("count"))
    check(all(os.path.basename(p) in _scanned for p in FILES),
          "扫描结果包含全部 5 个基础牌谱（扫描到 %d 个）" % (d.get("count") or 0))

    print("  -- POST /api/analyze（5 个基础牌谱 + node，含第二类特征补列，耗时较长）")
    st, d = http("/api/analyze", {"paths": FILES, "db_name": "__mjtest__", "tool": "node"}, timeout=3600)
    eq((st, d.get("ok")), (200, True), "POST /api/analyze（文件列表 + node）")
    eq((d.get("logs"), d.get("db_total")), (5, 2786), "analyze 摘要")
    eq(d.get("warnings"),
       ["--tool node：第一类特征来自 node，第二类 17 项由 python 补齐（js 侧没有实现）"],
       "analyze 带 node 路径的第二类特征补齐警告")

    # --- 第 21 轮新接口：进度 / 帧特征 / 下载 -----------------------------
    st, d = http("/api/analyze-progress")
    eq((st, isinstance(d.get("progress"), dict)), (200, True), "GET /api/analyze-progress")
    eq(d["progress"].get("running"), False,
       "分析结束后 running=False（done=%r tool=%r）" % (d["progress"].get("done"), d["progress"].get("tool")))
    eq(d["progress"].get("tool"), "node", "进度快照记录工具")
    eq(d["progress"].get("files_done"), 5, "进度快照记录已完成牌谱数")

    st5, d5 = http("/api/analyze", {"paths": FILES, "db_name": "__mjtest__", "extend": True}, timeout=600)
    eq(st5, 400, "POST /api/analyze 扩充已全部入库的库 400")
    check("都已经在数据库里了" in str(d5.get("error")), "扩充重复提示：%s" % d5.get("error"))
    st5, d5 = http("/api/detail", {"db_name": "__mjtest_ver__", "idx": 1})
    eq(st5, 400, "版本不匹配的库拒绝加载 400")
    check("数据库由软件版本" in str(d5.get("error")), "版本不匹配提示：%s" % d5.get("error"))
    st, d = http("/api/download-progress")
    eq((st, isinstance(d.get("progress"), dict)), (200, True), "GET /api/download-progress")

    _c = sqlite3.connect(os.path.join(cli.DB_DIR, "__mjtest__.sqlite"))
    _c.row_factory = sqlite3.Row
    _pick = _c.execute("SELECT round_index, frame_index FROM frame WHERE log_id = ? ORDER BY idx LIMIT 1",
                       ("2026083021gm-00a9-0000-d0810acf",)).fetchone()
    _c.close()
    check(_pick is not None, "样本库里能查到 2026083021gm-00a9-0000-d0810acf 的打点帧")
    st, d = http("/api/frame-feats", {"db_name": "__mjtest__",
                                      "log_id": "2026083021gm-00a9-0000-d0810acf",
                                      "round_index": _pick["round_index"], "frame_index": _pick["frame_index"]})
    eq((st, (d.get("row") or {}).get("frame_index")), (200, _pick["frame_index"]),
       "POST /api/frame-feats 命中帧（round %d / frame %d）" % (_pick["round_index"], _pick["frame_index"]))
    eq(len(((d.get("row") or {}).get("feats") or {})), 33, "frame-feats 行带 33 个特征")
    st, d = http("/api/frame-feats", {"db_name": "__mjtest__", "log_id": "nope",
                                      "round_index": 0, "frame_index": 1})
    eq((st, d.get("row")), (200, None), "POST /api/frame-feats 未命中返回 null")
    st, d = http("/api/frame-feats", {"db_name": "__mjtest__", "log_id": "nope"})
    eq(st, 400, "POST /api/frame-feats 缺参数 400")

    st, d = http("/api/download", {"subdir": "__mjtest_dl", "url": "   "})
    eq(st, 400, "POST /api/download 空输入 400")
    check("请先输入" in (d.get("error") or ""), "空输入提示：%s" % d.get("error"))
    st, d = http("/api/download", {"subdir": "../evil", "url": "2026082919gm-00a9-0000-4e40cd3e"})
    eq(st, 400, "POST /api/download 非法存储地址 400")
    check("data/paipu" in (d.get("error") or ""), "非法存储地址提示：%s" % d.get("error"))
    st, d = http("/api/download", {"subdir": "__mjtest_dl", "url": "not-a-paipu"})
    eq((st, d.get("started"), d.get("total")), (200, True, 1), "POST /api/download 启动后台下载")
    _p = {}
    for _ in range(60):
        _p = http("/api/download-progress")[1].get("progress") or {}
        if _p.get("done"):
            break
        time.sleep(0.05)
    eq(_p.get("done"), True, "下载任务结束（saved=%r failed=%r）" % (_p.get("saved"), _p.get("failed")))
    eq((_p.get("total"), _p.get("failed")), (1, 1), "无效输入的下载计入失败数")
    check(download.download_snapshot().get("dir", "").endswith("__mjtest_dl"), "下载目录 = data/paipu/__mjtest_dl")

    st, d = http("/api/query", {"db_name": "__mjtest__", "conds": [
        {"key": "junme", "expr": "3"},
        {"key": "kyotaku", "expr": ">=1000"},
        {"key": "riichi_self", "expr": "是"}]})
    eq((st, d.get("total")), (200, 1), "POST /api/query 精确检索")
    eq((d["rows"][0]["label"] if d.get("rows") else ""),
       "2026083021gm-00a9-0000-d0810acf 東三局 0本場 3巡目 西家", "命中行条目名（与 row_label 一致）")
    check(bool(d.get("rows")) and d["rows"][0]["label"].endswith("西家"), "命中行条目名：%s"
          % (d["rows"][0]["label"] if d.get("rows") else "-"))

    st, d = http("/api/query", {"db_name": "__mjtest__", "lines": "巡目=3\n供托>=1000\n自家立直状态=是"})
    eq((st, d.get("total")), (200, 1), "POST /api/query（lines 文本条件）")
    st, d = http("/api/query", {"db_name": "__mjtest__", "conds": [{"key": "junme", "expr": "boom"}]})
    eq(st, 400, "POST /api/query 坏条件 400")
    check("可接受条件" in (d.get("error") or ""), "坏条件错误内容：%s" % d.get("error"))
    st, d = http("/api/query", {"db_name": "__mjtest__", "conds": []})
    eq(st, 400, "POST /api/query 空条件 400")
    st, d = http("/api/query", {"db_name": "__nope__", "conds": [{"key": "junme", "expr": "3"}]})
    eq(st, 400, "POST /api/query 不存在的库 400")
    check(not os.path.isfile(os.path.join(cli.DB_DIR, "__nope__.sqlite")),
          "检索不存在的库不会顺手建库")

    st, d = http("/api/browse", {"db_name": "__mjtest__", "limit": 0})
    eq((st, d.get("total"), len(d.get("rows") or [])), (200, 2786, 2786), "POST /api/browse limit=0 取全 2786 行")
    eq(set(d["rows"][0].keys()) >= {"idx", "log_id", "frame_index", "seat", "label", "log_path", "kind"}, True,
       "browse 行含定位/条目/牌谱路径/kind 字段")
    st, d = http("/api/browse", {"db_name": "__mjtest__", "limit": 100, "offset": 10})
    eq((st, len(d.get("rows") or [])), (200, 100), "POST /api/browse 分页")

    st, d = http("/api/detail", {"db_name": "__mjtest__", "idx": 2076})
    eq((st, len(((d.get("row") or {}).get("feats") or {}))), (200, 33), "POST /api/detail 展开 33 特征")
    st, d = http("/api/round-frames", {"db_name": "__mjtest__", "log_id": "2026083021gm-00a9-0000-d0810acf",
                                       "round_index": 0})
    eq((st, len(d.get("rows") or []) > 0), (200, True), "POST /api/round-frames")

    st, d = http("/api/read?path=" + urllib.parse.quote(FILES[0]))
    eq(st, 200, "GET /api/read 牌谱原文")
    check((d.get("text") or "").lstrip().startswith("<mjloggm"), "read 返回 mjlog 文本（%d 字符）" % len(d.get("text") or ""))
    st, d = http("/api/read?path=" + urllib.parse.quote(os.path.join(ROOT, "no_such.xml")))
    eq(st, 400, "GET /api/read 不存在的文件 400")
    st, d = http("/api/nope")
    eq(st, 404, "GET 未知接口 404")

    st, d = http("/api/delete-db", {"name": "__mjtest__"})
    eq((st, d.get("ok")), (200, True), "POST /api/delete-db")
    st, d = http("/api/dbs")
    eq(all(not x["name"].startswith("__mjtest") or x["name"] == "__mjtest_ver__.sqlite"
           for x in (d.get("dbs") or [])), True,
       "删除后列表已无该库（__mjtest_ver__ 由收尾清理删除）")
finally:
    srv.shutdown()
    srv.server_close()

# ------------------------------------------------------------------ 清理 + 汇总
shutil.rmtree(TMP, ignore_errors=True)
shutil.rmtree(os.path.join(download.paipu_root(), "__mjtest_dl"), ignore_errors=True)
leftover = [d["path"] for d in cli.list_dbs() if d["name"].startswith("__mjtest")]
for p in leftover:
    try:
        os.remove(p)
    except OSError:
        pass

print("")
print("===== 结果 =====")
print("通过 %d 项，失败 %d 项" % (OK[0], BAD[0]))
if BAD[0]:
    print("测试失败")
    sys.exit(1)
print("全部通过")