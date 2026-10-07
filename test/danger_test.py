# -*- coding: utf-8 -*-
r"""第 20 轮：立直家（他家）危险筋组数量 / 危险两面组数（`mjscore/danger.py`，用户 m02865）。

覆盖：
  1. 筋组表：18 组、两两不重复、両面 = 中间隔开的两张、每种花色各 6 组
  2. 手算用例（合成状态 + 合成出牌序）：-1 条件（与第一类特征「立直家（他家）数量」一致）、
     立直家打出过的牌（含被其他家鸣走的）、立直动作之后别家的出牌、② 両面看到 4 张、
     両面剩余张数的乘法（用户 m02865 的例子：筋组 14m 危险、看到 2 张 2m 与 1 张 3m => 6 组）、
     多家立直「安全 = 对全体立直家均安全」的连词逻辑
  3. 全量语料：71 个牌谱的摸牌帧 / 吃碰帧，与独立参考实现（安全牌改走「各家牌河后缀」）逐帧对拍；
     不变量（-1 条件、0..18、危险组数为 0 <=> 两面组数为 0）、出牌序与各家牌河的一致性、分布、耗时
  4. `values_at()` 一次性取数（回放到该帧再算）与逐帧流式取数抽样对拍

运行：& 'D:\coding\anaconda3\envs\py314_null\python.exe' test\danger_test.py
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

from mjscore import danger, feats, mjlog, replay, shanten

OK = [0]
BAD = [0]
SUJI_KEY = danger.KEYS[0]
RYANMEN_KEY = danger.KEYS[1]


def check(cond, label):
    if cond:
        OK[0] += 1
        print("  OK   " + label)
    else:
        BAD[0] += 1
        print("  FAIL " + label)


def eq(got, want, label):
    check(got == want, "%s（got %r / want %r）" % (label, got, want))


def ids_of(kinds):
    """牌种列表 -> 牌 id 列表（同种重复用同一个 id；本模块只看张数/牌种）。"""
    return [k * 4 for k in kinds]


def tid(k):
    return k * 4


def mk_state(hand, rivers=None, riichi=(), melds=None, dora=()):
    """合成一帧的状态：hand = 自己（座位 0）的手牌牌 id；rivers = {座位: [牌 id]}；
    riichi = 立直家座位集合；melds = {座位: [副露]}；dora = 宝牌指示牌 id 列表。"""
    players = []
    for s in range(4):
        riv = [{"tile": t, "tsumogiri": False, "riichi": False, "called": False, "win": False}
               for t in (rivers or {}).get(s, [])]
        players.append({"hand": list(hand) if s == 0 else [],
                        "melds": list((melds or {}).get(s, [])),
                        "river": riv, "riichi": s in riichi, "riichiPending": False,
                        "score": 25000, "name": "P%d" % s, "turns": len(riv)})
    return {"players": players, "dora": list(dora), "dices": (1, 1), "drawn": None,
            "tilesLeft": 70, "oya": 0, "honba": 0, "kyotaku": 0, "round": 0,
            "scores": [25000] * 4, "phase": "play", "warnings": [], "reveal": [],
            "result": None, "desc": "", "evIndex": 0}


def mk_log(entries, reach_at=None):
    """合成出牌序：entries = [(座位, 牌 id)]（按全局顺序）；reach_at = {座位: 宣告时的出牌数}。"""
    log = danger.DangerLog()
    for p, t in entries:
        log.seq.append((p, t // 4))
    log.reach_at = dict(reach_at or {})
    return log


# 14 张手牌：2m2m3m + 1111z 2222z 333z（m 侧只看到 2m 两张、3m 一张，其余花色一张没看到）
HAND14 = [1, 1, 2] + [27] * 4 + [28] * 4 + [29] * 3


def section1():
    """筋组表。"""
    eq(len(danger.SUJI), 18, "筋组共 18 组（三种花色 x {1,4},{2,5},{3,6},{4,7},{5,8},{6,9}）")
    eq(len(set(danger.SUJI)), 18, "18 个筋组两两不重复")
    ok = True
    per = {}
    for k1, k2, r1, r2 in danger.SUJI:
        per[k1 // 9] = per.get(k1 // 9, 0) + 1
        if k2 != k1 + 3 or r1 != k1 + 1 or r2 != k1 + 2:
            ok = False
        if k1 % 9 > 5:
            ok = False                       # 只到 {6,9}，不出现 {7,10}
    check(ok, "每组 = (n, n+3)，両面 = 中间隔开的两张 (n+1, n+2)")
    eq(sorted(per.values()), [6, 6, 6], "m / p / s 各 6 组")
    eq([g for g in danger.SUJI if g[0] == 1], [(1, 4, 2, 3)], "筋组 25m 对应両面 34m")
    eq(danger.NAMES[SUJI_KEY], "立直家（他家）危险筋组数量", "特征名 = 立直家（他家）危险筋组数量")
    eq(danger.NAMES[RYANMEN_KEY], "立直家（他家）危险两面组数", "特征名 = 立直家（他家）危险两面组数")
    eq(danger.RANGES[SUJI_KEY], (-1, 18), "取值域 -1 或 0..18")
    eq(danger.RANGES[RYANMEN_KEY][0], -1, "取值域从 -1 起（非负整数）")


def section2():
    """手算用例。"""
    # ---- 没有他家立直 => 两项都是 -1；判定与第一类特征一致
    st0 = mk_state(ids_of(HAND14))
    eq(danger.values(st0, 0), {SUJI_KEY: -1, RYANMEN_KEY: -1},
       "其他家无人立直 => 两项都是 -1")
    eq(feats.extract(st0, 0)["riichi_others_n"], 0,
       "-1 条件与第一类特征「立直家（他家）数量」= 0 一致")
    # 自己立直不算「立直家（他家）」
    st_self = mk_state(ids_of(HAND14), riichi={0})
    eq(danger.values(st_self, 0), {SUJI_KEY: -1, RYANMEN_KEY: -1},
       "只有自己立直 => 仍然 -1（-1 只看其他家）")

    # ---- 立直家只打出过 4z（字牌不属于任何筋组）：18 组全部危险
    #      主视角只看到 2m x2、3m x1（都在自己手里）=> 筋组 14m 的两面 23m：
    #      2m 剩 2 张 x 3m 剩 3 张 = 6 组（用户 m02865 的算例）
    stc = mk_state(ids_of(HAND14), rivers={1: [tid(30)]}, riichi={1})
    logc = mk_log([(1, tid(30))], {1: 1})
    eq(danger.values(stc, 0, logc), {SUJI_KEY: 18, RYANMEN_KEY: 274},
       "只有 4z 是安全牌 => 18 组全危险、两面组数 274")
    detail = danger.groups_detail(stc, 0, logc)
    eq([(g[0], g[1], g[6]) for g in detail if g[0] == 0], [(0, 3, 6)],
       "筋组 14m 危险时両面 23m 的组数 = 2 x 3 = 6（用户 m02865 的例子）")

    # ---- 立直家打出过 3m + 立直之后别家打出 9m：{3,6}m 与 {6,9}m 安全
    st = mk_state(ids_of(HAND14), rivers={1: [tid(2)], 2: [tid(8)]}, riichi={1})
    log = mk_log([(1, tid(2)), (2, tid(8))], {1: 1})
    eq(danger.values(st, 0, log), {SUJI_KEY: 16, RYANMEN_KEY: 236},
       "安全牌 {3m, 9m} => 16 组危险、两面组数 236")
    safe_groups = [(g[0], g[1]) for g in danger.groups_detail(st, 0, log) if g[4]]
    eq(sorted(safe_groups), [(2, 5), (5, 8)], "安全的是 {3,6}m 与 {6,9}m 两个筋组")

    # ---- 立直动作「之前」别家打出的牌不算安全牌（同一张 9m 换到 reach_at 之后就不是安全牌了）
    log_pre = mk_log([(1, tid(2)), (2, tid(8))], {1: 2})
    check(8 not in danger.safe_kinds(st, 1, log_pre),
          "立直动作之前别家打出的 9m 不算安全牌")
    eq(danger.values(st, 0, log_pre), {SUJI_KEY: 17, RYANMEN_KEY: 252},
       "立直前打出的 9m 不算安全牌、3m 是唯一安全牌 => 17 组危险、两面组数 252")

    # ---- ② 両面的一种牌能看到 4 张（4p 暗槓 4 张）=> {2,5}p 与 {3,6}p 两组安全
    stb = mk_state(ids_of(HAND14), rivers={1: [tid(2)], 2: [tid(8)]}, riichi={1},
                   melds={3: [{"callType": "kakan", "tiles": [tid(12)] * 4,
                               "calledId": None, "from": None, "open": True}]})
    eq(danger.values(stb, 0, log), {SUJI_KEY: 14, RYANMEN_KEY: 204},
       "看到 4 张 4p => {2,5}p / {3,6}p 两组安全（14 组危险、204 组两面）")
    blocked = [(g[0], g[1]) for g in danger.groups_detail(stb, 0, log) if g[5]]
    eq(sorted(blocked), [(10, 13), (11, 14)], "② 命中的是両面含 4p 的两个筋组")

    # ---- 被其他家鸣走的牌仍算立直家打出过的牌
    stk = mk_state(ids_of(HAND14), rivers={1: [tid(2)]}, riichi={1})
    stk["players"][1]["river"][0]["called"] = True
    stk["players"][2]["melds"] = [{"callType": "chi", "tiles": [tid(1), tid(2), tid(3)],
                                   "calledId": tid(2), "from": 1, "open": True}]
    check(2 in danger.safe_kinds(stk, 1, danger.DangerLog()),
          "立直家被鸣走的牌（牌河条目标 called）仍算它的安全牌")

    # ---- 多家立直：安全 = 对全体立直家均安全
    st1 = mk_state(ids_of(HAND14), rivers={1: [tid(2)], 2: [tid(3)]}, riichi={1, 2})
    log1 = mk_log([(1, tid(2)), (2, tid(3))], {1: 2, 2: 2})
    eq(danger.values(st1, 0, log1), {SUJI_KEY: 18, RYANMEN_KEY: 262},
       "两家立直各只挡住一个筋组 => 任何筋组都不是对两家都安全（18 组全危险）")
    st2 = mk_state(ids_of(HAND14), rivers={1: [tid(2)], 2: [tid(2)]}, riichi={1, 2})
    log2 = mk_log([(1, tid(2)), (2, tid(2))], {1: 2, 2: 2})
    eq(danger.values(st2, 0, log2), {SUJI_KEY: 17, RYANMEN_KEY: 246},
       "两家立直都打出过 3m => {3,6}m 对两家都安全（17 组危险）")

    # ---- 有他家立直时必须给 DangerLog（安全牌要用全局出牌序）
    try:
        danger.values(stc, 0)
        check(False, "有他家立直时不传 DangerLog 应当报错")
    except ValueError:
        check(True, "有他家立直时不传 DangerLog 报错")


def ref_suji():
    """独立参考用的筋组表（换个写法生成，避免与模块共用同一个表达式）。"""
    out = []
    for s in range(3):
        for a, b in ((1, 4), (2, 5), (3, 6), (4, 7), (5, 8), (6, 9)):
            k1 = s * 9 + a - 1
            k2 = s * 9 + b - 1
            out.append((k1, k2, k1 + 1, k1 + 2))
    return out


def ref_values(st, seat, seq, reach_at):
    """独立参考：安全牌改走「各家牌河后缀」。

    cut = 立直宣告时的全局出牌序号；对每家 p，它在该时刻已打出的张数 = seq[:cut] 里 p 的
    条目数 => 该家牌河的第 [已打出:] 条起就是「立直动作发生后」打出的牌（牌河条目含被鸣
    走的那张，所以张数对得上）。
    """
    riichis = [s for s in range(4) if s != seat and feats.is_riichi(st["players"][s])]
    if not riichis:
        return (-1, -1)
    seen = shanten.visible_counts(st, seat)
    safes = {}
    for x in riichis:
        s = set(r["tile"] // 4 for r in st["players"][x]["river"])
        before = {}
        for p, _k in seq[:reach_at[x]]:
            before[p] = before.get(p, 0) + 1
        for p in range(4):
            for r in st["players"][p]["river"][before.get(p, 0):]:
                s.add(r["tile"] // 4)
        safes[x] = s
    n1 = 0
    n2 = 0
    for k1, k2, r1, r2 in ref_suji():
        if seen[r1] >= 4 or seen[r2] >= 4:
            continue
        if all(k1 in safes[x] or k2 in safes[x] for x in riichis):
            continue
        n1 += 1
        n2 += max(0, 4 - seen[r1]) * max(0, 4 - seen[r2])
    return (n1, n2)


def corpus():
    files = sorted(glob.glob(os.path.join(ROOT, "data", "**", "*.xml"), recursive=True))
    files += sorted(glob.glob(os.path.join(ROOT, "data_extra", "*.xml")))
    return files


def frame_seat(events, i, ev):
    """这一个事件是不是打点帧（摸牌帧 / 吃碰帧）；是就返回该家座位，否则 None。"""
    if ev["type"] == "draw":
        nxt = events[i + 1] if i + 1 < len(events) else None
        if (nxt is not None and nxt["type"] == "agari" and nxt["winner"] == ev["player"]
                and nxt["fromWho"] == ev["player"]):
            return None                      # 自摸和了：本轮打点排除
        return ev["player"]
    if ev["type"] == "call" and ev["callType"] in ("chi", "pon"):
        return ev["player"]
    return None


def section3():
    """全量语料：独立参考对拍 + 不变量 + 分布 + 耗时。"""
    files = corpus()
    n = 0
    n_riichi = 0
    n_multi = 0
    diffs = 0
    bad = 0
    log_bad = 0
    n_reach = 0
    dist1 = {}
    dist2 = {}
    t0 = time.perf_counter()
    for fn in files:
        game = mjlog.game_from_file(fn)
        for ri in range(len(game["rounds"])):
            events = game["rounds"][ri]["events"]
            st = replay.initial_state(game, ri)
            log = danger.DangerLog()
            for i, ev in enumerate(events):
                replay.apply_event(st, ev)
                st["evIndex"] = i
                log.feed(ev)
                seat = frame_seat(events, i, ev)
                if seat is None:
                    continue
                n += 1
                v = danger.values(st, seat, log)
                got = (v[SUJI_KEY], v[RYANMEN_KEY])
                rv = ref_values(st, seat, list(log.seq), dict(log.reach_at))
                if got != rv:
                    diffs += 1
                    if diffs <= 5:
                        print("    差异 %s ri=%d ev=%d seat=%d 模块 %s / 参考 %s" % (
                            os.path.basename(fn)[:24], ri, i, seat, got, rv))
                rc = feats.extract(st, seat)["riichi_others_n"]
                if rc == 0:
                    if got != (-1, -1):
                        bad += 1
                else:
                    n_riichi += 1
                    if rc >= 2:
                        n_multi += 1
                    if not (0 <= got[0] <= 18 and 0 <= got[1] <= 288):
                        bad += 1
                    if (got[0] == 0) != (got[1] == 0):
                        bad += 1
                    dist1[got[0]] = dist1.get(got[0], 0) + 1
                    dist2[got[1]] = dist2.get(got[1], 0) + 1
            # 局末：全局出牌序 vs 各家牌河（含被鸣走的牌）逐牌种核对
            for p in range(4):
                cnt = {}
                for q, k in log.seq:
                    if q == p:
                        cnt[k] = cnt.get(k, 0) + 1
                riv = {}
                for r in st["players"][p]["river"]:
                    riv[r["tile"] // 4] = riv.get(r["tile"] // 4, 0) + 1
                if cnt != riv:
                    log_bad += 1
            n_reach += len(log.reach_at)
    t_all = time.perf_counter() - t0
    print("    帧数 %d（其中有他家立直 %d，多家立直 %d）；立直宣告 %d 次；耗时 %.1f s（%.3f ms/帧）" % (
        n, n_riichi, n_multi, n_reach, t_all, t_all * 1000.0 / max(1, n)))
    eq(diffs, 0, "与独立参考实现逐帧一致（%d 帧，差异 %d）" % (n, diffs))
    eq(bad, 0, "不变量：-1 条件 / 0..18 / 危险组数为 0 <=> 两面组数为 0")
    eq(log_bad, 0, "出牌序与各家牌河逐牌种一致（每局 4 家）")
    check(n > 30000, "语料帧数 %d > 30000（71 个牌谱）" % n)
    print("    危险筋组数量分布（-1 的 %d 帧未计入）：%s" % (n - n_riichi, sorted(dist1.items())))
    vals2 = sorted(dist2.items())
    print("    危险两面组数：min %d / max %d / 平均 %.2f / 档位 %s" % (
        vals2[0][0], vals2[-1][0],
        sum(k * c for k, c in vals2) / float(n_riichi), [k for k, _c in vals2]))
    return n, t_all


def section4():
    """values_at() 一次性取数与逐帧流式取数抽样对拍。"""
    files = corpus()
    checked = 0
    bad = 0
    for fn in files[:10]:
        game = mjlog.game_from_file(fn)
        for ri in range(len(game["rounds"])):
            events = game["rounds"][ri]["events"]
            st = replay.initial_state(game, ri)
            log = danger.DangerLog()
            for i, ev in enumerate(events):
                replay.apply_event(st, ev)
                st["evIndex"] = i
                log.feed(ev)
                seat = frame_seat(events, i, ev)
                if seat is None or not danger.riichi_others(st, seat):
                    continue
                checked += 1
                if checked % 5:              # 每 5 帧抽一个，少跑几遍回放
                    continue
                v1 = danger.values(st, seat, log)
                v2 = danger.values_at(game, ri, i, seat)
                if v1 != v2:
                    bad += 1
                    if bad <= 3:
                        print("    差异 %s ri=%d ev=%d seat=%d %s / %s" % (
                            os.path.basename(fn)[:24], ri, i, seat, v1, v2))
    eq(bad, 0, "values_at() 与逐帧流式取数一致（抽样 %d 帧，差异 %d）" % (checked // 5, bad))


def main():
    t0 = time.perf_counter()
    print("=== 1. 筋组表 ===")
    section1()
    print("=== 2. 手算用例 ===")
    section2()
    print("=== 3. 全量语料 + 独立参考 ===")
    section3()
    print("=== 4. values_at() 抽样 ===")
    section4()
    print("=== 结果：通过 %d 项，失败 %d 项 ===（总耗时 %.1f s）" % (OK[0], BAD[0], time.perf_counter() - t0))
    if BAD[0] == 0:
        print("全部通过")
    return 1 if BAD[0] else 0


if __name__ == "__main__":
    sys.exit(main())