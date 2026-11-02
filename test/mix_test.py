# -*- coding: utf-8 -*-
r"""牌谱判重与 AI 分析合并（用户 m00001）回归测试。

覆盖：
  1. 真实重复对：两份 Mortal 报告（同局、不同模型 / 特征码）的牌局进程 hash 相同；
     合并为 [mix] 文件、删除源文件、模型 union、帧数据 union、幂等。
  2. 多模型 union：四份同局不同模型名的容器合并成四个模型槽。
  3. 跨来源规范化：骰子 / 天凤 m / kakan 4 张 vs 1 张 / reach step2 / 和牌细节都不影响 hash。
  4. 非同一局拒绝合并。
  5. 下载落盘后的自动合并入口（download._auto_mix）回填 entry / seen / results。
"""
import copy
import glob
import io
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mjscore import cli, download, mix, mortal  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OK = [0]
BAD = [0]
SRC1 = os.path.join(ROOT, "data", "paipu", "mortal", "718521d3073f9ee3.mortal-b")
SRC2 = os.path.join(ROOT, "data", "paipu", "mortal", "bbffcce78e5db531.mortal-c")


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


def fresh(name):
    p = os.path.join(ROOT, "build", "_scratch", name)
    shutil.rmtree(p, ignore_errors=True)
    os.makedirs(p, exist_ok=True)
    return p


def write_mix(path, game, sources=None):
    obj = {"mjscore_mix": 1, "created": 0, "game": game, "sources": sources or []}
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))


def test_real_pair():
    print("=== 1. 真实重复对：Mortal 同局不同模型 ===")
    check(os.path.isfile(SRC1) and os.path.isfile(SRC2), "两份 Mortal 样例存在")
    fp1 = mix.fingerprint_file(SRC1)
    fp2 = mix.fingerprint_file(SRC2)
    eq(fp1, fp2, "同局不同模型 -> 牌局进程 hash 相同")
    out = fresh("mix_real")
    p1 = os.path.join(out, os.path.basename(SRC1))
    p2 = os.path.join(out, os.path.basename(SRC2))
    shutil.copy2(SRC1, p1)
    shutil.copy2(SRC2, p2)
    res = mix.scan_and_merge(p2, root=out)
    check(res.get("merged"), "扫描命中并合并")
    mix_path = res.get("path") or ""
    eq(os.path.basename(mix_path), "[mix]718521d3073f9ee3.mortal-b", "输出名 = [mix] + 最早文件名")
    eq(sorted(os.listdir(out)), ["[mix]718521d3073f9ee3.mortal-b"], "只保留 mix 文件")
    eq(sorted(os.path.basename(x) for x in (res.get("removed") or [])),
       ["718521d3073f9ee3.mortal-b", "bbffcce78e5db531.mortal-c"], "新旧两份源文件都删除")
    eq(cli.report_kind(mix_path), "mix", "report_kind 认得 mix")
    eq(cli.file_log_id(mix_path), "[mix]718521d3073f9ee3", "file_log_id 用 mix 文件 stem")
    game = cli.game_from_file(mix_path)
    eq(game["meta"].get("mix"), True, "meta.mix")
    eq(game["meta"].get("viewer_seat"), 0, "viewer_seat 保留 0（不能被 or 吞掉）")
    eq(game["naga"].get("mix"), True, "naga.mix")
    eq(len(game["rounds"]), 13, "13 局")
    eq(len(game["naga"]["models"]), 2, "模型 union 两个槽")
    eq([m["name"] for m in game["naga"]["models"]],
       ["Mortal-4.1-平衡", "Mortal-4.1-争一"], "模型顺序 = base 在前")
    eq(game["naga"]["types"], {"0": "4.1b", "1": "4.1c"}, "naga.types 同步重映射")
    eq(game["naga"]["model_index"], 0, "model_index 仍在 base 模型")
    first = game["naga"]["rounds"][0][1]
    eq(len(first.get("dahai_pred") or []), 2, "首帧 dahai_pred 两个模型槽")
    counts = [0, 0]
    for rnd in game["naga"]["rounds"]:
        for fr in rnd:
            for i, val in enumerate(fr.get("dahai_pred") or []):
                if val:
                    counts[i] += 1
    eq(counts, [168, 168], "两个模型槽都有 168 帧预测数据")
    names = list(game["naga"].get("mix_sources") or [])
    eq(sorted(names), ["718521d3073f9ee3.mortal-b", "bbffcce78e5db531.mortal-c"], "来源文件名保留两份")
    with open(mix_path, "r", encoding="utf-8") as fh:
        container = json.load(fh)
    eq([x.get("report_id") for x in container.get("sources") or []],
       ["718521d3073f9ee3", "bbffcce78e5db531"], "容器 sources 保留 report_id")
    res2 = mix.scan_and_merge(mix_path, root=out)
    eq((res2.get("ok"), res2.get("merged"), res2.get("reason")), (True, False, "unique"),
       "再次扫描幂等（不重复合并）")


def test_model_union():
    print("=== 2. 四个模型槽 union ===")
    out = fresh("mix_union")
    base = mortal.game_from_file(SRC1)
    paths = []
    for i, tag in enumerate(("synth-a", "synth-b", "synth-c", "synth-d")):
        game = copy.deepcopy(base)
        game.pop("path", None)
        naga = game["naga"]
        naga["models"] = [{"index": 0, "raw": tag, "name": "合成模型-%d" % i, "series": "Mortal"}]
        naga["types"] = {"0": tag}
        naga["model_index"] = 0
        naga["report_id"] = "synth%d" % i
        naga["kind"] = "mortal"
        path = os.path.join(out, "synth%d.mortal-b" % i)
        write_mix(path, game)
        paths.append(path)
    res = mix.merge_paths(paths, delete=True)
    check(res.get("merged"), "四份同局容器合并")
    eq(len(res.get("models") or []), 4, "四个模型名")
    eq(sorted(os.listdir(out)), ["[mix]synth0.mortal-b"], "四份源文件删除，只留 mix")
    game = mix.game_from_file(res["path"])
    eq([m["name"] for m in game["naga"]["models"]], ["合成模型-%d" % i for i in range(4)], "模型顺序")
    frame = game["naga"]["rounds"][0][1]
    eq(len(frame["dahai_pred"]), 4, "首帧四个模型槽")
    counts = [0, 0, 0, 0]
    for rnd in game["naga"]["rounds"]:
        for fr in rnd:
            for i, val in enumerate(fr.get("dahai_pred") or []):
                if val:
                    counts[i] += 1
    eq(counts, [168, 168, 168, 168], "四个槽各有 168 帧")


def test_sequential_merge():
    print("=== 2a. 已有的 [mix] 再并第三份来源 ===")
    out = fresh("mix_sequential")
    p1 = os.path.join(out, os.path.basename(SRC1))
    p2 = os.path.join(out, os.path.basename(SRC2))
    shutil.copy2(SRC1, p1)
    shutil.copy2(SRC2, p2)
    first = mix.scan_and_merge(p2, root=out)
    check(first.get("merged"), "先合并两份")
    mix_path = first["path"]
    base = mortal.game_from_file(SRC2)
    base.pop("path", None)
    naga = base["naga"]
    naga["models"] = [{"index": 0, "raw": "4.1x", "name": "Mortal-4.1-第三家", "series": "Mortal"}]
    naga["types"] = {"0": "4.1x"}
    naga["model_index"] = 0
    naga["report_id"] = "third-report"
    naga["kind"] = "mortal"
    p3 = os.path.join(out, "third-report.mortal-b")
    write_mix(p3, base)
    second = mix.scan_and_merge(p3, root=out)
    check(second.get("merged"), "已有 mix 再并第三份")
    eq(os.path.basename(second["path"]), os.path.basename(mix_path), "输出仍是原来的 [mix] 名字")
    eq(sorted(os.listdir(out)), [os.path.basename(mix_path)], "第三次扫描后只留 mix")
    merged = mix.game_from_file(second["path"])
    eq([m["name"] for m in merged["naga"]["models"]],
       ["Mortal-4.1-平衡", "Mortal-4.1-争一", "Mortal-4.1-第三家"], "第三家追加到模型 union")
    eq(len(merged["naga"]["rounds"][0][1]["dahai_pred"]), 3, "首帧三个模型槽")
    eq(sorted(merged["naga"].get("mix_sources") or []),
       ["718521d3073f9ee3.mortal-b", "bbffcce78e5db531.mortal-c", "third-report.mortal-b"],
       "来源名保留三份原始文件，不列 [mix] 容器名")


def test_same_model_seats():
    print("=== 2b. 同一模型、四家视角的副露数据合并 ===")
    out = fresh("mix_seats")
    base = mortal.game_from_file(SRC1)
    paths = []
    for i in range(4):
        game = copy.deepcopy(base)
        game.pop("path", None)
        naga = game["naga"]
        naga["models"] = [{"index": 0, "raw": "4.1b", "name": "Mortal-4.1-平衡", "series": "Mortal"}]
        naga["types"] = {"0": "4.1b"}
        naga["model_index"] = 0
        naga["report_id"] = "seat%d" % i
        naga["kind"] = "mortal"
        # 第 0 局第 1 帧（0 号家摸牌）放一个只属于第 i 家视角的副露候选。
        naga["rounds"][0][1]["huro"] = {str(i): [{"0": 1000 + i}]}
        # 四家各自作为决策者的摸牌帧：都往同一模型槽写自己的预测，验证互不覆盖。
        seen_actor = set()
        for fr in naga["rounds"][0]:
            if fr.get("actor") == i and fr.get("msg") == "tsumo":
                vec = [0.0] * 34
                vec[33] = float(i + 1)
                fr["dahai_pred"] = [vec]
                seen_actor.add(i)
        check(seen_actor == {i}, "第 %d 家有自己的摸牌帧" % i)
        path = os.path.join(out, "seat%d.mortal-b" % i)
        write_mix(path, game)
        paths.append(path)
    res = mix.merge_paths(paths, delete=True)
    check(res.get("merged"), "四家视角合并")
    eq(len(res.get("models") or []), 1, "同名模型只占一个槽")
    game = mix.game_from_file(res["path"])
    frame = game["naga"]["rounds"][0][1]
    eq(sorted((frame.get("huro") or {}).keys()), ["0", "1", "2", "3"], "四家 huro 座位都保留")
    eq([frame["huro"][str(i)][0]["0"] for i in range(4)], [1000, 1001, 1002, 1003], "各座位数据未被覆盖")
    for i in range(4):
        got = [fr["dahai_pred"][0][33] for fr in game["naga"]["rounds"][0]
               if fr.get("actor") == i and fr.get("msg") == "tsumo" and fr.get("dahai_pred")]
        check(got and all(v == i + 1 for v in got), "第 %d 家摸牌帧的预测保留在同一模型槽" % i)


def test_base_model_order():
    print("=== 2c. base 的模型 index 顺序与 union 槽不同 ===")
    out = fresh("mix_model_order")
    base = mortal.game_from_file(SRC1)
    paths = []
    for i in range(2):
        game = copy.deepcopy(base)
        game.pop("path", None)
        naga = game["naga"]
        # 源文件里模型列表顺序故意与 index 相反：列表第 0 项是 index=1。
        naga["models"] = [
            {"index": 1, "raw": "B", "name": "合成模型-B", "series": "Mortal"},
            {"index": 0, "raw": "A", "name": "合成模型-A", "series": "Mortal"},
        ]
        naga["types"] = {"1": "B", "0": "A"}
        naga["model_index"] = 1
        naga["report_id"] = "order%d" % i
        naga["kind"] = "mortal"
        for rnd in naga["rounds"]:
            for fr in rnd:
                old = fr.get("dahai_pred")
                if isinstance(old, list) and old:
                    val = old[0]
                    fr["dahai_pred"] = [None, val]
                else:
                    fr["dahai_pred"] = None
                for field in ("pred_dahai", "reach", "kan", "dahai_split",
                              "kyushu", "ankan_pai", "kakan_pai"):
                    fr[field] = None
                fr["huro"] = {}
                fr["hora"] = {}
        path = os.path.join(out, "order%d.mortal-b" % i)
        write_mix(path, game)
        paths.append(path)
    res = mix.merge_paths(paths, delete=True)
    check(res.get("merged"), "模型顺序错位的两份容器合并")
    game = mix.game_from_file(res["path"])
    eq([m["name"] for m in game["naga"]["models"]], ["合成模型-B", "合成模型-A"], "union 保持 base 列表顺序")
    frame = game["naga"]["rounds"][0][1]
    arr = frame.get("dahai_pred") or []
    eq(len(arr), 2, "首帧两个槽")
    check(bool(arr[0]), "base 的 index=1 数据落到 union 槽 0")
    check(arr[1] is None, "旧槽位没有留下重复数据")


def test_no_overwrite():
    print("=== 2d. 默认 mix 目标已存在时拒绝覆盖 ===")
    out = fresh("mix_no_overwrite")
    p1 = os.path.join(out, os.path.basename(SRC1))
    p2 = os.path.join(out, os.path.basename(SRC2))
    shutil.copy2(SRC1, p1)
    shutil.copy2(SRC2, p2)
    target = os.path.join(out, "[mix]718521d3073f9ee3.mortal-b")
    write_mix(target, {"meta": {}, "rounds": []})
    before = io.open(target, "rb").read()
    try:
        mix.merge_paths([p1, p2], delete=True)
    except mix.MixError:
        pass
    else:
        check(False, "已存在的目标文件应拒绝覆盖")
        return
    check(os.path.isfile(p1) and os.path.isfile(p2), "拒绝覆盖时源文件保留")
    check(io.open(target, "rb").read() == before, "已存在的目标文件内容未变")


def test_mix_dedupe():
    print("=== 2e. 下载判重能识别 mix 里的来源 ===")
    out = fresh("mix_dedupe")
    p1 = os.path.join(out, os.path.basename(SRC1))
    p2 = os.path.join(out, os.path.basename(SRC2))
    shutil.copy2(SRC1, p1)
    shutil.copy2(SRC2, p2)
    res = mix.scan_and_merge(p2, root=out)
    mix_path = res["path"]
    check(mix_path in download.find_mortal_files(out, "718521d3073f9ee3"), "Mortal 来源 1 命中 mix")
    check(mix_path in download.find_mortal_files(out, "bbffcce78e5db531"), "Mortal 来源 2 命中 mix")
    # 天凤来源：mix sources 里只有文件名 / log_id，没有 report_id 的独立字段时也要能命中。
    log_id = "2026082919gm-00a9-0000-4e40cd3e"
    game = mortal.game_from_file(SRC1)
    game.pop("path", None)
    tp = os.path.join(out, "[mix]%s.tenhou" % log_id)
    write_mix(tp, game, sources=[{"name": log_id + ".tenhou", "kind": "tenhou",
                                  "report_id": log_id, "fingerprint": "x"}])
    check(tp in download._mix_source_files(out, log_id, kind="tenhou"), "天凤 log_id 命中 mix")
    # NAGA 来源：report_id 含 v2_2 这类格式后缀，也要按完整 report_id 命中。
    naga_id = "a" * 64 + "v2_2"
    np = os.path.join(out, "[mix]%s.naga" % naga_id)
    write_mix(np, game, sources=[{"name": naga_id + ".naga", "kind": "naga",
                                  "report_id": naga_id, "fingerprint": "x"}])
    check(np in download.find_naga_files(out, naga_id), "NAGA report_id 命中 mix")


def test_run_download_auto_mix():
    print("=== 5b. run_download 全流程：下载两份同局 Mortal 后自动合并 ===")
    out = fresh("mix_run_download")
    raw1 = io.open(SRC1, "rb").read()
    raw2 = io.open(SRC2, "rb").read()
    original = download.fetch_mortal_report

    def fake_fetch(target, timeout=30.0, retries=3):
        rid = (target or {}).get("report_id")
        data = raw1 if rid == "718521d3073f9ee3" else raw2
        return data, download.mortal_model_info(data)

    download.fetch_mortal_report = fake_fetch
    try:
        res = download.run_download([
            "https://mjai.ekyu.moe/report/718521d3073f9ee3.json",
            "https://mjai.ekyu.moe/report/bbffcce78e5db531.json",
        ], out)
    finally:
        download.fetch_mortal_report = original
    eq(res.get("saved"), 2, "两份都真正落盘")
    eq(res.get("duplicate"), 0, "来源 report_id 不同，不按来源判重")
    eq(sorted(os.listdir(out)), ["[mix]718521d3073f9ee3.mortal-b"], "run_download 后只留 mix")
    eq([os.path.basename((r or {}).get("path") or "") for r in res.get("results") or []],
       ["[mix]718521d3073f9ee3.mortal-b"] * 2, "results 两条 path 都回填 mix")
    eq((res.get("results") or [{}])[1].get("mixed"), True, "第二条标记 mixed")
    # 再下载同一对来源：应命中 mix 里的 sources，直接拒绝/跳过，不再发请求。
    def fail_fetch(*_a, **_k):
        raise AssertionError("mix 已包含该 report_id，不应重新下载")
    download.fetch_mortal_report = fail_fetch
    try:
        res2 = download.run_download([
            "https://mjai.ekyu.moe/report/718521d3073f9ee3.json",
            "https://mjai.ekyu.moe/report/bbffcce78e5db531.json",
        ], out)
    finally:
        download.fetch_mortal_report = original
    eq(res2.get("saved"), 0, "再次下载不落盘")
    eq(res2.get("duplicate"), 2, "两条都按 mix sources 判重")
    eq([os.path.basename((r or {}).get("path") or "") for r in res2.get("results") or []],
       ["[mix]718521d3073f9ee3.mortal-b"] * 2, "重复项路径也指向 mix")


def test_canon():
    print("=== 3. 跨来源规范化口径 ===")
    init = {"round": 0, "combo": 0, "kyotaku": 0, "dora": 0,
            "scores": [25000, 25000, 25000, 25000], "oya": 0,
            "hands": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                      [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25],
                      [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38],
                      [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51]]}

    def make(events):
        return {"names": ["甲", "乙", "丙", "丁"], "dices": [1, 2],
                "rounds": [{"init": dict(init), "events": events}]}

    # 天凤：kakan 4 张、reach step1、和牌手牌/待牌/里宝/役/点数与 NAGA 不同
    g1 = make([
        {"type": "call", "player": 0, "callee": 1, "callType": "kakan",
         "tiles": [128, 129, 130, 131], "m": 123, "rel": 3},
        {"type": "reach", "player": 1, "step": 1},
        {"type": "agari", "winner": 0, "fromWho": 1, "hand": list(range(14)),
         "machi": [1, 2], "dora": [3], "ura": [4], "yaku": ["立直"], "ten": [20, 8000, 1],
         "ba": 0, "gain": [8000, -8000, 0, 0]},
    ])
    # NAGA/Mortal：kakan 1 张、reach step2、和牌手牌/待牌/里宝/役/点数不同、骰子为 0
    g2 = make([
        {"type": "call", "player": 0, "callee": None, "callType": "kakan",
         "tiles": [128], "m": None},
        {"type": "reach", "player": 1, "step": 2},
        {"type": "agari", "winner": 0, "fromWho": 1, "hand": [5, 6, 7],
         "machi": [9], "dora": [8], "ura": [], "yaku": ["平和"], "ten": [30, 3900],
         "ba": 1, "gain": [3900, -3900, 0, 0]},
    ])
    g2["dices"] = [0, 0]
    g2["names"] = ["A", "B", "C", "D"]
    eq(mix.fingerprint(g1), mix.fingerprint(g2), "kakan / reach / 和牌细节 / 骰子差异不影响 hash")
    g3 = make([
        {"type": "call", "player": 0, "callee": None, "callType": "kakan",
         "tiles": [132], "m": None},
        {"type": "reach", "player": 1, "step": 2},
        {"type": "agari", "winner": 0, "fromWho": 1},
    ])
    check(mix.fingerprint(g1) != mix.fingerprint(g3), "不同加杠牌 -> hash 不同")
    g4 = make([
        {"type": "call", "player": 0, "callee": None, "callType": "kakan", "tiles": [128]},
        {"type": "reach", "player": 1, "step": 2},
        {"type": "agari", "winner": 0, "fromWho": 2},
    ])
    check(mix.fingerprint(g1) != mix.fingerprint(g4), "不同放铳者 -> hash 不同")
    eq(mix._tile(16), "0m", "红 5 牌 id -> 0m")
    eq(mix._tile("5sr"), "0s", "红 5 牌名 -> 0s")
    # 用户提醒：对局者 ID / 名字 / 复盘视角不是判重依据；分析软件可能隐去 ID。
    g5 = copy.deepcopy(g1)
    g5["meta"] = {"viewer_seat": 3, "names": ["匿名A", "匿名B", "匿名C", "匿名D"]}
    g5["naga"] = {"player_id": 2, "viewer_seat": 2, "report_id": "different-report"}
    eq(mix.fingerprint(g1), mix.fingerprint(g5), "对局者 ID / 名字 / 视角 / 报告号不影响 hash")
    eq(mix.mix_name_for("x.tenhou"), "[mix]x.tenhou", "mix 命名加前缀")
    eq(mix.mix_name_for("[mix]x.tenhou"), "[mix]x.tenhou", "已有前缀不重复加")


def test_reject_other_game():
    print("=== 4. 非同一局拒绝合并 ===")
    out = fresh("mix_reject")
    tenhou = glob.glob(os.path.join(ROOT, "data", "paipu", "tenhou", "*.tenhou"))
    check(bool(tenhou), "有天凤样例")
    if not tenhou:
        return
    p1 = os.path.join(out, os.path.basename(SRC1))
    p2 = os.path.join(out, os.path.basename(tenhou[0]))
    shutil.copy2(SRC1, p1)
    shutil.copy2(tenhou[0], p2)
    try:
        mix.merge_paths([p1, p2], delete=False)
    except mix.MixError as exc:
        check("不是同一场对局" in str(exc), "不同牌局 -> MixError")
    else:
        check(False, "不同牌局应当拒绝合并")


def test_download_hook():
    print("=== 5. 下载落盘后的自动合并 ===")
    out = fresh("mix_download")
    p1 = os.path.join(out, os.path.basename(SRC1))
    p2 = os.path.join(out, os.path.basename(SRC2))
    shutil.copy2(SRC1, p1)
    shutil.copy2(SRC2, p2)
    entry = {"path": p2, "written": True}
    seen = {"bbffcce78e5db531": p2, "718521d3073f9ee3": p1}
    results = [{"path": p1}, {"path": p2}]
    download._auto_mix(entry, seen, results)
    check(entry.get("mixed"), "entry.mixed = True")
    mix_path = entry.get("path")
    eq(os.path.basename(mix_path or ""), "[mix]718521d3073f9ee3.mortal-b", "entry.path 改为 mix")
    eq(seen.get("bbffcce78e5db531"), mix_path, "seen 回填 mix 路径")
    eq(seen.get("718521d3073f9ee3"), mix_path, "seen 旧路径回填 mix")
    eq([r.get("path") for r in results], [mix_path, mix_path], "results 旧路径回填 mix")
    eq(os.listdir(out), ["[mix]718521d3073f9ee3.mortal-b"], "源文件已删除")


def main():
    if not os.path.isfile(SRC1) or not os.path.isfile(SRC2):
        print("缺少真实重复对样例，跳过：%s / %s" % (SRC1, SRC2))
        return 1
    test_real_pair()
    test_model_union()
    test_sequential_merge()
    test_same_model_seats()
    test_base_model_order()
    test_no_overwrite()
    test_mix_dedupe()
    test_canon()
    test_reject_other_game()
    test_download_hook()
    test_run_download_auto_mix()
    print("\n结果：%d OK / %d FAIL" % (OK[0], BAD[0]))
    return 0 if BAD[0] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
