# -*- coding: utf-8 -*-
r"""naga 正式测试（第 27 轮：NAGA 报告适配层 / 流局种类推断，用户 m00653）。

覆盖：
  1. infer_ryuukyoku_reason 的字面判定：三家和了 / 四家立直 / 四风连打 / 九种九牌 /
     四杠散了 / 流局满贯 / 荒牌流局（判定顺序 = 途中流局 -> 流局满贯 -> 荒牌流局）
  2. 合成报告端到端（荒牌流局）：种类 = ""、听牌家自己按向听数算（报告的 tenpais
     故意写成全 true 以证明我们不依赖它）、只给听牌家摊牌、replay 不变量 0 错误、
     帧对齐（naga 帧数 == 事件数）
  3. 合成报告端到端（四风连打）：种类 = kaze4，四家都不摊牌
  4. 真实样本（build\_scratch\naga_samples\ 里的 naga 报告，存在时才跑）：三处流局都是
     荒牌流局，听牌家 = [2] / [0,3] / [0]，且与报告 deltas 反推的收支一致
 5. 打点链路 / 存储集成（第 29 轮，用户 m00080 目标 3）：目录扫描认得 .naga（旧 .json / .json.gz）、
    log_id = 完整 report_id、每行 42 个特征（7 第零类 + 17 第一类 + 17 第二类 + 1 第三类）、第零类七项**按帧判定**
     （第 60 轮 / 用户 m06323 ①，口径按 m06560 更正：这一帧的决策者持有该模型的决策概率表才是「是」；
     天凤七项全「否」）、f_ai_* 入库、schema_version = 11、天凤 / NAGA / Mortal 混编进同一个库
  6. 本地服务接口（第 30 轮，用户 m01171 第 1 / 2 条）：POST /api/naga-convert 把浏览器
     手选 / 拖放进来的报告字节转成同构 JSON（与 naga.to_game 逐字节一致）、坏内容被拒；
     GET /api/paipu-browse 只列 data/paipu 里的子目录与牌谱文件（越界目录被拒）
 7. 第 36 轮（用户 m02227 / m02356 / m02357）：版本 v0.2.0 / schema 5 / 第一类 18 项
     （NAGA决策 置首、第 12 项 = 立直家（他家）一发巡，紧随立直家（他家）数量）
  8. 第 37 轮（用户 m02546）：NAGA 和了结算（符 / 点 / 役种）：符走 agari 引擎、
     点数取报告 deltas 扣本场 / 供托（与天凤 ten 同口径）、役种优先用报告的（报告缺时用引擎判的）
 9. 第 52 轮（用户 m04556 ②③）：第零类特征（f_ai_*，原「NAGA决策」改名移入）+
     辅助列 ai_models / ai_series、四种第零类检索方案；第 59 轮（用户 m05937 ①②）：v1.0.0 / schema 7 /
     第零类 5 项（补 Mortal-4.1-避四、Mortal-4.1-争一）；
     第 60 轮（用户 m06323 ①、口径按 m06560 更正）：第零类改为逐帧判定
     （这一帧的决策者是否有概率表）⇒ v1.1.0 / schema 8
 10. 第 56 轮（用户 m05392）：naga 下载判重 —— 官方来源发现本地已有同名文件就跳过（不发请求），
      ricochet 来源下载并覆盖同名文件；同一次下载里同一来源的重复 url 仍算重复
  11. 第 56 轮（用户 m05480）：天凤牌谱下载判重 —— 本地已有同名 <log_id>.tenhou（旧 .xml）就跳过、
      不发请求、不覆盖（`overwrite` 不再影响天凤牌谱）
  12. 第 57 轮（用户 m05545 ①② / m05806 ②）：mortal 报告下载（ekyu.moe，端点 /report/<id>.json）+
      本地后缀改成 .tenhou / .naga / .mortal-a|b|c（风格后缀 = review.model_tag：4.1a 避四 /
      4.1b 平衡 / 4.1c 争一）
 13. 第 59 轮（用户 m05937 ③）：mortal 报告也进分析链路 —— cli.report_kind 按后缀 / 内容嗅探分派
      （裸 .json 的 Mortal 报告不再被当成 NAGA）、resolve_inputs 认 .mortal-a|b|c
14. 第 62 轮（用户 m06801 / m06832）：新增「等待鸣牌」、kind = 'wait' 的决策帧、每行 40 个特征
15. 第 63 轮（用户 m07289）：关键帧 / wait 行的判据改成「这张牌**可能**被他家鸣牌」（碰 / 大明杠 =
    非立直家同种 ≥2；吃 = 只有下家、且吃后还剩可打的牌〔食替〕），wait 行改为「可能鸣牌的那一家各一行」；
    「等待鸣牌」编为**第三类特征**（1 项，不进检索下拉、不列进「当前帧特征」，改由面板底部的局面文字体现）、
    检索新增必选单选「出牌 / 鸣牌响应」、每行 42 个特征（7 第零类 + 17 第一类 + 17 第二类 + 1 第三类）、
    v1.3.1 / schema 10
16. 第 65 轮（用户 m08125 ①）：加杠副露的 4 张牌回归 —— 报告里的加杠事件只带「加进去的那一张」，
    replay 必须把它并回原来的碰（4 张同种牌），否则牌桌上会整组消失
17. 第 74 轮（用户 m09507）：新版 NAGA 报告（アナンタ / ウロボロス）—— 别名补 NAGA-避四 / NAGA-争一、
    第零类 5 项 → 7 项（共 42 项）、新模型的打牌分布取 dahai_detail（37 槽，末 3 槽 = 赤 5）折叠回 34 槽；
    新模型的「立直概率」= dahai_detail 的立直支之和（官方 viewer 口径，与 dahai_pred 的两支相加同源）；
    schema 10 → 11

运行：
  python test\naga_test.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mjscore import ai_models, feats, naga, paths, replay  # noqa: E402
import urllib.parse  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OK = [0]
BAD = [0]
SAMP = os.path.join(ROOT, "build", "_scratch", "naga_samples")


def check(cond, label):
    if cond:
        OK[0] += 1
        print("  OK   %s" % label)
    else:
        BAD[0] += 1
        print("  FAIL %s" % label)


def eq(got, want, label):
    check(got == want, "%s（得到 %r，期望 %r）" % (label, got, want))


class FakeTable(object):
    """只给推断函数用的最小 table（rivers / hands）。"""

    def __init__(self, rivers=None, hands=None):
        self.rivers = rivers if rivers is not None else [[], [], [], []]
        self.hands = hands if hands is not None else [[], [], [], []]


def _tids(kinds):
    return [4 * k for k in kinds]


# ------------------------------------------------------------------ 1. 字面判定
def section1():
    print("---- 1. infer_ryuukyoku_reason 字面判定")
    ends = [{"type": "ryukyoku"}]
    name_of = naga.infer_ryuukyoku_reason

    # 三家和了：局末同时出现三家以上和了
    hora3 = [{"type": "hora", "actor": 1, "target": 0},
             {"type": "hora", "actor": 2, "target": 0},
             {"type": "hora", "actor": 3, "target": 0}]
    eq(name_of([], hora3), "tripleRon", "三家和了（≥3 条 hora）")
    eq(name_of([{"type": "dahai"}], hora3 + [{"type": "hora"}]), "tripleRon", "四家和了也归三家和了")

    # 四家立直：四条 reach_accepted
    r4 = [{"type": "reach", "actor": i} for i in range(4)] + \
         [{"type": "reach_accepted", "actor": i} for i in range(4)]
    eq(name_of(r4, ends), "reach4", "四家立直")

    # 四风连打：无人鸣牌 + 恰好四张弃牌 + 同一张风牌
    kaze = [{"type": "tsumo", "actor": i} for i in range(4)] + \
           [{"type": "dahai", "actor": i, "pai": "N"} for i in range(4)]
    eq(name_of(kaze, ends), "kaze4", "四风连打")
    eq(name_of([{"type": "tsumo", "actor": i} for i in range(4)] +
               [{"type": "dahai", "actor": i, "pai": "N"} for i in range(4)] +
               [{"type": "pon", "actor": 3, "target": 1}], ends),
       "", "四人打同一张风牌但有人鸣牌（不算四风连打）")
    eq(name_of([{"type": "tsumo", "actor": i} for i in range(3)] +
               [{"type": "dahai", "actor": i, "pai": "N"} for i in range(3)], ends),
       "", "只有三家打出风牌（不算四风连打）")
    eq(name_of([{"type": "dahai", "actor": i, "pai": "5m"} for i in range(4)], ends),
       "", "四张同样的数牌不是四风连打")

    # 九种九牌：无人鸣牌、宣言者还没打过牌、手里么九牌 >= 9 种
    yao_hand = _tids([0, 8, 9, 17, 18, 26, 27, 28, 29, 31, 32, 33, 12, 13])   # 13 种么九 + 4p/5p
    tbl = FakeTable(hands=[[], [], [], []])
    tbl.hands[2] = yao_hand
    eq(name_of([{"type": "tsumo", "actor": 2, "pai": "5p"}], ends, tbl), "yao9", "九种九牌")
    tbl2 = FakeTable(hands=[[], [], [], []])
    tbl2.hands[2] = _tids([0, 8, 9, 17, 18, 26, 27, 28, 13, 14, 15, 16, 20])   # 只有 8 种么九
    eq(name_of([{"type": "tsumo", "actor": 2, "pai": "5p"}], ends, tbl2), "", "么九牌只有 8 种（不算九种九牌）")
    eq(name_of([{"type": "tsumo", "actor": 2, "pai": "5p"},
                {"type": "dahai", "actor": 2, "pai": "5p"}], ends, tbl),
       "", "九种九牌要求宣言者还没打过牌")

    # 四杠散了：四个以上杠、不是一家独杠
    eq(name_of([{"type": "ankan", "actor": 0}, {"type": "kakan", "actor": 1},
                {"type": "ankan", "actor": 0}, {"type": "daiminkan", "actor": 2}], ends),
       "rck4", "四杠散了（两人以上开杠）")
    eq(name_of([{"type": "ankan", "actor": 0}, {"type": "kakan", "actor": 0},
                {"type": "ankan", "actor": 0}], ends), "", "同一家三个杠（不够四杠）")

    # 流局满贯：某家牌河全是么九牌且一张都没被鸣走
    tbl3 = FakeTable(rivers=[_tids([0, 27, 33, 8]), [], [], []])
    eq(name_of([], ends, tbl3), "nm", "流局满贯（牌河全么九、没人鸣）")
    tbl4 = FakeTable(rivers=[_tids([0, 27, 33, 8]), [], [], []])
    eq(name_of([{"type": "chi", "actor": 1, "target": 0}], ends, tbl4), "", "牌河被鸣过（不算流局满贯）")
    tbl5 = FakeTable(rivers=[_tids([0, 27, 33, 4]), [], [], []])
    eq(name_of([], ends, tbl5), "", "牌河里有中张（不算流局满贯）")

    # 荒牌流局：都不是
    tbl6 = FakeTable(rivers=[_tids([0, 4, 8]), _tids([9, 13, 17]), _tids([18, 22]), _tids([27, 31, 4])])
    eq(name_of([], ends, tbl6), "", "荒牌流局")


# ------------------------------------------------------------------ 合成报告
def _report(tehais, events, end_msgs, dora="3p", scores=None, oya=0):
    """拼一份最小可用报告：pred = [[start_kyoku 帧, 逐帧事件...]]。"""
    start = {
        "type": "start_kyoku", "bakaze": "E", "kyoku": 1, "honba": 0, "kyotaku": 0,
        "oya": oya, "dora_marker": dora, "scores": scores or [25000] * 4,
        "tehais": tehais, "end_msgs": end_msgs,
    }
    frames = [{"info": {"msg": start}}]
    for msg in events:
        frames.append({"info": {"msg": msg}})
    return {"pred": [frames], "player_info": {"name": ["A", "B", "C", "D"]},
            "naga_types": {"0": "ニシキ"}, "naga_version": [2, 2],
            "report_info": {"hanchan": True}}


def _dump(game, evs):
    st = replay.initial_state(game, 0)
    for ev in evs:
        replay.apply_event(st, ev)
    return st


# --------------------------------------------------- 2. 端到端：荒牌流局 + 听牌自算
TEHAIS_EXHAUST = [
    ["1m", "1m", "1m", "2m", "2m", "2m", "3m", "3m", "3m", "5m", "5p", "5s", "7s"],
    ["4m", "4m", "4m", "5m", "5m", "5m", "6m", "6m", "6m", "7p", "8p", "1s", "3s"],
    ["7p", "7p", "7p", "8p", "8p", "8p", "9p", "9p", "9p", "1s", "1s", "1s", "5p"],
    ["9m", "9m", "9m", "1p", "1p", "1p", "2p", "2p", "2p", "2s", "4s", "8s", "9s"],
]


def section2():
    print("---- 2. 合成报告：荒牌流局（听牌自己算，不听报告的 tenpais）")
    evs = [{"type": "tsumo", "actor": 0, "pai": "4p"}, {"type": "dahai", "actor": 0, "pai": "4p"},
           {"type": "tsumo", "actor": 1, "pai": "6p"}, {"type": "dahai", "actor": 1, "pai": "6p"},
           {"type": "tsumo", "actor": 2, "pai": "4s"}, {"type": "dahai", "actor": 2, "pai": "4s"},
           {"type": "tsumo", "actor": 3, "pai": "6s"}, {"type": "dahai", "actor": 3, "pai": "6s"}]
    # tenpais 故意全 true（真实报告就是这样，与 deltas 自相矛盾）；deltas = 只有 2 号家听牌
    ends = [{"type": "ryukyoku", "deltas": [-1000, -1000, 3000, -1000],
             "scores": [24000, 24000, 28000, 24000], "ba": [0, 0],
             "tenpais": [True, True, True, True]}]
    game = naga.to_game(_report(TEHAIS_EXHAUST, evs, ends))
    rnd = game["rounds"][0]
    end = rnd["events"][-1]
    eq(end["type"], "ryuukyoku", "局末事件类型")
    eq(end["reason"], "", "荒牌流局的 reason 是空串")
    eq(end["who"], None, "荒牌流局没有宣言者")
    tenpai = [i for i in range(4) if end["hands"][i]]
    eq(tenpai, [2], "听牌家 = [2]（不理会报告的 tenpais 全 true）")
    eq([None if end["hands"][i] is None else len(end["hands"][i]) for i in range(4)],
       [None, None, 13, None], "只有听牌家摊开 13 张牌")
    eq(list(end["gain"]), [-1000, -1000, 3000, -1000], "收支用报告 deltas")
    eq(len(game["naga"]["rounds"][0]), len(rnd["events"]), "帧对齐：naga 帧数 == 事件数")
    errs, n = replay.check_invariants(game, 0)
    eq((len(errs), n), (0, 9), "replay 不变量 0 错误（9 帧）")
    st = _dump(game, rnd["events"])
    eq(st["desc"], "流局（荒牌流局）", "局末描述")
    eq(st["scores"], [24000, 24000, 28000, 24000], "局末分数 = before + gain")
    eq(sorted(st["reveal"]), [2], "摊牌名单 = 听牌家")


# --------------------------------------------------- 3. 端到端：四风连打（途中流局）
TEHAIS_KAZE = [
    ["E", "1m", "1m", "1m", "2m", "2m", "2m", "3m", "3m", "3m", "4m", "4m", "4m"],
    ["E", "1p", "1p", "1p", "2p", "2p", "2p", "3p", "3p", "3p", "4p", "4p", "4p"],
    ["E", "1s", "1s", "1s", "2s", "2s", "2s", "3s", "3s", "3s", "4s", "4s", "4s"],
    ["E", "5m", "5m", "5m", "6m", "6m", "6m", "7m", "7m", "7m", "8m", "8m", "8m"],
]


def section3():
    print("---- 3. 合成报告：四风连打（途中流局，四家都不摊牌）")
    evs = []
    for seat, pai in enumerate(("9m", "9p", "9s", "9m")):
        evs.append({"type": "tsumo", "actor": seat, "pai": pai})
        evs.append({"type": "dahai", "actor": seat, "pai": "E"})
    ends = [{"type": "ryukyoku", "deltas": [0, 0, 0, 0], "scores": [25000] * 4,
             "ba": [0, 1], "tenpais": [True, True, True, True]}]
    game = naga.to_game(_report(TEHAIS_KAZE, evs, ends))
    rnd = game["rounds"][0]
    end = rnd["events"][-1]
    eq(end["reason"], "kaze4", "四风连打 reason = kaze4")
    eq(end["who"], None, "四风连打没有宣言者")
    eq(end["hands"], [None, None, None, None], "途中流局四家都不摊牌")
    errs, n = replay.check_invariants(game, 0)
    eq((len(errs), n), (0, 9), "replay 不变量 0 错误（9 帧）")
    st = _dump(game, rnd["events"])
    eq(st["desc"], "流局（四風連打）", "局末描述用 REASON_NAME")
    eq(st["reveal"], [], "途中流局不摊牌")


# --------------------------------------------------- 4. 真实样本（有才跑）
SAMPLES = [
    ("3180043a69ad5cbf353fba1bde67491ff135d60f7902cbe654db9057f40ee4e0v2_2.json.gz",
     {7: [2], 14: [0, 3]}),
    ("60b5c2ad3d716fab830cc2ad5ad3053fe48cde77cb02094cc2fb50cb04e4675ev2_2.json.gz", {}),
    ("9ace0d86c7a7681b914064d9282ebcc53f6d76b458e51ce0197c574c9a01a641v2_2.json.gz",
     {0: [0]}),
]


def section4():
    print("---- 4. 真实样本的流局（build\\_scratch\\naga_samples\\）")
    found = 0
    for fn, want in SAMPLES:
        path = os.path.join(SAMP, fn)
        if not os.path.exists(path):
            print("  SKIP %s（样本不在）" % fn[:16])
            continue
        found += 1
        game = naga.game_from_file(path)
        got = {}
        bad = 0
        for ri, rnd in enumerate(game["rounds"]):
            errs, _n = replay.check_invariants(game, ri)
            bad += len(errs)
            for ev in rnd["events"]:
                if ev.get("type") == "ryuukyoku":
                    got[ri] = [i for i in range(4) if ev["hands"][i]]
                    check(ev["reason"] == "", "%s 局%d 是荒牌流局" % (fn[:8], ri + 1))
        eq(got, want, "%s 流局局的听牌家" % fn[:16])
        eq(bad, 0, "%s 全 %d 局不变量 0 错误" % (fn[:16], len(game["rounds"])))
    if not found:
        print("  SKIP 没有样本，第 4 节未执行")


# ------------------------------------------- 5. 打点链路 / 存储集成（第 29 轮，用户 m00080 目标 3）
RID_S5 = "3180043a69ad5cbf353fba1bde67491ff135d60f7902cbe654db9057f40ee4e0v2_2"


def section5():
    print("---- 5. 打点链路 / 存储集成（42 个特征 + 第零类 7 项 + 天凤/NAGA 混编）")
    import json as _json
    import shutil
    from mjscore import cli, feats, store

    # 临时目录放在 test/_tmp 下（沙箱禁止写系统 TEMP）
    tmp = os.path.join(ROOT, "test", "_tmp", "naga_s5")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        path = os.path.join(tmp, RID_S5 + ".json")
        evs = [{"type": "tsumo", "actor": 0, "pai": "4p"}, {"type": "dahai", "actor": 0, "pai": "4p"},
               {"type": "tsumo", "actor": 1, "pai": "6p"}, {"type": "dahai", "actor": 1, "pai": "6p"}]
        ends = [{"type": "ryukyoku", "deltas": [-1000, 1000, 0, 0], "scores": [24000, 26000, 25000, 25000],
                 "tenpais": [False, True, False, False], "rank2seat": [0, 1, 2, 3],
                 "seat2rank": [0, 1, 2, 3]}]
        rep = _report(TEHAIS_EXHAUST, evs, ends)
        # 用户 m06323 ① / m06560：第零类按帧判定 —— 给 0 号家那次摸牌的帧（帧 1 = ev_index 0）挂一份打牌概率表
        # （扁平列表会被 naga._model_values 复制给所有模型）；1 号家的帧（帧 3）故意不挂，
        # 所以那一行应判「否」（数据只属于这一帧的决策者）。
        rep["pred"][0][1]["dahai_pred"] = [[3000] + [0] * 33]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_json.dumps(rep, ensure_ascii=False))

        eq(naga.is_naga_file(path), True, "is_naga_file 认得 .json")
        eq(cli.file_log_id(path), RID_S5, "file_log_id = 完整 report_id（小写、不剥 v2_2）")
        eq(cli.resolve_inputs([tmp]), [path], "resolve_inputs 的目录扫描认得 .json")
        game = cli.game_from_file(path)
        eq(game["log_id"], RID_S5, "game_from_file 补回 log_id")
        eq(game["path"], os.path.abspath(path), "game_from_file 补回绝对路径")
        eq(bool(game.get("naga")), True, "game 带 naga 键")

        recs = feats.records_for_game(game)
        check(len(recs) > 0, "NAGA 报告打出 %d 行" % len(recs))
        eq(len(recs[0]["feats"]), 42, "每行 42 个特征（7 第零类 + 17 第一类 + 17 第二类 + 1 第三类）")
        eq(recs[0]["feats"]["ai_balance"], "是",
           "决策者（0 号家）的帧 + 该帧有概率表 → NAGA-平衡 分析 = 是（用户 m06560）")
        eq((recs[0]["feats"]["ai_superhuro"], recs[0]["feats"]["ai_mortal41a"],
            recs[0]["feats"]["ai_mortal41b"], recs[0]["feats"]["ai_mortal41c"]), ("否", "否", "否", "否"),
           "报告里只有ニシキ ⇒ 其余六项第零类 = 否（用户 m05937 ② / m09507）")
        eq((recs[0]["ai_models"], recs[0]["ai_series"]), ("NAGA-平衡", "NAGA"), "决策者那一行辅助列 = 规范名 / 系列")
        eq(len(recs), 3, "两次非自摸摸牌各打一行 + 1 行鸣牌响应帧（6p 下家能吃，用户 m07289）")
        eq((recs[2]["kind"], recs[2]["seat"], recs[2]["feats"]["meld_wait"]),
           ("wait", 2, "是"), "出牌 6p 后下家（2 号家）能吃 ⇒ 该家一行鸣牌响应帧，等待鸣牌 = 是")
        eq((recs[0]["kind"], recs[0]["seat"], recs[0]["feats"]["meld_wait"]), ("draw", 0, "否"),
           "摸牌帧的「等待鸣牌」= 否（第三类特征，用户 m07289）")
        eq([recs[1]["feats"][k] for k in feats.AI_KEYS], [feats.NO] * len(feats.AI_KEYS),
           "1 号家的决策帧没有概率表 ⇒ 七项全「否」（用户 m06560）")
        eq((recs[1]["ai_models"], recs[1]["ai_series"]), ("", ""), "没有概率表的那一行辅助列为空串")
        check(recs[0]["url"].startswith("https://naga.dmv.nico/htmls/report_viewer.html?report_id="),
              "url 指向 NAGA 观看页（%s…）" % recs[0]["url"][:58])

        # fill_ai：node / python / fixture 三条路径统一补第零类 7 项 + 两个辅助列
        th_log = "2026083020gm-00a9-0000-e9ce1efe"
        fake = [{"log_id": th_log, "feats": {}},
                {"log_id": RID_S5, "round_index": 0, "ev_index": 0, "seat": 0, "feats": {}},
                {"log_id": RID_S5, "round_index": 0, "ev_index": 2, "seat": 1, "feats": {}}]
        cli.fill_ai(fake, [game, {"log_id": th_log}])
        eq([r["feats"]["ai_balance"] for r in fake], ["否", "是", "否"],
           "fill_ai 按帧判定：天凤行 = 否 / NAGA 决策者帧 = 是 / 无概率表的帧 = 否（用户 m06560）")
        eq((fake[0]["ai_models"], fake[0]["ai_series"]), ("", ""), "天凤行两个辅助列为空串")
        eq((fake[1]["ai_models"], fake[1]["ai_series"]), ("NAGA-平衡", "NAGA"), "NAGA 行辅助列 = 规范名 / 系列")
        eq((fake[2]["ai_models"], fake[2]["ai_series"]), ("", ""), "无概率表的帧两个辅助列为空串")
        eq(cli.file_log_id(th_log + ".xml"), th_log, "file_log_id 对天凤 xml 仍用文件名")

        # 入库：schema 11 + f_ai_*（按帧判定）+ 42 项
        db = os.path.join(tmp, "an.sqlite")
        res = cli.analyze([path], db=db, tool="python")
        eq(res["tool"], "python", "analyze 用 python 打点")
        eq((res["sources"], res["rounds"]), (1, 1), "入库 1 个来源 / 1 局")
        conn = store.connect(db, create=False)
        try:
            eq(store.get_meta(conn).get("schema_version"), str(store.SCHEMA_VERSION),
               "meta.schema_version = %d（第 74 轮：第零类 7 项 + 新 NAGA 两模型）" % store.SCHEMA_VERSION)
            eq(store.source_ids(conn), {RID_S5}, "source.log_id = 完整 report_id")
            dist = dict(conn.execute("SELECT f_ai_balance, COUNT(*) FROM frame GROUP BY f_ai_balance").fetchall())
            eq(dist, {"是": 1, "否": len(recs) - 1},
               "f_ai_balance：决策者帧 = 是（1 行）/ 其余 %d 行 = 否（用户 m06560）" % (len(recs) - 1))
            _other = conn.execute("SELECT COUNT(*) FROM frame WHERE f_ai_superhuro <> '否'"
                                  " OR f_ai_naga_avoid4 <> '否' OR f_ai_naga_aggressive <> '否'"
                                  " OR f_ai_mortal41a <> '否' OR f_ai_mortal41b <> '否'"
                                  " OR f_ai_mortal41c <> '否'").fetchone()[0]
            eq(_other, 0, "该样本只含「ニシキ」⇒ 其余六项第零类全为「否」")
            idx, seat = conn.execute("SELECT idx, seat FROM frame WHERE f_ai_balance = '是' LIMIT 1").fetchone()
            one = store.query_detail(conn, idx)
            eq(len(one["feats"]), 42, "query_detail 展开 42 个特征")
            eq(one["feats"]["ai_balance"], "是", "库里的 NAGA-平衡 分析 = 是")
            ff = store.frame_feats(conn, RID_S5, one["round_index"], one["frame_index"], seat)
            eq(len((ff or {}).get("feats") or {}), 42, "frame_feats 返回 42 项特征")
            eq((ff or {}).get("feats", {}).get("ai_balance"), "是", "frame_feats 里的 NAGA-平衡 分析 = 是")
            eq(store.list_feature_values(conn, "ai_balance"),
               [{"value": "否", "count": len(recs) - 1}, {"value": "是", "count": 1}],
               "list_feature_values('ai_balance') = 否 × %d / 是 × 1" % (len(recs) - 1))
            idxs = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")]
            check("frame_ai" in idxs, "frame_ai 索引已建")

            # 混编：把同一帧改写成天凤来源（第零类七项 = 否）插进同一个库
            row = dict(recs[0])
            row["log_id"] = th_log
            row["feats"] = dict(row["feats"])
            for _k in ("ai_balance", "ai_superhuro", "ai_naga_avoid4", "ai_naga_aggressive",
                       "ai_mortal41a", "ai_mortal41b", "ai_mortal41c"):
                row["feats"][_k] = "否"
            row["ai_models"] = ""
            row["ai_series"] = ""
            store.insert_records(conn, [row], tool="python", log_path=th_log + ".xml",
                                 added_at="2026-01-01 00:00:00")
            dist = dict(conn.execute("SELECT f_ai_balance, COUNT(*) FROM frame GROUP BY f_ai_balance").fetchall())
            eq(dist, {"是": 1, "否": len(recs)}, "同一个库里天凤（否）+ NAGA（1 帧是）混编")
            eq(store.list_feature_values(conn, "ai_balance"),
               [{"value": "否", "count": len(recs)}, {"value": "是", "count": 1}],
               "list_feature_values 按值排序（否 / 是）")
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def section6():
    """第 30 轮（用户 m01171 第 1 / 2 条）：本地服务的 NAGA 上传转换 + 牌谱目录浏览接口。"""
    import json as _json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from mjscore import server

    def _sl(x):
        return str(x).replace("\\", "/")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    old_log = server.Handler.log_message
    server.Handler.log_message = lambda *a, **k: None
    try:
        def req(path, data=None):
            rq = urllib.request.Request(base + path, data=data, method="GET" if data is None else "POST")
            def _read(resp, code):
                body = resp.read().decode("utf-8")
                try:
                    return code, dict(resp.headers), _json.loads(body)
                except ValueError:      # 静态资源（js / css）不是 JSON
                    return code, dict(resp.headers), body

            try:
                with urllib.request.urlopen(rq, timeout=300) as resp:
                    return _read(resp, resp.status)
            except urllib.error.HTTPError as exc:
                return _read(exc, exc.code)

        # 6.1 静态资源不许缓存（免得浏览器拿着旧 js，用户 m01171 排查时踩过）
        code, headers, _body = req("/web/js/app.js")
        check(code == 200 and "no-store" in (headers.get("Cache-Control") or ""),
              "静态 js 带 Cache-Control: no-store（%r）" % headers.get("Cache-Control"))

        # 6.2 GET /api/paipu-browse：前缀固定 data/paipu
        code, _h, d = req("/api/paipu-browse")
        eq(code, 200, "GET /api/paipu-browse 正常返回")
        eq(d.get("root"), os.path.abspath(paths.paipu_root()), "浏览根 = paths.paipu_root()")
        check(d.get("root_rel") in (d.get("root"), "data/paipu"), "root_rel = %r" % d.get("root_rel"))
        check(isinstance(d.get("dirs"), list) and d["dirs"] and all(
            "data/paipu" in _sl(x) and ".." not in _sl(x) for x in d["dirs"]),
            "子目录都在牌谱根里（%r）" % (d.get("dirs") or [])[:1] + "…" if False else
            "子目录都在牌谱根里（%d 个）" % len(d.get("dirs") or []))
        exts = tuple(naga.NAGA_SUFFIXES) + tuple(paths.TENHOU_SUFFIXES)
        check(all(str(f).lower().endswith(exts) for f in (d.get("files") or [])),
              "文件列表只含 .tenhou / .xml / .mjlog / .naga / .json.gz / .json（%d 个）" % len(d.get("files") or []))
        code, _h, bad = req("/api/paipu-browse?dir=" + urllib.parse.quote("web"))
        eq(code, 400, "越界目录（web/）被拒")
        check("只能浏览牌谱目录" in (bad.get("error") or ""), "越界提示：%s" % bad.get("error"))
        code, _h, _bad2 = req("/api/paipu-browse?dir=" + urllib.parse.quote("data/paipu/no-such-dir"))
        eq(code, 400, "不存在的目录被拒")

        # 6.3 POST /api/naga-convert：浏览器手选 / 拖放的文件没有磁盘路径
        sample = os.path.join(SAMP, "3180043a69ad5cbf353fba1bde67491ff135d60f7902cbe654db9057f40ee4e0v2_2.json.gz")
        if not os.path.isfile(sample):
            check(True, "没有样本 %s，跳过上传转换断言" % os.path.basename(sample))
        else:
            raw = open(sample, "rb").read()
            name = os.path.basename(sample)
            code, _h, up = req("/api/naga-convert?name=" + urllib.parse.quote(name), raw)
            eq(code, 200, "POST /api/naga-convert 正常返回")
            eq(up.get("naga"), True, "返回 naga=true")
            check(isinstance(up.get("text"), str) and up["text"].startswith("{"), "返回的是 JSON 文本")
            game = _json.loads(up["text"])
            eq(game["log_id"], naga.report_id_of_path(name), "log_id = 完整 report_id（含 v2_2）")
            eq(game.get("path"), "", "上传的文件没有磁盘路径，path 留空")
            want = naga.to_game(naga.load_report(raw), report_id=naga.report_id_of_path(name))
            same = up["text"] == _json.dumps(want, ensure_ascii=False, separators=(",", ":"))
            check(same, "转换结果与 naga.to_game 逐字节一致（%d B）" % len(up["text"]))
        code, _h, _e = req("/api/naga-convert?name=x.json", b"")
        eq(code, 400, "空体被拒（%d）" % code)
        code, _h, err = req("/api/naga-convert?name=x.json", b'{"hello":1}')
        eq(code, 400, "不是 NAGA 报告被拒")
        check("NAGA 报告解析失败" in (err.get("error") or ""), "错误提示：%s" % err.get("error"))
        eq(server.MAX_UPLOAD, 32 * 1024 * 1024, "上传上限 32 MB")

        # 6.4 老接口没被影响
        code, _h, sc = req("/api/scan?dir=" + urllib.parse.quote("data/paipu") + "&kind=all")
        eq(code, 200, "GET /api/scan?kind=all 仍正常")
        check(isinstance(sc.get("files"), list), "scan 返回文件列表（%d 个）" % len(sc.get("files") or []))
    finally:
        server.Handler.log_message = old_log
        httpd.shutdown()
        httpd.server_close()


# ------------------------------------------- 7. 和了结算（第 37 轮，用户 m02546）
TEHAIS_TANYAO = [
    ["2m", "3m", "4m", "5m", "6m", "7m", "2p", "3p", "4p", "6p", "7p", "8p", "8s"],
    ["1p", "1p", "1p", "9s", "9s", "9s", "E", "E", "E", "P", "P", "1s", "1s"],
    ["1m", "1m", "1m", "9m", "9m", "9m", "C", "C", "C", "F", "F", "2s", "2s"],
    ["9p", "9p", "9p", "S", "S", "S", "N", "N", "N", "W", "W", "3s", "3s"],
]

# 自家（亲）摸 8s 自摸断幺九；他家手牌不参与结算
HORA_TANYAO = {"type": "hora", "actor": 0, "target": 0, "pai": "8s",
               "deltas": [3000, -1000, -1000, -1000], "scores": [28000, 24000, 24000, 24000],
               "ba": [0, 0], "hu": 30, "fan": 2, "raw_delta": 3000,
               "yakus": [], "yakus_detail": [], "yakuman": []}

TEHAIS_TARGET0 = [
    ["1m", "9p", "9p", "9p", "E", "E", "E", "1s", "1s", "1s", "P", "P", "8s"],
    ["2m", "3m", "4m", "5m", "6m", "7m", "2p", "3p", "4p", "5p", "6p", "7p", "8s"],
    ["1p", "1p", "1p", "9s", "9s", "9s", "C", "C", "C", "F", "F", "2s", "2s"],
    ["9p", "9p", "9p", "S", "S", "S", "N", "N", "N", "W", "W", "3s", "3s"],
]

TEHAIS_NOYAKU = [
    ["1m", "1m", "1m", "9p", "9p", "9p", "E", "E", "E", "P", "P", "5s", "5s"],
    ["1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "1s", "2s", "3s", "5s"],
    ["1p", "1p", "1p", "9s", "9s", "9s", "C", "C", "C", "F", "F", "2s", "2s"],
    ["9p", "9p", "9p", "S", "S", "S", "N", "N", "N", "W", "W", "3s", "3s"],
]

# 七対子（1m1m 2m2m 1p1p 2p2p 1s1s 2s2s 9s + 摸 9s）：役 22 是 2 番，
# 用来验证「报告只给役种 id 时不能假设每项 1 番」（用户 m02801 ②）
TEHAIS_CHIITOI = [
    ["1m", "1m", "2m", "2m", "1p", "1p", "2p", "2p", "1s", "1s", "2s", "2s", "9s"],
    ["3m", "3m", "4m", "4m", "3p", "3p", "4p", "4p", "3s", "3s", "4s", "4s", "8s"],
    ["5m", "5m", "6m", "6m", "5p", "5p", "6p", "6p", "5s", "5s", "6s", "6s", "7s"],
    ["7m", "7m", "7m", "8m", "8m", "9m", "9m", "7p", "7p", "8p", "8p", "9p", "9p"],
]


# 一炮双响（ダブロン）：同一张 8s 被两家同时荣和（用户 m02984 ①）
TEHAIS_DBL = [
    ["1m", "9p", "9p", "9p", "E", "E", "E", "1s", "1s", "1s", "P", "P", "8s"],
    ["2m", "3m", "4m", "5m", "6m", "7m", "2p", "3p", "4p", "5p", "6p", "7p", "8s"],
    ["2m", "3m", "4m", "5m", "6m", "7m", "2p", "3p", "4p", "6p", "7p", "8p", "8s"],
    ["S", "S", "S", "N", "N", "N", "W", "W", "W", "3s", "3s", "3s", "7z"],
]


def section7():
    print("---- 7. 和了结算（符 / 点 / 役种，报告缺时用引擎补）（第 37 轮，用户 m02546）")

    # 7.1 自摸：报告没给役种 -> 用引擎判的；符 / 点由我们算
    evs = [{"type": "tsumo", "actor": 0, "pai": "8s"}]
    game = naga.to_game(_report(TEHAIS_TANYAO, evs, [dict(HORA_TANYAO)]))
    end = game["rounds"][0]["events"][-1]
    eq(end["type"], "agari", "7.1 和了事件")
    eq(end["winner"], 0, "7.1 和了家 = 0")
    eq(end["fromWho"], 0, "7.1 自摸（fromWho == winner）")
    eq(end["ten"], [30, 3000], "7.1 符 / 点：30 符 3000 点（＝ deltas - 本场 - 供托）")
    ids = [int(y[0]) for y in end["yaku"]]
    check(0 in ids, "7.1 报告没给役种时用引擎判的（含門前清自摸和 0）")
    check(8 in ids, "7.1 引擎判出断幺九 8")
    eq(end["yakuman"], [], "7.1 非役満")

    # 7.2 本场 / 供托要扣掉（与天凤 ten 同口径）
    hb = dict(HORA_TANYAO)
    hb["ba"] = [1, 1]
    hb["deltas"] = [3000 + 300 + 1000, -1000, -1000, -1000]
    game = naga.to_game(_report(TEHAIS_TANYAO, evs, [hb]))
    end = game["rounds"][0]["events"][-1]
    eq(end["ten"], [30, 3000], "7.2 1 本场 + 1 根供托已扣掉（4300 -> 3000）")

    # 7.3 报告给了役种 -> 报告为准（引擎不再追加）
    hd = dict(HORA_TANYAO)
    hd["yakus"] = [8]
    hd["yakus_detail"] = [[8, 1]]
    game = naga.to_game(_report(TEHAIS_TANYAO, evs, [hd]))
    end = game["rounds"][0]["events"][-1]
    eq(end["yaku"], [[8, 1]], "7.3 报告给了役种就用报告的（不追加引擎的自摸）")

    # 7.4 荣和且放铳家坐在 0 号位（target == 0）：不能当成自摸
    evs = [{"type": "tsumo", "actor": 0, "pai": "1m"}, {"type": "dahai", "actor": 0, "pai": "8s"}]
    hr = {"type": "hora", "actor": 1, "target": 0, "pai": "8s",
          "deltas": [-1300, 1300, 0, 0], "scores": [23700, 26300, 25000, 25000],
          "ba": [0, 0], "hu": 40, "fan": 1, "raw_delta": 1300,
          "yakus": [1], "yakus_detail": [[1, 1]], "yakuman": []}
    game = naga.to_game(_report(TEHAIS_TARGET0, evs, [hr]))
    end = game["rounds"][0]["events"][-1]
    eq(end["winner"], 1, "7.4 和了家 = 1")
    eq(end["fromWho"], 0, "7.4 放铳家 = 0（target 0 不能被 or 兜底）")
    eq(end["ten"], [40, 1300], "7.4 荣和 40 符 1300 点（报告缺立直消息时用役种里的立直补上）")
    eq(end["yaku"], [[1, 1]], "7.4 役种用报告的立直")
    errs, _n = replay.check_invariants(game, 0)
    eq(len(errs), 0, "7.4 replay 不变量 0 错误")

    # 7.5 引擎算不出（放铳家打出的牌并不成和）-> 符回退用报告的 hu，点数照算
    #      （荣和的 win 取放铳家牌河最后一张，所以这里故意打一张不和牌的 1m）
    evs = [{"type": "tsumo", "actor": 0, "pai": "5s"}, {"type": "dahai", "actor": 0, "pai": "1m"}]
    hn = {"type": "hora", "actor": 1, "target": 0, "pai": "1m",
          "deltas": [-1000, 1000, 0, 0], "scores": [24000, 26000, 25000, 25000],
          "ba": [0, 0], "hu": 30, "fan": 1, "raw_delta": 1000,
          "yakus": [], "yakus_detail": [], "yakuman": []}
    game = naga.to_game(_report(TEHAIS_NOYAKU, evs, [hn]))
    end = game["rounds"][0]["events"][-1]
    eq(end["ten"], [30, 1000], "7.5 引擎算不出时符用报告的 hu（点数照算）")
    eq(end["yaku"], [], "7.5 引擎算不出且报告没给役种 -> 空役种")

    # 7.10 一炮双响（ダブロン）：报告里两条 hora，两家都要算出来（用户 m02984 ①）
    evs = [{"type": "tsumo", "actor": 0, "pai": "1m"}, {"type": "dahai", "actor": 0, "pai": "8s"}]
    h1 = {"type": "hora", "actor": 1, "target": 0, "pai": "8s",
          "deltas": [-4200, 4200, 0, 0], "scores": [20800, 29200, 25000, 25000],
          "ba": [1, 1], "hu": 40, "fan": 1, "raw_delta": 2900,
          "yakus": [], "yakus_detail": [], "yakuman": []}
    h2 = {"type": "hora", "actor": 2, "target": 0, "pai": "8s",
          "deltas": [-1300, 0, 1300, 0], "scores": [19500, 29200, 26300, 25000],
          "ba": [1, 1], "hu": 40, "fan": 1, "raw_delta": 1300,
          "yakus": [], "yakus_detail": [], "yakuman": []}
    game = naga.to_game(_report(TEHAIS_DBL, evs, [h1, h2]))
    ends = [ev for ev in game["rounds"][0]["events"] if ev.get("type") == "agari"]
    eq(len(ends), 2, "7.10 一炮双响：两条和了事件都保留（以前第二家会被丢掉）")
    eq([e["winner"] for e in ends], [1, 2], "7.10 两家都是和了家")
    eq([e["fromWho"] for e in ends], [0, 0], "7.10 两家都荣和同一个放铳家")
    check(bool(ends[0]["ten"]) and ends[0]["ten"][1] == 2900,
          "7.10 先和者扣本场 300 + 供托 1000（4200 -> %s）" % (ends[0]["ten"][1:2] or ["?"]))
    check(bool(ends[1]["ten"]) and ends[1]["ten"][1] == 1300,
          "7.10 第二家不扣本场 / 供托（1300 -> %s）" % (ends[1]["ten"][1:2] or ["?"]))
    check(all(e["yaku"] for e in ends), "7.10 两家都判出役种（报告没给 -> 引擎补）")
    eq([e["ba"] for e in ends], [[1, 1], [1, 1]], "7.10 报告 ba 原样保留")
    errs, _n = replay.check_invariants(game, 0)
    eq(len(errs), 0, "7.10 replay 不变量 0 错误")

    # 7.6 真实样本：每个和了局的 符 / 点 / 役种 都与报告对得上
    found = 0
    for fn, _want in SAMPLES:
        path = os.path.join(SAMP, fn)
        if not os.path.exists(path):
            continue
        found += 1
        rep = naga.load_report(path)
        game = naga.game_from_file(path)
        fu_ok = fu_bad = ten_ok = ten_bad = yaku_ok = yaku_bad = yaku_engine = yaku_empty = 0
        for ri, rnd in enumerate(game["rounds"]):
            end = rnd["events"][-1]
            if end.get("type") != "agari":
                continue
            msgs = ((rep["pred"][ri][0].get("info") or {}).get("msg") or {}).get("end_msgs") or [{}]
            raw = msgs[0]
            ten = end.get("ten") or []
            if raw.get("hu"):
                if ten and ten[0] == raw["hu"]:
                    fu_ok += 1
                else:
                    fu_bad += 1
                    print("  BAD fu 局%d ours=%s report=%s" % (ri + 1, ten, raw.get("hu")))
            if raw.get("raw_delta"):
                if ten and ten[1] == raw["raw_delta"]:
                    ten_ok += 1
                else:
                    ten_bad += 1
                    print("  BAD ten 局%d ours=%s raw_delta=%s" % (ri + 1, ten, raw.get("raw_delta")))
            rep_ids = [int(q[0]) for q in (raw.get("yakus_detail") or [])] or [int(y) for y in (raw.get("yakus") or [])]
            our_ids = [int(y[0]) for y in (end.get("yaku") or [])]
            if rep_ids:
                if sorted(rep_ids) == sorted(our_ids):
                    yaku_ok += 1
                else:
                    yaku_bad += 1
                    print("  BAD yaku 局%d report=%s ours=%s" % (ri + 1, rep_ids, our_ids))
            else:
                yaku_engine += 1
                if not our_ids:
                    yaku_empty += 1
                    print("  BAD 空役种 局%d（报告也没给）" % (ri + 1))
        print("  %s：符 %d 对 / %d 空；点数 %d 对 / %d 空；役种按报告 %d 对 / %d 空；报告没给役种的 %d 局全补上 / %d 空"
              % (fn[:8], fu_ok, fu_bad, ten_ok, ten_bad, yaku_ok, yaku_bad, yaku_engine, yaku_empty))
        eq(fu_bad, 0, "%s 符全对" % fn[:8])
        eq(ten_bad, 0, "%s 点数全对" % fn[:8])
        eq(yaku_bad, 0, "%s 役种与报告一致" % fn[:8])
        eq(yaku_empty, 0, "%s 报告没给役种的局也有役种" % fn[:8])
        check(fu_ok > 0, "%s 比对到了报告给的符" % fn[:8])
    if not found:
        print("  SKIP 没有样本，7.6 未执行")

    # 7.7 报告只给役种 id（yakus 有、yakus_detail 空）时：役种 / 番数用引擎判的，
    #     不能假设「每项 1 番」（用户 m02801 ②）。七対子（22）是 2 番，能区分开。
    evs = [{"type": "tsumo", "actor": 0, "pai": "9s"}]
    h7 = {"type": "hora", "actor": 0, "target": 0, "pai": "9s", "deltas": [2400, -800, -800, -800],
          "scores": [27400, 24200, 24200, 24200], "ba": [0, 0], "hu": 25, "fan": 3,
          "raw_delta": 2400, "yakus": [22], "yakus_detail": [], "yakuman": []}
    game = naga.to_game(_report(TEHAIS_CHIITOI, evs, [h7]))
    end = game["rounds"][0]["events"][-1]
    eq(end["ten"], [25, 2400], "7.7 报告只给役种 id 时符 / 点照算（25 符 2400 点）")
    chi = [y for y in end["yaku"] if y[0] == 22]
    eq(len(chi), 1, "7.7 报告给的役种（七対子 22）出现在结果里")
    eq(chi[0][1], 2, "7.7 七対子取引擎判的 2 番（不是默认 1 番）")
    check(0 in [y[0] for y in end["yaku"]], "7.7 引擎把門前清自摸和也补上（报告只给了 id 列表）")

    # 7.8 引擎也算不出（放铳家打出的牌并不成和）时：只显示报告给的役种名，番数留 0、不猜
    evs = [{"type": "tsumo", "actor": 0, "pai": "5s"}, {"type": "dahai", "actor": 0, "pai": "1m"}]
    h8 = {"type": "hora", "actor": 1, "target": 0, "pai": "1m", "deltas": [-1000, 1000, 0, 0],
          "scores": [24000, 26000, 25000, 25000], "ba": [0, 0], "hu": 30, "fan": 1,
          "raw_delta": 1000, "yakus": [8], "yakus_detail": [], "yakuman": []}
    game = naga.to_game(_report(TEHAIS_NOYAKU, evs, [h8]))
    end = game["rounds"][0]["events"][-1]
    eq(end["yaku"], [[8, 0]], "7.8 引擎也算不出时只给役种名、番数留 0（不猜 1 番）")

    # 7.9 场况旗标：报告的役种是权威；岭上要跳过中间夹着的新宝牌消息（用户 m02801 ②）
    st = {"ippatsu": [False, False, False, False], "tilesLeft": 10, "dora": [0]}
    endx = {"uradora_markers": []}
    tsumo1 = [{"type": "tsumo", "actor": 0, "pai": "9s"}]
    eq(naga._hora_ctx(st, [{"type": "ankan", "actor": 0}, {"type": "dora", "actor": 0},
                           {"type": "tsumo", "actor": 0, "pai": "9s"}], endx, 0, 0)["rinshan"], True,
       "7.9 杠 → 新宝牌 → 摸岭上牌：跳过 dora 也能判出岭上")
    eq(naga._hora_ctx(st, tsumo1, endx, 0, 0)["rinshan"], False, "7.9 没有杠就没有岭上")
    eq(naga._hora_ctx(st, tsumo1, endx, 0, 0, (4,))["rinshan"], True,
       "7.9 报告役种里有嶺上開花 4 时直接置真")
    ron1 = naga._hora_ctx(st, [{"type": "kakan", "actor": 0}], endx, 1, 0)
    eq(ron1["chankan"], True, "7.9 荣和前一手是加杠 -> 抢杠")
    eq(naga._hora_ctx(st, [{"type": "dahai", "actor": 0, "pai": "1m"}], endx, 1, 0)["chankan"], False,
       "7.9 荣和前一手只是打牌时不是抢杠")
    hin = naga._hora_ctx(st, tsumo1, endx, 0, 0, (2, 5))
    eq((hin["ippatsu"], hin["haitei"]), (True, True), "7.9 役种提示（一発 / 海底）也能置真")


# ------------------------------------------- 8. naga 下载判重（第 56 轮，用户 m05392）
def section8():
    """两种来源撞到同一个 report_id：官方跳过同名文件、ricochet 覆盖它。"""
    import shutil
    from mjscore import download

    print("\n=== 8. naga 下载判重（用户 m05392） ===")
    rid = "60b5c2ad3d716fab830cc2ad5ad3053fe48cde77cb02094cc2fb50cb04e4675ev2_2"
    off = "https://naga.dmv.nico/htmls/report_viewer.html?report_id=%s&tw=0" % rid
    ric = ("https://ricochet.cn/api/naga/proxy/htmls/report_viewer.html?report_id=" + rid
           + "&tw=0&mtd=%7B%22Mortal-UNK%22%3A%5B%2274683a214bdd1dc3%22%5D%7D")
    eq(download.parse_naga_url(off)["form"], "naga", "官方 url -> form = naga")
    eq(download.parse_naga_url(ric)["form"], "ricochet", "ricochet url -> form = ricochet")
    eq(download.parse_naga_url(off)["key"], download.parse_naga_url(ric)["key"], "两种来源判重键相同")

    calls = []
    real = download.fetch_naga_report

    def fake_fetch(target, **kw):
        info = target if isinstance(target, dict) else download.parse_naga_url(target)
        calls.append(info["form"])
        return (b"\x1f\x8b\x08" + info["form"].encode("utf-8"), b'{"ok": 1}')

    # 注意：沙箱里 %TEMP% 不可写，而且 tempfile.mkdtemp() 建出来的目录连 listdir 都报
    # PermissionError [WinError 5]（os.makedirs 建的目录正常）⇒ 固定名目录放在仓库内
    scratch = os.path.join(ROOT, "build", "_scratch")
    os.makedirs(scratch, exist_ok=True)
    tmp = os.path.join(scratch, "dl_dedup")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    download.fetch_naga_report = fake_fetch
    try:
        path = os.path.join(tmp, "%s.naga" % rid)
        # 8.1 空目录 + 官方来源 -> 下载
        r1 = download.run_download([off], tmp)
        eq((r1["saved"], r1["duplicate"], r1["skipped"]), (1, 0, 0), "空目录 + 官方来源 → 下载（saved=1）")
        eq(os.path.exists(path), True, "落盘 = <report_id>.naga")
        eq(calls, ["naga"], "只请求了一次官方来源")
        # 8.2 本地已有同名文件 + 官方来源 -> 跳过，既不重复下载也不覆盖
        calls[:] = []
        open(path, "wb").write(b"MARKER")
        r2 = download.run_download([off], tmp)
        eq((r2["saved"], r2["duplicate"], r2["skipped"]), (0, 1, 1), "本地已有同名文件 + 官方来源 → 跳过")
        eq(calls, [], "跳过时不发请求（用户 m05392）")
        eq(open(path, "rb").read(), b"MARKER", "官方来源不覆盖本地同名文件")
        # 8.3 本地已有同名文件 + ricochet 来源 -> 下载并覆盖
        r3 = download.run_download([ric], tmp)
        eq((r3["saved"], r3["duplicate"]), (1, 0), "本地已有同名文件 + ricochet 来源 → 下载")
        eq(r3["results"][0]["form"], "ricochet", "结果条目里带上来源形式")
        eq(open(path, "rb").read().endswith(b"ricochet"), True, "本地文件被 ricochet 覆盖（用户 m05392）")
        # 8.4 同一次下载里同一来源的重复 url -> 仍算重复（第二次不再发请求）
        calls[:] = []
        r4 = download.run_download([ric, ric], tmp)
        eq((r4["duplicate"], calls.count("ricochet")), (1, 1), "同一次下载里同一来源的重复 url 仍算重复")
        # 8.5 官方在前、ricochet 在后（同一次下载）-> 最终留下 ricochet 的内容
        os.remove(path)
        r5 = download.run_download([off, ric], tmp)
        eq((r5["saved"], r5["duplicate"]), (2, 0), "官方 + ricochet 同列时两份都写（后者覆盖前者）")
        eq(open(path, "rb").read().endswith(b"ricochet"), True, "官方在前也会被后面的 ricochet 覆盖")
        # 8.6 ricochet 在前、官方在后 -> 官方不覆盖，ricochet 的内容留下
        os.remove(path)
        r6 = download.run_download([ric, off], tmp)
        eq((r6["saved"], r6["duplicate"]), (1, 1), "ricochet 在前时官方来源算重复（1 写 + 1 跳过）")
        eq(open(path, "rb").read().endswith(b"ricochet"), True, "官方来源不覆盖 ricochet 写下的文件")
        # 8.7 overwrite=False 时 ricochet 也不覆盖（尊重显式参数）
        open(path, "wb").write(b"MARKER")
        r7 = download.run_download([ric], tmp, overwrite=False)
        eq((r7["saved"], r7["duplicate"]), (0, 1), "overwrite=False 时 ricochet 也跳过")
        eq(open(path, "rb").read(), b"MARKER", "overwrite=False 时本地文件保持原样")
    finally:
        download.fetch_naga_report = real
        shutil.rmtree(tmp, ignore_errors=True)


def section9():
    """第 56 轮：天凤牌谱同名跳过（用户 m05480）。"""
    print("=== 9. 天凤下载判重（用户 m05480） ===")
    import shutil
    from mjscore import download

    scratch = os.path.join(ROOT, "build", "_scratch")
    os.makedirs(scratch, exist_ok=True)
    tmp = os.path.join(scratch, "dl_tenhou")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)

    log_id = "2026082919gm-00a9-0000-4e40cd3e"
    other = "2026091320gm-00a9-0000-15180bb5"
    url = "http://tenhou.net/0/?log=%s&tw=0" % log_id
    url2 = "http://tenhou.net/0/?log=%s" % other
    path = os.path.join(tmp, "%s.tenhou" % log_id)
    path2 = os.path.join(tmp, "%s.tenhou" % other)

    calls = []
    real = download.fetch_log

    def fake_fetch(target, **kw):
        i = download.extract_log_id(target)
        calls.append(i)
        return b'<mjloggm ver="2.3">%s</mjloggm>' % i.encode("utf-8")

    download.fetch_log = fake_fetch
    try:
        # 9.1 空目录 -> 下载
        r1 = download.run_download([url], tmp)
        eq((r1["saved"], r1["duplicate"], r1["skipped"]), (1, 0, 0),
           "空目录 + 天凤 url → 下载（saved=1）")
        eq(os.path.exists(path), True, "落盘 = <log_id>.tenhou")
        eq(calls, [log_id], "只请求了一次")
        # 9.2 本地已有同名文件 -> 跳过（不发请求、不覆盖）
        calls[:] = []
        open(path, "wb").write(b"OLD")
        r2 = download.run_download([url], tmp)
        eq((r2["saved"], r2["duplicate"], r2["skipped"]), (0, 1, 1),
           "本地已有同名文件 + 天凤 url → 跳过（用户 m05480）")
        eq(calls, [], "跳过时不发请求")
        eq(open(path, "rb").read(), b"OLD", "同名天凤牌谱不会被覆盖")
        # 9.3 overwrite=False 也一样跳过
        calls[:] = []
        r3 = download.run_download([url], tmp, overwrite=False)
        eq((r3["saved"], r3["duplicate"], calls), (0, 1, []),
           "overwrite=False 同样跳过、不发请求")
        # 9.4 同一次下载里重复的同一个 url -> 第二次算重复
        calls[:] = []
        os.remove(path)
        r4 = download.run_download([url, url], tmp)
        eq((r4["saved"], r4["duplicate"], calls), (1, 1, [log_id]),
           "同一次下载里重复 url 仍判重")
        # 9.5 另一个特征码不受影响
        calls[:] = []
        r5 = download.run_download([url2], tmp)
        eq((r5["saved"], os.path.exists(path2)), (1, True), "不同特征码各自下载")
        # 9.6 一列里两个 url：两条都已在本地 -> 都算重复
        calls[:] = []
        r6 = download.run_download([url, url2], tmp)
        eq((r6["saved"], r6["duplicate"], calls), (0, 2, []),
           "两条都已在本地 → 全部跳过、不发请求")
    finally:
        download.fetch_log = real
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------- 10. mortal 下载 + 后缀按风格（第 57 轮，用户 m05545 / m05806）
def section10():
    """第 57 轮（用户 m05545 ① / ② + m05806 ②）：mortal 报告下载 + 文件名后缀按来源 / 风格。"""
    print("=== 10. mortal 下载 + 后缀按风格（用户 m05545 / m05806） ===")
    import json as _json
    import shutil
    from mjscore import cli, download

    rid = "fb13c2973c0eabb3"
    rid2 = "0af57be54bf867a0"
    urls = [
        "https://mjai.ekyu.moe/killerducky/?data=/report/%s.json" % rid,
        "https://mjai.ekyu.moe/report/%s.json" % rid2,
    ]
    infos = [download.parse_mortal_url(u) for u in urls]
    eq([i["report_id"] for i in infos], [rid, rid2], "两种 mortal url 都能解析出 report_id")
    eq([i["form"] for i in infos], ["mortal", "mortal"], "form 一律 = mortal")
    eq(download.parse_mortal_url(rid)["key"], rid, "裸 16 位 report_id 也认")
    eq(download.mortal_report_key(rid.upper() + ".mortal-b"), rid, "判重键 = 文件名去后缀 + 小写")
    eq(download.mortal_report_key(rid + ".mortal"), rid, "通用 .mortal 后缀也认（老文件）")
    eq(download.build_mortal_url(rid), "https://mjai.ekyu.moe/report/%s.json" % rid, "下载地址")
    eq(download.looks_like_mortal_url("https://example.com/x"), False, "非 mortal url 不误判")

    # 区分风格的关键字：报告里没有中文风格名，唯一标识是 review.model_tag
    for tag, style, en in (("4.1a", "避四", "defensive"), ("4.1b", "平衡", "balanced"),
                           ("4.1c", "争一", "aggressive")):
        raw = _json.dumps({"review": {"model_tag": tag, "temperature": 0.1}, "mjai_log": []}).encode("utf-8")
        info = download.mortal_model_info(raw)
        eq((info.get("model_tag"), info.get("style"), info.get("style_en")), (tag, style, en),
           "review.model_tag %s -> %s / %s（用户 m05545 ① 询问的关键字）" % (tag, style, en))
        eq(download.mortal_suffix_for(tag), ".mortal-" + tag[-1],
           "model_tag %s -> 落盘后缀 .mortal-%s（用户 m05806 ②）" % (tag, tag[-1]))
    eq(download.mortal_suffix_for(None), ".mortal", "认不出的 tag -> 通用 .mortal")
    eq(download.mortal_model_info(b"not json at all"), {}, "坏内容 -> {}")
    eq(download.mortal_model_info(_json.dumps({"engine": "Mortal"}).encode("utf-8")), {},
       "没有 review 的报告 -> {}")

    # 后缀常量（新旧并存）
    eq(paths.TENHOU_SUFFIX, ".tenhou", "天凤新后缀 = .tenhou")
    eq(paths.NAGA_SUFFIX, ".naga", "NAGA 新后缀 = .naga")
    eq(paths.MORTAL_SUFFIX, ".mortal", "Mortal 通用后缀 = .mortal")
    eq(tuple(paths.MORTAL_STYLE_SUFFIXES), (".mortal-a", ".mortal-b", ".mortal-c"),
       "mortal 风格后缀 = .mortal-a / -b / -c")
    eq(paths.MORTAL_SUFFIX_BY_TAG, {"4.1a": ".mortal-a", "4.1b": ".mortal-b", "4.1c": ".mortal-c"},
       "model_tag -> 后缀映射")
    check(".tenhou" in paths.TENHOU_SUFFIXES and ".xml" in paths.TENHOU_SUFFIXES,
          "天凤后缀表同时含新旧（%r）" % (paths.TENHOU_SUFFIXES,))
    check(".naga" in naga.NAGA_SUFFIXES and ".json.gz" in naga.NAGA_SUFFIXES,
          "NAGA 后缀表同时含新旧（%r）" % (naga.NAGA_SUFFIXES,))

    scratch = os.path.join(ROOT, "build", "_scratch")
    os.makedirs(scratch, exist_ok=True)
    tmp = os.path.join(scratch, "dl_mortal")
    tmp2 = os.path.join(scratch, "dl_mixed")
    for d in (tmp, tmp2):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)

    calls = []
    real = download.fetch_mortal_report
    real_naga = download.fetch_naga_report
    real_log = download.fetch_log

    def fake_mortal(target, **kw):
        info = target if isinstance(target, dict) else download.parse_mortal_url(target)
        calls.append(info["report_id"])
        tag = "4.1b" if info["report_id"] == rid else "4.1c"
        body = _json.dumps({"engine": "Mortal", "mjai_log": [],
                            "review": {"model_tag": tag, "temperature": 0.1}}).encode("utf-8")
        info = dict(info)
        info.update(download.mortal_model_info(body))
        return body, info

    download.fetch_mortal_report = fake_mortal
    try:
        # 10.1 空目录 + 两条 mortal url -> 都下载，后缀按风格
        r1 = download.run_download(urls, tmp)
        eq((r1["saved"], r1["duplicate"], r1["skipped"]), (2, 0, 0), "空目录 + 两条 mortal url → 都下载")
        eq(calls, [rid, rid2], "两个 report_id 各请求一次")
        p1 = os.path.join(tmp, rid + ".mortal-b")
        eq(os.path.exists(p1), True, "4.1b 落盘 = <report_id>.mortal-b（用户 m05806 ②）")
        eq(os.path.exists(os.path.join(tmp, rid2 + ".mortal-c")), True, "4.1c 落盘 = <report_id>.mortal-c")
        eq([e.get("model_tag") for e in r1["results"]], ["4.1b", "4.1c"], "结果条目带 model_tag")
        eq([e.get("style") for e in r1["results"]], ["平衡", "争一"], "结果条目带风格（平衡 / 争一）")
        # 10.2 本地已有同名（任意风格后缀）-> 跳过、不发请求、不覆盖
        calls[:] = []
        open(p1, "wb").write(b"MARKER")
        r2 = download.run_download([urls[0]], tmp)
        eq((r2["saved"], r2["duplicate"], r2["skipped"]), (0, 1, 1), "本地已有同名 .mortal-b → 跳过")
        eq(calls, [], "跳过时不发请求")
        eq(open(p1, "rb").read(), b"MARKER", "同名 mortal 文件不被覆盖")
        # 10.2b 已有 .mortal-b、这次是 .mortal-c 的同一 report_id -> 仍按重复跳过
        other = os.path.join(tmp, rid + ".mortal-c")
        shutil.copyfile(p1, other)
        r2b = download.run_download([urls[0]], tmp)
        eq((r2b["saved"], r2b["duplicate"]), (0, 1), "同一 report_id 换个风格后缀也算重复")
        eq(os.path.exists(other), True, "风格后缀不同的同名报告都留着")
        os.remove(other)
        # 10.3 同一次下载里重复的同一个 url -> 第二次算重复
        calls[:] = []
        r3 = download.run_download([urls[0], urls[0]], tmp)
        eq((r3["saved"], r3["duplicate"], calls), (0, 2, []), "同名 + 重复 url 都是跳过（两条都算重复）")
        # 10.4 三种来源混在一列 -> 三种后缀各自落盘
        download.fetch_naga_report = lambda t, **kw: (b"\x1f\x8b\x08naga", b'{"ok": 1}')
        download.fetch_log = lambda t, **kw: b'<mjloggm ver="2.3"></mjloggm>'
        log_id = "2026082919gm-00a9-0000-4e40cd3e"
        naga_rid = "60b5c2ad3d716fab830cc2ad5ad3053fe48cde77cb02094cc2fb50cb04e4675ev2_2"
        calls[:] = []
        r4 = download.run_download(["https://naga.dmv.nico/reports/%s.json.gz" % naga_rid,
                                    "http://tenhou.net/0/?log=%s&tw=0" % log_id,
                                    urls[0]], tmp2)
        eq((r4["saved"], r4["duplicate"]), (3, 0), "mortal / naga / 天凤 混在一列都能下载")
        check(os.path.exists(os.path.join(tmp2, naga_rid + ".naga")), "NAGA 落盘 = <report_id>.naga")
        check(os.path.exists(os.path.join(tmp2, log_id + ".tenhou")), "天凤落盘 = <log_id>.tenhou")
        check(os.path.exists(os.path.join(tmp2, rid + ".mortal-b")), "Mortal 落盘 = <report_id>.mortal-b")
        # 分析链路的目录扫描认得三种新后缀（第 59 轮起 Mortal 也参与分析，用户 m05937 ③）
        picked = cli.resolve_inputs([tmp2])
        eq(sorted(os.path.basename(p) for p in picked),
           sorted([naga_rid + ".naga", log_id + ".tenhou", rid + ".mortal-b"]),
           "resolve_inputs 目录扫描认得 .tenhou / .naga / .mortal-b")
        eq(cli.report_kind(os.path.join(tmp2, rid + ".mortal-b")), "mortal", "report_kind 认得 .mortal-b")
        eq(cli.report_kind(os.path.join(tmp2, naga_rid + ".naga")), "naga", "report_kind 认得 .naga")
        eq(naga.is_naga_file(os.path.join(tmp2, naga_rid + ".naga")), True, "is_naga_file 认得 .naga")
        eq(naga.is_naga_file(os.path.join(tmp2, rid + ".mortal-b")), False, "mortal 不会被当成 naga")
    finally:
        download.fetch_mortal_report = real
        download.fetch_naga_report = real_naga
        download.fetch_log = real_log
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)


# --------------------------------------------------- 11. 杠副露的牌张数（用户 m08125 ①，第 65 轮回归）
def section11():
    print("---- 11. 杠 / 碰副露的牌张数（用户 m08125 ①）")
    cnt = {}
    bad = []
    for fn, _want in SAMPLES:
        path = os.path.join(SAMP, fn)
        if not os.path.exists(path):
            continue
        game = naga.game_from_file(path)
        for ri in range(len(game["rounds"])):
            st = replay.initial_state(game, ri)
            for ev in game["rounds"][ri]["events"]:
                replay.apply_event(st, ev)
            for s in range(4):
                for m in st["players"][s]["melds"]:
                    t = m["callType"]
                    cnt[t] = cnt.get(t, 0) + 1
                    want = 4 if t in ("kakan", "ankan", "daiminkan") else 3
                    same = (t == "chi") or len(set(x // 4 for x in m["tiles"])) == 1
                    if len(m["tiles"]) != want or not same:
                        bad.append((fn[:12], ri + 1, s, t, m["tiles"]))
    print("       副露统计：%s" % cnt)
    check(cnt.get("kakan", 0) > 0, "11.1 样本里有加杠（%d 次）" % cnt.get("kakan", 0))
    eq(bad, [], "11.2 加杠 / 暗杠 / 大明杠都是 4 张、碰 3 张、且同种牌"
                "（加杠曾只带 1 张导致 4 张消失，用户 m08125 ①）")


# --------------------------------------------------- 12. 新版 NAGA（アナンタ / ウロボロス，用户 m09507）
def section12():
    print("---- 12. 新版 NAGA 报告：别名 / 37 槽折叠 / 第零类 7 项")
    eq(ai_models.normalize("アナンタ"), ai_models.NAGA_AVOID4, "アナンタ → NAGA-避四")
    eq(ai_models.normalize("ウロボロス"), ai_models.NAGA_AGGRESSIVE, "ウロボロス → NAGA-争一")
    eq(ai_models.series_of(ai_models.NAGA_AVOID4), "NAGA", "NAGA-避四 属 NAGA 系列")
    eq(ai_models.series_of(ai_models.NAGA_AGGRESSIVE), "NAGA", "NAGA-争一 属 NAGA 系列")
    eq([m["name"] for m in ai_models.model_list({"0": "ニシキ", "1": "アナンタ", "2": "ウロボロス"})],
       ["NAGA-平衡", "NAGA-避四", "NAGA-争一"], "新版 naga_types → 三个模型名（用户 m09507）")
    eq(len(ai_models.CHOICES), 7, "第零类 7 项")
    eq([c[0] for c in ai_models.CHOICES],
       ["ai_balance", "ai_superhuro", "ai_naga_avoid4", "ai_naga_aggressive",
        "ai_mortal41a", "ai_mortal41b", "ai_mortal41c"], "第零类 key 顺序（NAGA 三项在前，用户 m09507）")
    eq(len(feats.FEATURES), 42, "总特征 42 项（7 + 17 + 17 + 1）")
    arr = [0] * 37
    arr[34] = 3000; arr[4] = 100
    arr[35] = 2000; arr[13] = 50
    arr[36] = 4000; arr[22] = 10
    out = naga._collapse_dahai(arr)
    eq(len(out), 34, "折叠后 34 槽")
    eq((out[4], out[13], out[22]), (3100, 2050, 4010), "赤 5 的 34 / 35 / 36 折回 5m / 5p / 5s")
    eq(naga._collapse_dahai([0] * 34 + [0, 0, 3000], [0] * 34 + [0, 0, 1000])[22], 4000,
       "两支逐槽相加后再折叠（官方 viewer 的 gt(a[0] + a[1])）")
    fr = {"info": {"msg": {"type": "tsumo", "actor": 0, "pai": "5m", "tsumo": []}},
          "dahai_pred": [[100] * 34, [0] * 34, [0] * 34],
          "reach": [5000, None, None],
          "dahai_detail": [None, [[0] * 34 + [0, 0, 6000], [0] * 34 + [800, 0, 0]],
                           [[0] * 34 + [0, 0, 7000], [0] * 37]]}
    em = naga._frame(fr, ai_models.model_list({"0": "ニシキ", "1": "アナンタ", "2": "ウロボロス"}))
    eq(em["dahai_pred"][0], [100] * 34, "ニシキ 的 dahai_pred 原样保留（零变化前提，用户 m09507）")
    eq(em["dahai_pred"][1][22], 6000, "アナンタ 的边际打牌分布 = 两支相加（赤 5s 槽折回 5s）")
    eq(em["dahai_pred"][1][4], 800, "アナンタ 立直支里的 5m 也并入边际分布")
    eq(em["dahai_pred"][2][22], 7000, "ウロボロス 同理（立直支全 0）")
    eq(em["reach"][0], 5000, "ニシキ 的 reach 原样保留")
    eq(em["reach"][1], 800, "アナンタ 的立直概率 = 立直支之和（官方 viewer 口径）")
    eq(em["reach"][2], 0, "ウロボロス 的立直支全 0 ⇒ 这一帧立直概率 0")
    fr2 = {"info": {"msg": {"type": "dahai", "actor": 1, "pai": "1m", "tsumo": []}},
           "dahai_pred": [[100] * 34, [0] * 34, [0] * 34],
           "dahai_detail": [None, [[0] * 34 + [0, 0, 6000], [0] * 37], None]}
    em2 = naga._frame(fr2, ai_models.model_list({"0": "ニシキ", "1": "アナンタ", "2": "ウロボロス"}))
    eq(em2["dahai_pred"][1][22], 6000, "不是立直决策帧也照样用 detail 算边际打牌分布")
    eq("reach" in em2, False, "报告没标立直决策 ⇒ 不补 reach（沿用报告原始取值）")
    # ------------------------------------------------ 完整动作空间（用户 m10081）
    fr3 = {"info": {"msg": {"type": "tsumo", "actor": 2, "pai": "F", "tsumo": []}},
           "dahai_pred": [None, None, None],
           "dahai_detail": [None, [[0] * 37, [0] * 37], [[0] * 37, [0] * 37]],
           "hora": {"0": [None, 1200, 0], "2": [None, 9999, 10000]},
           "ankan_pai": [None, {"F": 9944}, {"F": 9984}],
           "kakan_pai": [None, {"9s": 7}, None],
           "kyushu": [None, 0, 0]}
    em3 = naga._frame(fr3, ai_models.model_list({"0": "ニシキ", "1": "アナンタ", "2": "ウロボロス"}))
    eq(em3["hora"]["2"], [None, 9999, 10000], "hora 原样带出（{座位: [每模型和了概率]}，用户 m10081）")
    eq(em3["ankan_pai"][1], {"32": 9944}, "ankan_pai 的牌名转成牌种索引（F = 発 = 32）")
    eq(em3["ankan_pai"][2], {"32": 9984}, "ウロボロス 的暗杠概率按模型各自带出")
    eq(em3["kakan_pai"][1], {"26": 7}, "kakan_pai 同理（9s = 26）")
    eq(em3["kyushu"], [None, 0, 0], "kyushu 按每模型带出（样本里没有，格式先支持）")
    em4 = naga._frame({"info": {"msg": {"type": "tsumo", "actor": 0, "pai": "5m", "tsumo": []}},
                       "dahai_pred": [[100] * 34, [0] * 34, [0] * 34]},
                      ai_models.model_list({"0": "ニシキ", "1": "アナンタ", "2": "ウロボロス"}))
    eq([k for k in ("hora", "kyushu", "ankan_pai", "kakan_pai") if k in em4], [],
       "报告没有这些字段 ⇒ 转换结果里也不出现（旧模型 / 旧报告零变化，用户 m09507）")


def main():
    print("naga_test：第 27 轮 NAGA 报告适配层（流局种类推断 + 听牌自算）+ 第 29 轮打点链路集成")
    section1()
    section2()
    section3()
    section4()
    section5()
    section6()
    section7()
    section8()
    section9()
    section10()
    section11()
    section12()
    print("=== 结果：通过 %d 项，失败 %d 项 ===" % (OK[0], BAD[0]))
    if BAD[0]:
        print("有失败用例")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
