# -*- coding: utf-8 -*-
r"""第 19 轮：12 个期望特征（`mjscore/expect.py`）的测试。

覆盖点
  1) `waits_of` 与暴力枚举对拍（合成国士/七対子/面子手 + 语料里的听牌手牌）
  2) 手算用例：副露/门清两套假设、概率扣减、嵌张无役、平和両面、副露役牌、副露无役、
     立直/默听两套假想（m02512：未立直的门清帧也按立直假设算，副露帧两项记 0）、14 张根节点、
     已和牌帧、范畴外、期望打点的归一化（m02389）、听牌枚数的归一化（m02647：分子 Σp·枚数 / 分母
     Σp；分母按 m02766 只数「有役听牌」，叶子值 1.0 / 0.0）
  3) 独立参考实现：叶子（2 种假设 x 2 种模式 x 枚数分子 / 枚数分母 / 打点分子 / 打点分母）与模块节点
     字典逐键对拍
  3b) 14 张「打一张即听」的帧：独立一层聚合（sum/best x 副露/门清，枚数按 m02647 + m02766 归一化）
  3c) 进张概率扣减：向听 1 的帧用独立一层枚举（每步扣掉已假想摸进的牌）对拍
  4) 不变量（非负、绝对枚数 >= 期望枚数、和牌帧枚数为 0、超范围全 0）+ 语料子集的耗时与分档统计

运行：& 'D:\coding\anaconda3\envs\py314_null\python.exe' test\expect_test.py
"""
import glob
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mjscore import agari, expect, mjlog, replay, shanten

OK = [0]
BAD = [0]
TSUMO = expect.TSUMO
RON = expect.RON
RIICHI = expect.RIICHI
DAMATEN = expect.DAMATEN


def check(cond, label):
    if cond:
        OK[0] += 1
        print("  OK   " + label)
    else:
        BAD[0] += 1
        print("  FAIL " + label)


def eq(got, want, label):
    check(got == want, "%s（got %r / want %r）" % (label, got, want))


def near(got, want, label, tol=1e-6):
    check(abs(got - want) <= tol, "%s（got %.6f / want %.6f）" % (label, got, want))


def ids(kinds):
    """牌种列表 -> 互不相同的牌 id（同种第 n 张 = kind*4+n，天然避开赤 5 的 16/52/88）。"""
    used = {}
    out = []
    for k in kinds:
        n = used.get(k, 0)
        used[k] = n + 1
        out.append(k * 4 + n)
    return out


def pon(k):
    return {"callType": "pon", "tiles": [k * 4 + 1, k * 4 + 2, k * 4 + 3], "fromWho": 1}


def chi(kinds):
    return {"callType": "chi", "tiles": ids(kinds), "fromWho": 3}


def state_for(hand, melds=(), seen=(), oya=3, round_=0, riichi=False, dora=()):
    """合成截面：座位 0 拿 hand/melds；`seen` 是 1 家牌河的 [{tile, called}]。"""
    pls = []
    for i in range(4):
        pls.append({"hand": [], "melds": [], "river": [], "riichi": False,
                    "riichiPending": False, "score": 25000})
    pls[0]["hand"] = list(hand)
    pls[0]["melds"] = list(melds)
    if riichi:
        pls[0]["riichi"] = True
    if seen:
        pls[1]["river"] = list(seen)
    return {"round_index": 0, "round": round_, "honba": 0, "kyotaku": 0, "oya": oya,
            "scores": [25000] * 4, "players": pls, "dora": list(dora), "dices": [],
            "drawn": hand[0] if hand else None, "tilesLeft": 40, "phase": "play",
            "result": None, "reveal": None, "desc": "", "evIndex": 0, "warnings": []}


def node_keys():
    """`Expect.node()` 返回字典的全部键（36 个：枚数分子 12 + 枚数分母 12 + 打点分子 6 + 分母 6）。"""
    out = []
    for agg in expect.AGGS:
        for mode in (TSUMO, RON):
            for measure in ("avail", "abs"):
                out.append(("tp", expect.FURO_ASSUME, agg, mode, measure))
                out.append(("tq", expect.FURO_ASSUME, agg, mode, measure))
        for measure in ("avail", "abs"):
            out.append(("tp", expect.MENZEN_ASSUME, agg, measure))
            out.append(("tq", expect.MENZEN_ASSUME, agg, measure))
    for assume in expect.ASSUMES:
        for mode in (TSUMO, RON):
            out.append(("sc", assume, mode))
            out.append(("ms", assume, mode))
    return set(out)


def corpus():
    return sorted(glob.glob(os.path.join(ROOT, "data", "**", "*.xml"), recursive=True)
                  + glob.glob(os.path.join(ROOT, "data_extra", "*.xml")))


def sub(counts, k):
    out = list(counts)
    out[k] -= 1
    return out


def frames(files, limit=None, skip=0):
    """产出 (ev, st, seat)：摸牌帧与吃/碰帧，且该帧手牌正好 14-3n 张。"""
    n = 0
    for fn in files:
        game = mjlog.game_from_file(fn)
        for ri in range(len(game["rounds"])):
            for i, ev, st in replay.iter_events(game, ri):
                if ev["type"] == "draw":
                    seat = ev["player"]
                elif ev["type"] == "call" and ev.get("callType") in ("chi", "pon"):
                    seat = ev["player"]
                else:
                    continue
                pl = st["players"][seat]
                if sum(agari.counts_of(pl["hand"])) != agari.concealed_size(pl["melds"]) + 1:
                    continue
                n += 1
                if n <= skip:
                    continue
                if limit is not None and n > skip + limit:
                    return
                yield ev, st, seat


def tenpai_hands(files):
    """产出 (st, seat, counts)：语料里 13-3n 张且听牌（向听 0）的手牌。"""
    for fn in files:
        game = mjlog.game_from_file(fn)
        for ri in range(len(game["rounds"])):
            for i, ev, st in replay.iter_events(game, ri):
                if ev["type"] != "draw":
                    continue
                seat = ev["player"]
                pl = st["players"][seat]
                c14 = agari.counts_of(pl["hand"])
                if sum(c14) != agari.concealed_size(pl["melds"]) + 1:
                    continue
                k = mjlog.kind_of(ev["tile"])
                if c14[k] <= 0:
                    continue
                c = sub(c14, k)
                e = expect.Expect(st, seat)
                if e.dist(c) == 0:
                    yield st, seat, c


def ref_leaf(e, counts, tsumo, assume=None, used=None, all_waits=False):
    """独立参考：叶子（13-3n 张听牌手牌）的 (期望枚数, 绝对枚数, Σp·得点, Σp)。

    `assume` = `expect.FURO_ASSUME`（门清役不存在）/ `expect.RIICHI_ASSUME`（保持门清 + 宣布立直）/
    `expect.DAMATEN_ASSUME`（保持门清但不宣布立直，m02512）；`all_waits=True` 时枚数按全部形状听牌
    计（门清枚数项的口径，与自摸 / 荣和 / 立直 / 默听无关）。
    `used` = 34 项「已假想摸进的张数」（概率与枚数都要扣掉这些牌）。
    最后两项分别是模块内部键 `("sc", assume, mode)` 与 `("ms", assume, mode)`；帧级打点特征 =
    argmax{p x 打点} 那一条分支上的 分子 / 分母（用户 m02389）。
    """
    assume = e.cat if assume is None else assume
    if used is None:
        al = list(e.avail)
        ul = e.unseen
    else:
        al = e._avail_left(used)
        ul = e._unseen_left(used)
    if assume == expect.FURO_ASSUME:
        menzen, state, riichi = False, expect.FURO, 0
    elif assume == expect.RIICHI_ASSUME:
        menzen, state, riichi = True, RIICHI, (e.riichi or 1)
    else:                                    # DAMATEN / MENZEN（门清枚数参考）
        menzen, state, riichi = True, DAMATEN, 0
    avail = 0
    absn = 0
    sc = 0.0
    ms = 0.0
    for k in sorted(e.waits(counts)):
        r = None
        if not all_waits:
            try:
                r = agari.score(expect.tiles_of(counts), e.melds, win_tile=expect.tid_of(k),
                                tsumo=tsumo, oya=e.oya, honba=e.honba, kyotaku=e.kyotaku,
                                seat_wind=e.sw, round_wind=e.rw, riichi=riichi, state=state,
                                menzen=(e.menzen if menzen else False),
                                ctx={"dora": e.dora})
            except ValueError:
                continue
        avail += al[k]
        absn += 4 - counts[k] - e.meldc[k]
        if r is not None and ul > 0:
            p = al[k] / float(ul)
            sc += p * r["gain"]
            ms += p
    return avail, absn, sc, ms


def ref_yaku_ok(e, counts, tsumo, assume=None):
    """独立参考（m02766）：这个听牌叶子在该假设 / 模式下算不算「有役听牌」（归一化分母 1.0 / 0.0）。

    判据 = 至少有一张形状听牌能过起和役门槛（`agari.score` 抛 `ValueError` 即无役）。
    `assume=expect.MENZEN_ASSUME`（门清枚数项）按「门清自摸必有役」处理 => 听牌叶子一律算有役。
    """
    assume = e.cat if assume is None else assume
    if assume == expect.MENZEN_ASSUME:
        return True
    if assume == expect.FURO_ASSUME:
        menzen, state, riichi = False, expect.FURO, 0
    elif assume == expect.RIICHI_ASSUME:
        menzen, state, riichi = True, RIICHI, (e.riichi or 1)
    else:
        menzen, state, riichi = True, DAMATEN, 0
    for k in sorted(e.waits(counts)):
        try:
            agari.score(expect.tiles_of(counts), e.melds, win_tile=expect.tid_of(k), tsumo=tsumo,
                        oya=e.oya, honba=e.honba, kyotaku=e.kyotaku, seat_wind=e.sw,
                        round_wind=e.rw, riichi=riichi, state=state,
                        menzen=(e.menzen if menzen else False), ctx={"dora": e.dora})
            return True
        except ValueError:
            continue
    return False


def ref_frame(e, counts, assume):
    """独立参考：向听 1 的 13-3n 张帧的一层枚举（每次进张后把那张牌从剩余未见里扣掉）。

    -> (vals, scs)：``vals[(agg, mode, measure)]``（agg 为 "sum"/"best"）、``scs[mode]``（打点：
    每个进张按 argmax{p x 打点} 选一手，分子 / 分母都取这一手，最后相除 = 条件期望，m02389）。
    枚数（m02647）：分子 = Σ p x 枚数、分母 = 同一批听牌叶子的 Σ p（叶子分母 1.0），最后相除 ——
    "sum" 口径对每条完美路线求和（分母 = Σ p x 该进张下的最小向听打牌数），"best" 口径按枚数分子
    argmax 选一手。
    """
    vals = {}
    for agg in ("sum", "best"):
        for mode in (TSUMO, RON):
            for measure in ("avail", "abs"):
                vals[(agg, mode, measure)] = 0.0
    nums = {}                                       # [(分子, 分母)]，最后相除
    for agg in ("sum", "best"):
        for mode in (TSUMO, RON):
            for measure in ("avail", "abs"):
                nums[(agg, mode, measure)] = [0.0, 0.0]
    scs = {TSUMO: [0.0, 0.0], RON: [0.0, 0.0]}      # [Σ p·得点, Σ p]，最后相除
    for t in range(34):
        if counts[t] >= 4 or e.avail[t] <= 0:
            continue
        used = [0] * 34
        used[t] = 1
        c14 = list(counts)
        c14[t] += 1
        if e.dist(c14, used) != 0:
            continue
        keep = [k for k in range(34) if c14[k] > 0 and e.dist(sub(c14, k), used) == 0]
        if not keep:
            continue
        p = e.avail[t] / float(e.unseen)
        for mode in (TSUMO, RON):
            tsumo = (mode == TSUMO)
            kids = [sub(c14, k) for k in keep]
            rows = [ref_leaf(e, kids[j], tsumo, assume=assume, used=used) for j in range(len(kids))]
            # m02766：归一化分母只数「有役听牌」的叶子（副露假设要判役；门清枚数项按「门清自摸
            # 必有役」=> 每个听牌叶子都算）
            if assume == expect.FURO_ASSUME:
                ok = [ref_yaku_ok(e, kids[j], tsumo, assume) for j in range(len(kids))]
            else:
                ok = [True] * len(kids)
            for i, measure in enumerate(("avail", "abs")):
                nums[("sum", mode, measure)][0] += p * sum(r[i] for r in rows)
                nums[("sum", mode, measure)][1] += p * float(sum(1 for o in ok if o))
                j = max(range(len(rows)), key=lambda x: rows[x][i])     # best：按分子最大的那一手
                nums[("best", mode, measure)][0] += p * rows[j][i]
                nums[("best", mode, measure)][1] += p * (1.0 if ok[j] else 0.0)
            best = max(rows, key=lambda r: r[2])        # argmax{p x 打点} = argmax Σp·得点
            scs[mode][0] += p * best[2]
            scs[mode][1] += p * best[3]
    for mode in (TSUMO, RON):
        num, den = scs[mode]
        scs[mode] = (num / den) if den > 0 else 0.0
    for k, (num, den) in nums.items():
        vals[k] = (num / den) if den > 0 else 0.0
    return vals, scs


def section1():
    print("=== 1. waits_of 与暴力枚举对拍 ===")
    eq(sorted(expect.waits_of(agari.counts_of(ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 22, 24])))),
       [23], "合成：嵌张听 6s")
    eq(sorted(expect.waits_of(agari.counts_of(ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 22, 23])))),
       [21, 24], "合成：両面听 4s/7s")
    chiitoi = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6]
    eq(6 in expect.waits_of(agari.counts_of(ids(chiitoi))), True, "合成：七対子形听第 7 种牌")
    yao = list(shanten.YAO_KINDS)
    want13 = sorted(yao)
    eq(sorted(expect.waits_of(agari.counts_of(ids(yao)))), want13, "合成：国士十三面听 13 种幺九")
    kok = [yao[0], yao[0]] + yao[2:]        # 13 张：1 种成对 + 11 种单张，缺的那 1 种才是听牌
    eq(sorted(expect.waits_of(agari.counts_of(ids(kok)))), [yao[1]], "合成：国士有对子时只听缺的那 1 种幺九")
    files = corpus()[:3]
    n = 0
    bad = 0
    for st, seat, c in tenpai_hands(files):
        e = expect.Expect(st, seat)
        w = sorted(e.waits(c))
        brute = sorted(k for k in range(34) if c[k] < 4 and agari.shapes_of(
            expect.tiles_of(c) + [expect.tid_of(k)], e.melds))
        n += 1
        if w != brute:
            bad += 1
            if bad <= 5:
                print("    差异 %s vs %s（手牌 %s）" % (w, brute, c))
    check(n >= 100, "语料听牌手牌样本数 >= 100（实际 %d）" % n)
    eq(bad, 0, "waits_of 与暴力枚举一致（%d 例）" % n)
    return n


def section2():
    print("=== 2. 手算用例 ===")
    h1 = ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 22, 24])       # 123m456m234p66p5s7s
    h2 = ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 22, 23])       # 123m456m234p66p56s
    h3 = ids([0, 1, 2, 3, 4, 5, 15, 15, 22, 23])                  # 10 张 + 副露

    e1 = expect.Expect(state_for(h1), 0)
    f1 = expect.values(state_for(h1), 0)
    eq(sorted(e1.waits(e1.counts)), [23], "嵌张：听 6s")
    eq(f1["menzen_tenpai_expect"], 4.0, "嵌张：期望听牌枚数 4（门清按自摸门槛）")
    eq(f1["menzen_tenpai_abs"], 4.0, "嵌张：期望听牌绝对枚数 4")
    near(f1["damaten_tsumo_score"], 1100.0,
         "嵌张：默听自摸期望打点 1100（m02389：和牌前提下的条件期望，只有一种和牌张）")
    eq(f1["damaten_ron_score"], 0.0, "嵌张：默听荣和期望打点 0（无役）")
    eq(sum(v for k, v in f1.items() if k.startswith("furo")), 0.0, "嵌张：副露 6 项全 0")
    near(f1["riichi_ron_score"], 1300.0,
         "嵌张：立直荣和期望打点 1300（m02512：未立直的门清帧也按立直假设算；默听时无役）")
    near(f1["riichi_tsumo_score"], 2000.0,
         "嵌张：立直自摸期望打点 2000（立直 + 門前清自摸和 2 番 30 符）")

    e2 = expect.Expect(state_for(h2), 0)
    f2 = expect.values(state_for(h2), 0)
    eq(sorted(e2.waits(e2.counts)), [21, 24], "両面：听 4s/7s")
    eq(f2["menzen_tenpai_expect"], 8.0, "両面：期望听牌枚数 8")
    eq(f2["menzen_tenpai_abs"], 8.0, "両面：期望听牌绝对枚数 8")
    near(f2["damaten_ron_score"], 1000.0,
         "両面：默听荣和期望打点 1000（4s/7s 得点相同，归一化后就是该得点）")
    near(f2["damaten_tsumo_score"], 1500.0, "両面：默听自摸期望打点 1500（平和+自摸 2 番 20 符）")
    near(f2["riichi_ron_score"], 2000.0, "両面：立直荣和期望打点 2000（平和+立直 2 番 30 符）")
    near(f2["riichi_tsumo_score"], 2700.0,
         "両面：立直自摸期望打点 2700（平和+立直+自摸 3 番 20 符）")

    f2b = expect.values(state_for(h2, seen=[{"tile": 21 * 4 + 1, "called": False}]), 0)
    eq(f2b["menzen_tenpai_expect"], 7.0, "牌河见 1 张 4s：期望听牌枚数 7")
    eq(f2b["menzen_tenpai_abs"], 8.0, "牌河见 1 张 4s：绝对枚数仍 8（只看自己手牌）")

    e3 = expect.Expect(state_for(h3, melds=[pon(32)]), 0)           # 碰 發
    f3 = expect.values(state_for(h3, melds=[pon(32)]), 0)
    eq(sorted(e3.waits(e3.counts)), [21, 24], "副露：碰發后听 4s/7s")
    eq(f3["furo_tsumo_tenpai_expect"], 8.0, "副露：自摸期望听牌枚数 8")
    eq(f3["furo_ron_tenpai_expect"], 8.0, "副露：荣和期望听牌枚数 8")
    eq(f3["furo_tsumo_tenpai_abs"], 8.0, "副露：自摸期望听牌绝对枚数 8")
    eq(f3["furo_ron_tenpai_abs"], 8.0, "副露：荣和期望听牌绝对枚数 8")
    near(f3["furo_ron_score"], 1000.0, "副露：荣和期望打点 1000（役牌 1 番 30 符）")
    near(f3["furo_tsumo_score"], 1100.0, "副露：自摸期望打点 1100（两张和牌张得点相同）")
    eq(sum(v for k, v in f3.items() if k.startswith(("menzen", "damaten", "riichi"))), 0.0,
       "副露：门清 6 项全 0")

    f3b = expect.values(state_for(h3, melds=[chi([18, 19, 20])]), 0)  # 吃 123s
    eq(f3b["furo_ron_tenpai_expect"], 0.0, "副露无役（吃 123s）：荣和期望枚数 0")
    eq(f3b["furo_tsumo_tenpai_expect"], 0.0, "副露无役（吃 123s）：自摸期望枚数 0")
    eq(f3b["furo_ron_tenpai_abs"], 0.0, "副露无役（吃 123s）：绝对枚数也 0")
    e3b = expect.Expect(state_for(h3, melds=[chi([18, 19, 20])]), 0)
    eq(e3b.node(e3b.counts)[("tq", expect.FURO_ASSUME, "sum", TSUMO, "avail")], 0.0,
       "副露无役（吃 123s）：听牌叶子不进归一化分母（0.0，m02766）")

    f4 = expect.values(state_for(ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 22, 23, 26])), 0)
    check(f4["menzen_tenpai_expect"] >= 8.0, "14 张根节点（打 9s 即听）：期望枚数 >= 8")
    check(f4["damaten_tsumo_score"] > 0.0, "14 张根节点：自摸期望打点 > 0")

    f5 = expect.values(state_for(h1, riichi=True), 0)
    near(f5["riichi_ron_score"], 1300.0, "已宣布立直的帧：立直荣和期望打点 1300（用实际立直番数）")
    near(f5["damaten_tsumo_score"], 1100.0,
         "已宣布立直的帧：默听项仍是「假想不宣布立直」（m02512，与未立直帧同值）")
    eq(f5["menzen_tenpai_expect"], f1["menzen_tenpai_expect"], "立直/默听共用枚数项")

    # 已和牌帧：枚数 0、打点 = 该手牌的和牌得点
    won = ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 21, 22, 23])   # 123m456m234p66p456s
    st = state_for(won)
    e = expect.Expect(st, 0)
    eq(e.dist(e.counts), -1, "已和牌帧：向听 -1")
    fw = expect.values(st, 0)
    eq(sum(v for k, v in fw.items() if k.endswith("tenpai_expect") or k.endswith("tenpai_abs")), 0.0,
       "已和牌帧：6 个枚数项全 0")
    check(fw["damaten_tsumo_score"] > 0.0, "已和牌帧：默听自摸打点 = 和牌得点（>0）")
    check(fw["damaten_ron_score"] > 0.0, "已和牌帧：默听荣和打点（平和 >0）")

    # m02075：带「副露」字样的 6 项，门清手牌也要按「有副露」假设算
    fp = expect.values(state_for(h2), 0)          # h2 只有平和（副露状态不存在）
    eq(fp["furo_ron_tenpai_expect"], 0.0, "副露假设（门清手牌只有平和）：副露荣和期望枚数 0")
    eq(fp["furo_tsumo_tenpai_expect"], 0.0, "副露假设（门清手牌只有平和）：副露自摸期望枚数 0")
    eq(fp["furo_ron_score"] + fp["furo_tsumo_score"], 0.0, "副露假设：副露期望打点 0")
    eq(fp["menzen_tenpai_expect"], 8.0, "同一手的门清枚数仍是 8（两套假设并存）")
    tanyao = ids([1, 2, 3, 4, 5, 6, 10, 11, 12, 15, 15, 22, 23])   # 234m456m234p66p56s（断幺九）
    ety = expect.Expect(state_for(tanyao), 0)
    fty = expect.values(state_for(tanyao), 0)
    eq(fty["furo_ron_tenpai_expect"], 8.0, "副露假设（断幺九）：副露荣和期望枚数 8")
    near(fty["furo_ron_score"], 1000.0, "副露假设（断幺九）：副露荣和期望打点 1000")
    eq(set(ety.node(ety.counts).keys()), node_keys(),
       "节点字典 = 36 个键（枚数分子 12 + 枚数分母 12 + 打点分子 6 + 打点分母 6）")

    # m02073：概率分步扣掉「已假想摸进」的牌（不会摸到第 5 张）
    five = ids([22, 22, 22, 0, 1, 2, 3, 4, 5, 10, 11, 12, 26])
    ef = expect.Expect(state_for(five), 0)
    used = [0] * 34
    used[22] = 1
    eq(ef._avail_left(used)[22], 0, "手里 3 张 5s + 假想摸 1 张 => 剩余 0（摸不到第 5 张）")
    eq(ef._unseen_left(used), ef.unseen - 1, "概率分母同步减 1")

    # 表宝牌计入期望打点（宝牌指示牌是场上公开信息；不能用来满足起和条件）
    st_d = state_for(h2, dora=[20 * 4])            # 指示牌 3s => 宝牌 4s：4s/7s 两面里的 4s 多 1 番
    e_d = expect.Expect(st_d, 0)
    f_d = expect.values(st_d, 0)
    eq(f_d["menzen_tenpai_expect"], 8.0, "宝牌：期望听牌枚数不受宝牌影响（仍 8）")
    near(f_d["damaten_ron_score"], (4 * 2000 + 4 * 1000) / 8.0,
         "宝牌：默听荣和期望打点 = (4x2000 + 4x1000)/8 = 1500（m02389：叶子概率先归一化后加权）")
    near(f_d["damaten_tsumo_score"], (4 * 2700 + 4 * 1500) / 8.0,
         "宝牌：默听自摸期望打点 = (4x2700 + 4x1500)/8 = 2100（4s 3 番 20 符 / 7s 2 番 20 符）")
    # m02389：打牌层仍然按 argmax{p(和牌) x 打点} 选分支，但报告值是同一分支上的条件期望
    fake = [
        {("sc", expect.RIICHI_ASSUME, RON): 2.0, ("ms", expect.RIICHI_ASSUME, RON): 0.10},
        {("sc", expect.RIICHI_ASSUME, RON): 1.8, ("ms", expect.RIICHI_ASSUME, RON): 0.02},
    ]
    near(e_d._pick_score(fake, expect.RIICHI_ASSUME, RON), 20.0,
         "期望打点：按 p x 打点 选分支后取该分支的条件期望（2.0/0.10；另一分支 1.8/0.02 = 90 不选）")
    near(e_d._pick_score([{("sc", expect.RIICHI_ASSUME, RON): 0.0,
                           ("ms", expect.RIICHI_ASSUME, RON): 0.0}], expect.RIICHI_ASSUME, RON),
         0.0, "期望打点：分母为 0（和不了）时给 0，不做 0/0")
    # m02647：听牌枚数同样先归一化 —— 分子 Σp·枚数 / 分母 Σp；best 口径按分子 argmax 选一手
    TP_SUM = ("tp", expect.FURO_ASSUME, "sum", TSUMO, "avail")
    TQ_SUM = ("tq", expect.FURO_ASSUME, "sum", TSUMO, "avail")
    fake2 = [{TP_SUM: 10.0, TQ_SUM: 0.50}, {TP_SUM: 8.0, TQ_SUM: 0.10}]
    near(e_d._pick_tenpai(fake2, TP_SUM, TQ_SUM, "sum"), 18.0 / 0.60,
         "期望枚数：sum 口径先把分子 / 分母各自求和再相除（(10+8)/(0.5+0.1)）")
    near(e_d._pick_tenpai(fake2, TP_SUM, TQ_SUM, "best"), 20.0,
         "期望枚数：best 口径按分子最大的那一手取条件期望（10/0.5；另一手 8/0.1 = 80 不选）")
    near(e_d._pick_tenpai([{TP_SUM: 0.0, TQ_SUM: 0.0}], TP_SUM, TQ_SUM, "sum"), 0.0,
         "期望枚数：分母为 0（到不了听牌）时给 0，不做 0/0")
    eq(e_d.node(e_d.counts)[("tq", expect.MENZEN_ASSUME, "sum", "avail")], 1.0,
       "门清听牌叶子：门清自摸必有役 => 计入归一化分母（1.0，m02647 / m02766）")
    eq(e_d.node(e_d.counts)[TQ_SUM], 0.0,
       "副露假设下无役的听牌叶子不计入归一化分母（0.0，m02766：E[枚数 | 有役听牌]）")
    eq(ety.node(ety.counts)[TQ_SUM], 1.0, "副露假设下断幺九是役 => 叶子计入分母（1.0，m02766）")
    check(f_d["damaten_ron_score"] > expect.values(state_for(h2), 0)["damaten_ron_score"],
          "宝牌：计入表宝牌后期望打点变大")

    # 范畴外：牌数不对 -> 全 0
    fbad = expect.values(state_for(ids([0, 1, 2])), 0)
    eq(sum(fbad.values()), 0.0, "手牌张数不对：12 项全 0")
    # 超范围：max_shanten=0 时向听 1 的手牌全 0
    hfar = ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 22, 26])      # 5s7s9s 型
    e_far = expect.Expect(state_for(hfar), 0, max_shanten=0)
    eq(e_far.dist(e_far.counts) > 0, True, "超范围用例：该手牌向听 > 0")
    ffar = expect.values(state_for(hfar), 0, max_shanten=0)
    eq(sum(ffar.values()), 0.0, "超范围（max_shanten=0）：12 项全 0")


def section3():
    print("=== 3. 独立参考实现（叶子：副露 / 立直 / 默听三种打点假设 + 门清枚数）===")
    files = corpus()[:3]
    n = 0
    bad = []
    for st, seat, c in tenpai_hands(files):
        if n >= 120:
            break
        n += 1
        e = expect.Expect(st, seat)
        g = e.node(c)                        # 直接取叶子的内部键值 ("tp"/"tq"/"sc", ...)
        # m02647 / m02766：叶子分母 = 1.0 当且仅当该假设 / 模式下有「过起和役门槛的和牌张」
        for kk in node_keys():
            if kk[0] != "tq":
                continue
            if kk[1] == expect.FURO_ASSUME:
                want = 1.0 if ref_yaku_ok(e, c, kk[3] == TSUMO, expect.FURO_ASSUME) else 0.0
            elif e.menzen:
                want = 1.0                       # 门清枚数项：门清自摸必有役 => 每个听牌叶子都算
            else:
                continue
            if g[kk] != want:
                bad.append((kk[1], "tq", kk, g[kk], want))
        assumes = [expect.FURO_ASSUME]
        if e.menzen:
            assumes += [expect.RIICHI_ASSUME, expect.DAMATEN_ASSUME]
        for assume in assumes:
            for mode in (TSUMO, RON):
                av, ab, sc, ms = ref_leaf(e, c, mode == TSUMO, assume=assume)
                pairs = [(g[("sc", assume, mode)], sc), (g[("ms", assume, mode)], ms)]
                if assume == expect.FURO_ASSUME:
                    pairs += [(g[("tp", assume, "sum", mode, "avail")], av),
                              (g[("tp", assume, "sum", mode, "abs")], ab)]
                for got, want in pairs:
                    if abs(got - want) > 1e-6:
                        bad.append((assume, mode, got, want, c))
        if e.menzen:                         # 门清枚数项：全部形状听牌（与假设 / 模式无关）
            av, ab = ref_leaf(e, c, True, assume=expect.MENZEN_ASSUME, all_waits=True)[:2]
            for got, want in ((g[("tp", expect.MENZEN_ASSUME, "sum", "avail")], av),
                              (g[("tp", expect.MENZEN_ASSUME, "sum", "abs")], ab)):
                if abs(got - want) > 1e-6:
                    bad.append((expect.MENZEN_ASSUME, "tp", got, want, c))
    eq(len(bad), 0, "叶子逐键与独立参考一致（%d 个听牌手牌 x 3 种打点假设 + 门清枚数 + 有役听牌分母）" % n)
    for b in bad[:5]:
        print("    差异 假设 %s 模式 %s：模块 %.6f vs 参考 %.6f（手牌 %s）" % b)


def section3b():
    print("=== 3b. 14 张「打一张即听」的帧：独立一层聚合 ===")
    n = 0
    bad = []
    for ev, st, seat in frames(corpus()[:2]):
        if n >= 20:
            break
        pl = st["players"][seat]
        c = agari.counts_of(pl["hand"])
        e = expect.Expect(st, seat)
        if e.dist(c) == -1:                  # 14 张已经和牌：走的是「和牌帧」分支，枚数按设计为 0
            continue
        disc = [k for k in range(34) if c[k] > 0]
        ds = dict((k, e.dist(sub(c, k))) for k in disc)
        if min(ds.values()) != 0 or sum(c) != e.n13 + 1:
            continue
        keep = [k for k in disc if ds[k] == 0]
        n += 1
        f_sum, f_best = expect.values_both(st, seat)
        assumes = [expect.FURO_ASSUME]
        if e.menzen:
            assumes += [expect.RIICHI_ASSUME, expect.DAMATEN_ASSUME]
        for assume in assumes:
            for mode in (TSUMO, RON):
                avs = []
                abss = []
                nums = []
                dens = []
                oks = []
                for k in keep:
                    a1, a2, s1, m1 = ref_leaf(e, sub(c, k), mode == TSUMO, assume=assume)
                    avs.append(a1)
                    abss.append(a2)
                    nums.append(s1)
                    dens.append(m1)
                    oks.append(ref_yaku_ok(e, sub(c, k), mode == TSUMO, assume))
                i = max(range(len(keep)), key=lambda j: nums[j])     # 打牌层 argmax{p x 打点}
                want_sc = (nums[i] / dens[i]) if dens[i] > 0 else 0.0
                nkeep = float(len(keep))     # 门清枚数项：门清自摸必有役 => 每个听牌叶子都算
                nfuro = float(sum(1 for o in oks if o))              # 副露：只数有役听牌（m02766）
                if assume == expect.FURO_ASSUME:
                    k_sc = expect.SCORE_KEYS[(expect.FURO, mode)]
                    k_av = expect.TENPAI_KEYS[(expect.FURO, mode, "avail")]
                    k_ab = expect.TENPAI_KEYS[(expect.FURO, mode, "abs")]
                    # m02766：全帧没有有役听牌 => 模块 _pick_tenpai 分母 <= 0 记 0.0，参考侧同样
                    v_av = (sum(avs) / nfuro) if nfuro > 0 else 0.0
                    v_ab = (sum(abss) / nfuro) if nfuro > 0 else 0.0
                    pairs = [(f_sum[k_sc], want_sc),
                             (f_sum[k_av], v_av), (f_sum[k_ab], v_ab),
                             (f_best[k_av], max(avs)), (f_best[k_ab], max(abss))]
                    tag = k_av
                else:
                    cat = RIICHI if assume == expect.RIICHI_ASSUME else DAMATEN
                    k_sc = expect.SCORE_KEYS[(cat, mode)]
                    # 门清的枚数项是「模式 / 假设无关」的（门清自摸必有役 => 全部形状听牌张），
                    # 只和自摸模式的参考比；荣和模式只比打点项。
                    pairs = [(f_sum[k_sc], want_sc)]
                    if mode == TSUMO:
                        k_av = expect.MENZEN_TENPAI_KEYS["avail"]
                        k_ab = expect.MENZEN_TENPAI_KEYS["abs"]
                        pairs += [(f_sum[k_av], sum(avs) / nkeep), (f_sum[k_ab], sum(abss) / nkeep),
                                  (f_best[k_av], max(avs)), (f_best[k_ab], max(abss))]
                    tag = k_sc
                for got, want in pairs:
                    if abs(got - want) > 1e-6:
                        bad.append((assume, mode, tag, got, want))
    eq(len(bad), 0, "14 张聚合（sum/best x 副露/立直/默听，枚数按 m02647 + m02766 归一化）与独立参考一致（%d 帧）" % n)
    for b in bad[:5]:
        print("    差异 %s" % (b,))


def section3c():
    print("=== 3c. 进张概率扣减：向听 1 的帧（独立一层枚举，每步扣掉假想摸进的牌）===")
    hands = [
        ids([0, 1, 2, 3, 4, 5, 10, 11, 12, 15, 15, 23, 26]),        # 123m456m234p66p6s9s
        ids([1, 2, 3, 4, 5, 6, 10, 11, 12, 15, 15, 23, 26]),        # 234m456m234p66p6s9s
    ]
    n = 0
    bad = []
    for hand in hands:
        st = state_for(hand)
        e = expect.Expect(st, 0, max_shanten=1)
        if e.dist(e.counts) != 1:
            bad.append(("向听不是 1", e.dist(e.counts)))
            continue
        n += 1
        f, alt = e.compute()
        assumes = [expect.FURO_ASSUME]
        if e.menzen:
            assumes += [expect.RIICHI_ASSUME, expect.DAMATEN_ASSUME]
        for assume in assumes:
            vals, scs = ref_frame(e, e.counts, assume)
            if assume == expect.FURO_ASSUME:
                pairs = [
                    (f[expect.TENPAI_KEYS[(expect.FURO, TSUMO, "avail")]],
                     vals[("sum", TSUMO, "avail")]),
                    (f[expect.TENPAI_KEYS[(expect.FURO, RON, "avail")]],
                     vals[("sum", RON, "avail")]),
                    (f[expect.TENPAI_KEYS[(expect.FURO, TSUMO, "abs")]],
                     vals[("sum", TSUMO, "abs")]),
                    (f[expect.TENPAI_KEYS[(expect.FURO, RON, "abs")]],
                     vals[("sum", RON, "abs")]),
                    (f[expect.SCORE_KEYS[(expect.FURO, TSUMO)]], scs[TSUMO]),
                    (f[expect.SCORE_KEYS[(expect.FURO, RON)]], scs[RON]),
                    (alt[expect.TENPAI_KEYS[(expect.FURO, TSUMO, "avail")]],
                     vals[("best", TSUMO, "avail")]),
                    (alt[expect.TENPAI_KEYS[(expect.FURO, RON, "abs")]],
                     vals[("best", RON, "abs")]),
                ]
            else:
                cat = RIICHI if assume == expect.RIICHI_ASSUME else DAMATEN
                pairs = [
                    (f[expect.SCORE_KEYS[(cat, TSUMO)]], scs[TSUMO]),
                    (f[expect.SCORE_KEYS[(cat, RON)]], scs[RON]),
                ]
                if assume == expect.RIICHI_ASSUME:      # 门清枚数项与假设无关，只比一次
                    pairs += [
                        (f[expect.MENZEN_TENPAI_KEYS["avail"]], vals[("sum", TSUMO, "avail")]),
                        (f[expect.MENZEN_TENPAI_KEYS["abs"]], vals[("sum", TSUMO, "abs")]),
                        (alt[expect.MENZEN_TENPAI_KEYS["avail"]], vals[("best", TSUMO, "avail")]),
                    ]
            for got, want in pairs:
                if abs(got - want) > 1e-6:
                    bad.append((assume, got, want))
    eq(len(bad), 0, "向听 1 的帧：概率扣减 + 枚数归一化后与独立一层枚举一致（%d 个手牌 x 副露/立直/默听）" % n)
    for b in bad[:5]:
        print("    差异 %s" % (b,))


def section4():
    print("=== 4. 不变量 + 语料子集耗时（cap=0）===")
    files = corpus()[5:7]
    n = 0
    bad = []
    buckets = {}
    t_all = 0.0
    for ev, st, seat in frames(files):
        e = expect.Expect(st, seat, max_shanten=0)
        d = e.dist(e.counts)
        if d > 0:
            continue
        t1 = time.perf_counter()
        f, alt = expect.values_both(st, seat, max_shanten=0)
        dt = time.perf_counter() - t1
        t_all += dt
        n += 1
        b = buckets.setdefault(d, [0, 0.0])
        b[0] += 1
        b[1] += dt
        for k in expect.KEYS:
            if f[k] < 0 or f[k] != f[k]:
                bad.append(("负值/NaN", k, f[k]))
        if f["furo_tsumo_tenpai_abs"] + 1e-9 < f["furo_tsumo_tenpai_expect"]:
            bad.append(("绝对 < 期望", "furo_tsumo", f["furo_tsumo_tenpai_abs"], f["furo_tsumo_tenpai_expect"]))
        if f["furo_ron_tenpai_abs"] + 1e-9 < f["furo_ron_tenpai_expect"]:
            bad.append(("绝对 < 期望", "furo_ron", f["furo_ron_tenpai_abs"], f["furo_ron_tenpai_expect"]))
        if f["menzen_tenpai_abs"] + 1e-9 < f["menzen_tenpai_expect"]:
            bad.append(("绝对 < 期望", "menzen", f["menzen_tenpai_abs"], f["menzen_tenpai_expect"]))
        for k in expect.KEYS:
            if k.endswith("_score") and 0.0 < f[k] < 1000.0 - 1e-9:
                bad.append(("打点在 (0,1000)：和牌得点最低 1000，疑归一化分母出错", k, f[k]))
        if d == -1:
            for k in expect.KEYS:
                if k.endswith("tenpai_expect") or k.endswith("tenpai_abs"):
                    if f[k] != 0.0:
                        bad.append(("和牌帧枚数非 0", k, f[k]))
        if d > 0:
            if sum(f.values()) != 0.0:
                bad.append(("cap=0 时向听 %d 应为全 0" % d, "sum", sum(f.values())))
    eq(len(bad), 0,
       "不变量（非负 / 绝对>=期望 / 打点非 0 则 >=1000 / 和牌帧枚数 0 / 超范围全 0）：%d 帧" % n)
    if bad:
        for b in bad[:5]:
            print("    违规 %s" % (b,))
    print("    帧数 %d，总耗时 %.1f s（平均 %.4f s/帧，cap=0）" % (n, t_all, t_all / max(1, n)))
    for d in sorted(buckets):
        b = buckets[d]
        print("    向听 %2d：%4d 帧，平均 %.4f s" % (d, b[0], b[1] / b[0]))
    return n, t_all


def main():
    t0 = time.perf_counter()
    n1 = section1()
    section2()
    section3()
    section3b()
    section3c()
    n4, t4 = section4()
    print("=== 结果：通过 %d 项，失败 %d 项 ===（总耗时 %.1f s）" % (OK[0], BAD[0], time.perf_counter() - t0))
    if BAD[0] == 0:
        print("全部通过")
    return 1 if BAD[0] else 0


if __name__ == "__main__":
    sys.exit(main())