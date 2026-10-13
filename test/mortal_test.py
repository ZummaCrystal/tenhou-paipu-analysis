# -*- coding: utf-8 -*-
r"""mortal 报告适配层正式测试（第 59 轮，用户 m05937 ③：Mortal 系列牌谱沿用 NAGA 的分析与展示模板）。

覆盖：
  1. 后缀 / 特征码 / 报告地址 / load_report 的校验（.mortal-a|b|c、旧 .mortal、裸 .json）
  2. 合成报告端到端（第 1 局 = 决策映射）：entry -> 帧的定位（自己回合 / 他家打牌后的鸣牌决策）、
     dahai_pred / huro（PASS / 吃 / 碰）/ reach / kan 折算成万分比、同一次触发承载多条 entry、
     找不到触发消息的 entry 计入 miss
  3. 合成报告端到端（第 2 局 = 和了）：报告没有役种 / 番 / 符 / 点数 ⇒ 符 / 点 / 役种全部由
     mjscore/agari.py 现算；点数 = deltas[actor] 扣本场 300 / 供托 1000；里宝牌指示牌是牌名（"3s"）
     而不是牌 id（第 59 轮踩坑：NAGA 的 _hora_ctx 会 int() 它），换算后 yaku / ten 不再为空
  4. 内容嗅探与分派：mortal.looks_like_mortal()、cli.report_kind()（.json 消歧成 mortal / naga）、
     cli.file_log_id()、cli.game_from_file()
  5. 打点链路：feats.ai_values()（文件级：只有对应的那一个第零类 = 是）、feats.paipu_url_of()、
     feats.ai_frame_keys() / feats.ai_frame_values() 与 cli.fill_ai()（第 60 轮 / 用户 m06323 ①，
     口径按用户 m06560 更正：第零类**按帧判定** —— 只有该帧**做决策的那名玩家**（打点行的 seat 列，
     mortal 报告里就是 review.player_id 那一家）带该模型的决策概率表才是「是」；
     辅助列 ai_models / ai_series 也随帧）
  6. 真实样例（build\_scratch\mortal\ 里的报告，存在时才跑）：12 局 / entries 命中 / 模型名 /
     帧字段 / replay 不变量
  7. 决策帧 ≠ 有 AI 决策概率向量（用户 m06670）：检索范围（打点帧）按牌局选帧、覆盖四家的
     决策帧，而 AI 概率向量只出现在被复盘那一家决策的帧上（mortal 报告只复盘一家）

运行：
  python test\mortal_test.py
"""
import glob
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mjscore import cli, feats, mortal, naga, paths, replay  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                        # noqa: BLE001
    pass

OK = [0]
BAD = [0]
SCRATCH = os.path.join(ROOT, "build", "_scratch")
SAMP_MORTAL = os.path.join(SCRATCH, "mortal")
TEST_DIR = os.path.join(SCRATCH, "_mortaltest")

# 34 种牌名（mjai 写法；供确定性发牌用）
NAMES = (["%dm" % i for i in range(1, 10)] + ["%dp" % i for i in range(1, 10)]
         + ["%ds" % i for i in range(1, 10)] + ["E", "S", "W", "N", "P", "F", "C"])


def check(cond, label):
    if cond:
        OK[0] += 1
        print("  OK   %s" % label)
    else:
        BAD[0] += 1
        print("  FAIL %s" % label)


def eq(got, want, label):
    check(got == want, "%s（得到 %r，期望 %r）" % (label, got, want))


# ------------------------------------------------------------------ 夹具
def _deal():
    """确定性发牌：前 52 张按顺序发四家（每种牌最多 4 张），返回 (hands, 余牌)。"""
    pool = []
    for nm in NAMES:
        pool.extend([nm] * 4)
    hands = [pool[i * 13:(i + 1) * 13] for i in range(4)]
    return hands, pool[52:]


def _start(oya, kyoku, tehais, dora="9p"):
    return {"type": "start_kyoku", "bakaze": "E", "kyoku": kyoku, "honba": 0, "kyotaku": 0,
            "oya": oya, "dora_marker": dora, "scores": [25000, 25000, 25000, 25000],
            "tehais": [list(h) for h in tehais]}


def _dahai(actor, pai):
    return {"action": {"type": "dahai", "actor": actor, "pai": pai, "tsumogiri": True}, "prob": 0.5}


def _mapping_entries():
    """第 1 局的 7 条 entry（6 条能定位、1 条找不到触发消息）。"""
    return [
        {"junme": 1, "tiles_left": 69, "last_actor": 0, "tile": "5p", "shanten": 2,
         "details": [{"action": {"type": "dahai", "actor": 0, "pai": "5p", "tsumogiri": True}, "prob": 0.62},
                     {"action": {"type": "dahai", "actor": 0, "pai": "9p", "tsumogiri": False}, "prob": 0.38}]},
        {"junme": 1, "tiles_left": 68, "last_actor": 1, "tile": "6p", "shanten": 3,
         "details": [{"action": {"type": "none"}, "prob": 0.45},
                     {"action": {"type": "pon", "actor": 0, "target": 1, "pai": "6p"}, "prob": 0.55}]},
        {"junme": 2, "tiles_left": 67, "last_actor": 2, "tile": "7p", "shanten": 3,
         "details": [{"action": {"type": "none"}, "prob": 0.4},
                     {"action": {"type": "chi", "actor": 0, "target": 2, "pai": "7p",
                                 "consumed": ["5p", "6p"]}, "prob": 0.6}]},
        {"junme": 3, "tiles_left": 66, "last_actor": 0, "tile": "8p", "shanten": 1,
         "details": [{"action": {"type": "dahai", "actor": 0, "pai": "8p", "tsumogiri": True}, "prob": 0.3},
                     {"action": {"type": "reach", "actor": 0}, "prob": 0.7}]},
        {"junme": 3, "tiles_left": 66, "last_actor": 0, "tile": "8p", "shanten": 1,
         "details": [{"action": {"type": "dahai", "actor": 0, "pai": "8p", "tsumogiri": True}, "prob": 0.3}]},
        {"junme": 3, "tiles_left": 66, "last_actor": 0, "tile": "8p", "shanten": 1,
         "details": [{"action": {"type": "ankan", "actor": 0}, "prob": 0.85}]},
        {"junme": 9, "tiles_left": 50, "last_actor": 0, "tile": "C", "shanten": 1,
         "details": [{"action": {"type": "dahai", "actor": 0, "pai": "C", "tsumogiri": False}, "prob": 0.5}]},
    ]


def _mapping_log():
    hands, _rest = _deal()
    msgs = [
        {"type": "tsumo", "actor": 0, "pai": "5p"},
        {"type": "dahai", "actor": 0, "pai": "5p", "tsumogiri": True},
        {"type": "tsumo", "actor": 1, "pai": "6p"},
        {"type": "dahai", "actor": 1, "pai": "6p", "tsumogiri": True},
        {"type": "tsumo", "actor": 2, "pai": "7p"},
        {"type": "dahai", "actor": 2, "pai": "7p", "tsumogiri": True},
        {"type": "tsumo", "actor": 0, "pai": "8p"},
        {"type": "dahai", "actor": 0, "pai": "8p", "tsumogiri": True},
    ]
    log = [{"type": "start_game", "names": ["A", "B", "C", "D"], "kyoku_first": 1, "aka_flag": True},
           _start(0, 1, hands)]
    log.extend(msgs)
    log.append({"type": "ryukyoku", "deltas": [0, 0, 0, 0]})
    log.append({"type": "end_kyoku"})
    return log


def _hora_log():
    tehais = [
        ["C", "C", "C", "2m", "3m", "4m", "5m", "6m", "7m", "2p", "3p", "4p", "5s"],
        ["1m", "1m", "1m", "9m", "9m", "9m", "1s", "1s", "1s", "9s", "9s", "9s", "E"],
        ["2p", "2p", "2p", "5p", "5p", "5p", "6p", "6p", "6p", "7p", "7p", "7p", "S"],
        ["8p", "8p", "8p", "8p", "W", "W", "W", "N", "N", "N", "P", "P", "P"],
    ]
    log = [{"type": "start_game", "names": ["A", "B", "C", "D"], "kyoku_first": 1, "aka_flag": True},
           _start(1, 2, tehais)]
    log.append({"type": "tsumo", "actor": 0, "pai": "5s"})
    log.append({"type": "hora", "actor": 0, "target": 0, "deltas": [1200, -400, -400, -400],
                "ura_markers": ["3s"]})
    log.append({"type": "end_kyoku"})
    return log


def _report(model_tag="4.1b"):
    return {"engine": "Mortal", "version": "1.5.10", "game_length": "Hanchan", "temperature": None,
            "player_id": 0,
            "review": {"model_tag": model_tag, "temperature": 0.1,
                       "kyokus": [{"kyoku": 1, "honba": 0, "entries": _mapping_entries()},
                                  {"kyoku": 2, "honba": 0, "entries": []}]},
            "mjai_log": _mapping_log() + _hora_log()[1:]}


# ------------------------------------------------------------------ 1. 后缀 / 特征码 / 读取
def section1():
    print("---- 1. 后缀 / 特征码 / 报告地址 / load_report")
    eq(mortal.is_mortal_file("fb13c2973c0eabb3.mortal-b"), True, "is_mortal_file 认得 .mortal-b")
    eq(mortal.is_mortal_file("fb13c2973c0eabb3.MORTAL-A"), True, "后缀大小写不敏感（.MORTAL-A）")
    eq(mortal.is_mortal_file("fb13c2973c0eabb3.mortal"), True, "旧后缀 .mortal 仍认")
    eq(mortal.is_mortal_file("fb13c2973c0eabb3.json"), False, "裸 .json 不是后缀判定的 mortal")
    eq(mortal.is_mortal_file("x.naga"), False, "naga 报告不会被当成 mortal")
    eq(mortal.report_id_of_path("FB13C2973C0EABB3.mortal-b"), "fb13c2973c0eabb3", "特征码 = 去后缀并小写")
    eq(mortal.report_id_of_path("/tmp/a/0af57be54bf867a0.json"), "0af57be54bf867a0",
       "裸 .json（浏览器另存 / 报告地址）也能取特征码")
    eq(mortal.report_id_of_path("x.naga"), None, "naga 文件取不出 mortal 特征码")
    eq(mortal.view_url("fb13c2973c0eabb3"), "https://mjai.ekyu.moe/report/fb13c2973c0eabb3.json",
       "报告地址 = https://mjai.ekyu.moe/report/<id>.json")
    eq(mortal.MORTAL_SUFFIXES, (".mortal-a", ".mortal-b", ".mortal-c", ".mortal"),
       "后缀表 = .mortal-a|b|c + 旧 .mortal")
    eq(mortal.MORTAL_SUFFIXES, tuple(paths.MORTAL_SUFFIXES), "后缀表来自 mjscore/paths.py")

    rep = _report()
    eq(mortal.load_report(rep) is rep, True, "load_report 接受已解析的 dict")
    data = json.dumps(rep).encode("utf-8")
    eq(mortal.load_report(data)["version"], "1.5.10", "load_report 接受原始字节")
    import gzip
    eq(mortal.load_report(gzip.compress(data))["engine"], "Mortal", "load_report 自动解 gzip")
    for bad, why in ((b'{"pred": []}', "缺少 mjai_log"), (b"not json", "不是 JSON"),
                     ({"mjai_log": []}, "缺少 review")):
        try:
            mortal.load_report(bad)
            check(False, "坏内容被拒（%s）" % why)
        except ValueError as exc:
            check(why in str(exc), "坏内容被拒：%s -> %s" % (why, str(exc)[:40]))

    eq(mortal.model_list(_report("4.1b"))[0]["name"], "Mortal-4.1-平衡", "model_tag 4.1b -> Mortal-4.1-平衡")
    eq(mortal.model_list(_report("4.1c"))[0]["name"], "Mortal-4.1-争一", "model_tag 4.1c -> Mortal-4.1-争一")
    eq(mortal.model_list(_report("4.1a"))[0]["name"], "Mortal-4.1-避四", "model_tag 4.1a -> Mortal-4.1-避四")
    odd = mortal.model_list(_report("9.9x"))[0]
    eq((odd["name"], odd["raw"], odd["series"], odd["index"]),
       ("Mortal-4.1-平衡", "4.1b", "Mortal", 0),
       "认不出的 model_tag 回退到 4.1-平衡（软件只支持 4.1，用户 m05806 ①）")


# ------------------------------------------------------------------ 2. 决策映射
def section2():
    print("---- 2. 合成报告：entry -> 帧（决策映射）")
    game = mortal.to_game(_report())
    eq(game["naga"]["kind"], "mortal", "naga 容器带 kind = mortal（前端复用 NAGA 展示模板）")
    eq(game["naga"]["entries"], {"hit": 6, "miss": 1}, "6 条命中 / 1 条找不到触发消息")
    eq(len(game["rounds"]), 2, "两局")
    eq(game["meta"]["names"], ["A", "B", "C", "D"], "玩家名取 start_game.names")
    eq(game["meta"]["mortal"], True, "meta 标记 mortal")
    eq(game["log_id"], (game["meta"].get("log_id") or ""), "log_id 与 meta 一致")

    evs = game["rounds"][0]["events"]
    eq([e["type"] for e in evs][:4], ["draw", "discard", "draw", "discard"], "事件流前 4 步")
    eq(evs[-1]["type"], "ryuukyoku", "第 1 局以流局收尾（事件名沿用 naga.py 的 ryuukyoku）")
    frames = game["naga"]["rounds"][0]
    eq(len(frames), len(evs) + 1, "帧数 = 事件数 + 1（与 NAGA / 前端口径一致）")
    eq(frames[0]["msg"], "start_kyoku", "帧 0 = 配牌")
    eq(frames[1]["msg"], "tsumo", "帧 1 = 处理完第 1 个事件（自家摸牌）")

    k5p, k9p = naga.tile_kind("5p"), naga.tile_kind("9p")
    dp = (frames[1].get("dahai_pred") or [[]])[0]
    eq((dp[k5p], dp[k9p]), (6200, 3800), "帧 1 打牌概率 = 5p 62% / 9p 38%（0..1 -> 万分比）")
    eq(frames[2].get("dahai_pred"), None, "别人打出的那张牌所在帧没有决策概率")

    eq(frames[4].get("huro"), {"0": [{"0": 4500, "4": 5500}]},
       "鸣牌决策帧 huro = PASS 45% / 碰 55%（座位 0）")
    eq(frames[6].get("huro"), {"0": [{"0": 4000, "3": 6000}]}, "吃（5p+6p 吃 7p）= 下标 3")

    fr7 = frames[7]
    eq((fr7.get("dahai_pred") or [[]])[0][naga.tile_kind("8p")], 3000, "同一帧可以同时有打牌概率")
    eq(fr7.get("reach"), [7000], "同一帧可以同时有立直概率（立直 + 立直后的打牌两条 entry）")
    eq(fr7.get("kan"), [{"1": 8500}], "同一帧可以同时有暗杠概率")

    probs, n = replay.check_invariants(game, 0)
    eq((probs, n > 0), ([], True), "第 1 局 replay 不变量 0 错误（%d 帧）" % n)

    # 决策帧 ≠ 有 AI 决策概率向量（用户 m06670）：打点入库的静态帧由牌局决定、覆盖多家的决策帧；
    # AI 概率向量只出现在被复盘那一家的决策帧上（本合成谱的复盘家 = 座位 0）。
    recs = feats.records_for_round(game, 0)
    rseats = sorted(set(r["seat"] for r in recs))
    eq(rseats, [0, 1, 2], "打点帧按牌局选帧、覆盖多家的决策帧（seat = %s）" % rseats)
    ai_recs = [r for r in recs if any(r["feats"].get(k) == "是" for k in feats.AI_KEYS)]
    eq((len(ai_recs) > 0, all(r["seat"] == 0 and r["seat"] == game["meta"]["viewer_seat"] for r in ai_recs)),
       (True, True), "AI 概率向量只覆盖被复盘那一家的帧（%d / %d 条，用户 m06670）" % (len(ai_recs), len(recs)))
    check(len(ai_recs) < len(recs),
          "打点帧数 > 带 AI 概率向量的帧数（%d > %d：mortal 谱里两个概念不等价，用户 m06670）"
          % (len(recs), len(ai_recs)))


# ------------------------------------------------------------------ 3. 和了结算
def section3():
    print("---- 3. 合成报告：和了（符 / 点 / 役种由引擎现算）")
    game = mortal.to_game(_report())
    evs = game["rounds"][1]["events"]
    eq([e["type"] for e in evs], ["draw", "agari"], "第 2 局事件流 = 摸牌 + 和了")
    ag = [e for e in evs if e["type"] == "agari"][0]
    eq((ag["winner"], ag["fromWho"]), (0, 0), "自摸（winner == fromWho）")
    check(bool(ag["ten"]) and ag["ten"][0] > 0,
          "报告没给符 / 番 ⇒ 符由 mjscore/agari.py 现算：%r" % (ag["ten"],))
    eq(ag["ten"][1], 1200, "点数 = deltas[0] 扣本场 300 / 供托 1000（本局都 0）")
    check(len(ag["yaku"]) >= 1, "报告没给役种 ⇒ 引擎判定：%r" % (ag["yaku"],))
    check(all(isinstance(x, int) for x in (ag.get("ura") or [])),
          "里宝牌指示牌从牌名（3s）换算成牌 id：%r" % (ag.get("ura"),))
    probs, n = replay.check_invariants(game, 1)
    eq((probs, n > 0), ([], True), "第 2 局 replay 不变量 0 错误（%d 帧）" % n)


# ------------------------------------------------------------------ 4. 嗅探与分派
def section4():
    print("---- 4. looks_like_mortal / cli.report_kind / file_log_id / game_from_file")
    rep = _report("4.1c")
    check(mortal.looks_like_mortal(rep) is True, "looks_like_mortal：含 mjai_log + review -> True")
    check(mortal.looks_like_mortal({"pred": []}) is False, "looks_like_mortal：NAGA 报告 -> False")
    check(mortal.looks_like_mortal(b"\x1f\x8b\x08garbage") is False, "looks_like_mortal：坏字节 -> False")

    shutil.rmtree(TEST_DIR, ignore_errors=True)
    os.makedirs(TEST_DIR)
    try:
        p_mortal = os.path.join(TEST_DIR, "fb13c2973c0eabb3.json")     # 裸 .json（报告地址形态）
        p_naga = os.path.join(TEST_DIR, "aaaa.json")                   # 裸 .json 的 NAGA 报告
        with open(p_mortal, "w", encoding="utf-8") as fh:
            json.dump(rep, fh)
        with open(p_naga, "w", encoding="utf-8") as fh:
            json.dump({"pred": [[{"end_num": 1}]]}, fh)
        eq(cli.report_kind(p_mortal), "mortal", ".json 的 Mortal 报告 -> mortal（内容嗅探）")
        eq(cli.report_kind(p_naga), "naga", ".json 的 NAGA 报告 -> naga")
        eq(cli.report_kind("x.mortal-a"), "mortal", "显式后缀 .mortal-a -> mortal（不看内容）")
        eq(cli.report_kind("x.json.gz"), "naga", ".json.gz 默认 -> naga")
        eq(cli.report_kind("x.tenhou"), None, "天凤牌谱 -> None")
        eq(cli.file_log_id(p_mortal), "fb13c2973c0eabb3", "特征码 = 报告 id")
        g = cli.game_from_file(p_mortal)
        eq((g["naga"]["kind"], len(g["rounds"])), ("mortal", 2), "cli.game_from_file 分派到 mortal 解析器")
        eq(naga.is_naga_file(p_mortal), True, "注：mortal 的 .json 仍在 naga.is_naga_file 的后缀范围内")
        eq(mortal.is_mortal_file(p_mortal), False, "…但 mortal.is_mortal_file 按后缀是 False（靠嗅探消歧）")
    finally:
        shutil.rmtree(TEST_DIR, ignore_errors=True)


# ------------------------------------------------------------------ 5. 打点链路
def section5():
    print("---- 5. 打点链路：第零类特征 / ai_models / ai_series / url")
    for tag, key in (("4.1a", "ai_mortal41a"), ("4.1b", "ai_mortal41b"), ("4.1c", "ai_mortal41c")):
        game = mortal.to_game(_report(tag))
        vals = feats.ai_values(game)
        yes = sorted(k for k, v in vals.items() if v == feats.YES)
        eq((len(vals), yes), (7, [key]), "model_tag %s -> 只有 %s = 是（第零类 7 项）" % (tag, key))
        eq(feats.ai_models_text(game), dict((("4.1a", "Mortal-4.1-避四"), ("4.1b", "Mortal-4.1-平衡"),
                                             ("4.1c", "Mortal-4.1-争一")))[tag],
           "辅助列 ai_models = 规范模型名")
        eq(feats.ai_series_text(game), "Mortal", "辅助列 ai_series = Mortal")
        eq(feats.paipu_url_of(game, "fb13c2973c0eabb3"),
           "https://mjai.ekyu.moe/report/fb13c2973c0eabb3.json", "打点行 url = Mortal 报告地址")
    eq(sorted(feats.ai_values({}).values()), [feats.NO] * len(feats.AI_KEYS), "天凤牌谱七项全「否」")
    eq(feats.viewer_seat({}), 0, "没有 meta / viewer_seat 时主视角按 0（NAGA / 天凤口径）")
    game = mortal.to_game(_report("4.1b"))
    eq(game["meta"].get("viewer_seat"), 0, "mortal 牌谱的播放初始主视角 = 被复盘的那一家（review.player_id）")
    # 用户 m06323 ① / m06560：找出第一个有决策概率表的帧（= 被复盘者自己的决策帧）
    hit = None
    for ri, frames in enumerate(game["naga"]["rounds"]):
        for ev in range(len(frames) - 1):
            if feats.ai_frame_keys(game, ri, ev):
                hit = (ri, ev)
                break
        if hit:
            break
    check(hit is not None, "合成报告里能找到带决策概率表的帧")
    ri, ev = hit
    recs = cli.fill_ai([{"log_id": game["log_id"], "round_index": ri, "ev_index": ev,
                         "seat": 0, "feats": {}}], [game])
    eq(recs[0]["feats"]["ai_mortal41b"], feats.YES, "fill_ai：被复盘那一家（= 决策者）的帧 = 是（用户 m06560）")
    eq((recs[0]["ai_models"], recs[0]["ai_series"]), ("Mortal-4.1-平衡", "Mortal"), "fill_ai 补辅助列")
    # 同一帧、别人（seat = 1）那一行 ⇒ 五项全「否」、辅助列空串（数据只属于决策者）
    other = cli.fill_ai([{"log_id": game["log_id"], "round_index": ri, "ev_index": ev,
                          "seat": 1, "feats": {}}], [game])[0]
    eq([other["feats"][k] for k in feats.AI_KEYS], [feats.NO] * len(feats.AI_KEYS),
       "不是决策者的行 ⇒ 七项全「否」（用户 m06560）")
    eq((other["ai_models"], other["ai_series"]), ("", ""), "不是决策者的行 ⇒ 辅助列空串")
    # 没有概率表的帧（第 2 局没有任何 entry）⇒ 就算 seat 是被复盘的那一家也全「否」
    nohit = cli.fill_ai([{"log_id": game["log_id"], "round_index": 1, "ev_index": 0,
                          "seat": 0, "feats": {}}], [game])[0]
    eq([nohit["feats"][k] for k in feats.AI_KEYS], [feats.NO] * len(feats.AI_KEYS),
       "该帧没有决策概率表 ⇒ 七项全「否」（用户 m06560）")
    eq(feats.ai_frame_keys(game, 1, 0), [], "第 2 局没有 entry ⇒ 没有带概率表的帧")


# ------------------------------------------------------------------ 6. 真实样例
def section6():
    print("---- 6. 真实样例（build\\_scratch\\mortal\\，存在时才跑）")
    files = sorted(glob.glob(os.path.join(SAMP_MORTAL, "*.json")))
    if not files:
        print("  （跳过：%s 里没有 .json 报告）" % SAMP_MORTAL)
        return
    for path in files:
        rid = os.path.basename(path)[:-5]
        game = mortal.game_from_file(path)
        eq(game["naga"]["kind"], "mortal", "%s：kind = mortal" % rid)
        eq(len(game["rounds"]), 12, "%s：半庄 12 局" % rid)
        eq(game["naga"]["report_id"], rid, "%s：report_id = 文件名" % rid)
        ent = game["naga"]["entries"]
        eq(ent["miss"], 0, "%s：所有决策点都定位到了触发帧（命中 %d 条）" % (rid, ent["hit"]))
        check(ent["hit"] > 100, "%s：命中数 = %d（只含被复盘那一家的决策）" % (rid, ent["hit"]))
        check(bool(game["naga"]["model"].startswith("Mortal-4.1-")),
              "%s：模型名 %s" % (rid, game["naga"]["model"]))
        n_dp = sum(1 for frames in game["naga"]["rounds"] for fr in frames if fr.get("dahai_pred"))
        n_hu = sum(1 for frames in game["naga"]["rounds"] for fr in frames if fr.get("huro"))
        check(n_dp > 0 and n_hu > 0, "%s：带打牌概率的帧 %d / 带副露概率的帧 %d" % (rid, n_dp, n_hu))
        # 检索范围 = 决策帧（按牌局选帧、覆盖四家），与「有 AI 概率向量」无关（用户 m06670）
        recs = []
        for ri in range(len(game["rounds"])):
            recs.extend(feats.records_for_round(game, ri))
        rseats = sorted(set(r["seat"] for r in recs))
        eq(rseats, [0, 1, 2, 3],
           "%s：打点帧覆盖四家的决策帧（共 %d 条，用户 m06670）" % (rid, len(recs)))
        ai_recs = [r for r in recs if any(r["feats"].get(k) == "是" for k in feats.AI_KEYS)]
        check(len(ai_recs) < len(recs) and all(r["seat"] == game["meta"]["viewer_seat"] for r in ai_recs),
              "%s：只有被复盘那一家的部分帧带 AI 概率向量（%d / %d，用户 m06670）"
              % (rid, len(ai_recs), len(recs)))
        bad = []
        for ri in range(len(game["rounds"])):
            errs, _n = replay.check_invariants(game, ri)
            if errs:
                bad.append((ri, errs[0]))
        eq(bad, [], "%s：12 局 replay 不变量 0 错误" % rid)
        ags = [e for rnd in game["rounds"] for e in rnd["events"] if e.get("type") == "agari"]
        check(bool(ags) and all(a["ten"] and a["ten"][1] > 0 for a in ags),
              "%s：%d 个和了局都算出了点数" % (rid, len(ags)))


def main():
    print("mortal_test：第 59 轮 Mortal 报告适配层（用户 m05937 ③）")
    section1()
    section2()
    section3()
    section4()
    section5()
    section6()
    print("=== 结果：通过 %d 项，失败 %d 项 ===" % (OK[0], BAD[0]))
    if BAD[0]:
        print("有失败用例")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
