# -*- coding: utf-8 -*-
"""牌谱分析命令行入口（tools/analyze.py / server.py / 测试都走这里）。"""

import argparse
import datetime
import json
import os
import re
import sqlite3
import sys
import threading
import time

from . import feats, mjlog, nodeharness, store
from . import APP_NAME, __version__ as APP_VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(ROOT, "data", "db")
DEFAULT_DB_NAME = "paipu"


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ 进度
# 前端在「牌谱分析」时轮询 /api/analyze-progress 拿这里的快照（analyze 本身是阻塞的）。
PROGRESS = {
    "running": False, "done": False, "ok": None, "error": "", "stage": "",
    "tool": "", "db": "", "files_total": 0, "files_done": 0, "current": "",
    "rounds_done": 0, "rounds_total": 0, "records": 0, "events_done": 0,
    "events_total": 0, "elapsed_ms": 0, "started_at": 0.0, "updated_at": 0.0,
    "skipped": 0, "extend": False,
}
PROGRESS_LOCK = threading.Lock()


def progress_reset(**kw):
    """开始一次分析：清掉上一轮的计数（running/done/ok/error 等状态位除外，由 kw 决定）。"""
    with PROGRESS_LOCK:
        for k, v in list(PROGRESS.items()):
            if k in ("running", "done", "ok", "error", "elapsed_ms", "started_at", "updated_at"):
                continue
            PROGRESS[k] = 0 if isinstance(v, int) else ""
        PROGRESS["done"] = False
        PROGRESS["ok"] = None
        PROGRESS["error"] = ""
        PROGRESS["elapsed_ms"] = 0
        PROGRESS["updated_at"] = time.time()
        PROGRESS.update(kw)
        if not PROGRESS.get("started_at"):
            PROGRESS["started_at"] = time.time()


def progress_update(**kw):
    with PROGRESS_LOCK:
        PROGRESS.update(kw)
        if PROGRESS.get("started_at"):
            PROGRESS["elapsed_ms"] = int((time.time() - PROGRESS["started_at"]) * 1000)
        PROGRESS["updated_at"] = time.time()


def progress_snapshot():
    with PROGRESS_LOCK:
        snap = dict(PROGRESS)
    if snap.get("started_at"):
        snap["elapsed_ms"] = int((time.time() - snap["started_at"]) * 1000)
    snap.pop("updated_at", None)
    return snap


def db_path_of(db=None, db_name=None):
    """数据库文件路径：db 优先（绝对化），否则 data/db/<名字>.sqlite。

    名字末尾已经带 .sqlite 时不再重复追加 —— 前端「扩充现有数据库」下拉的
    value 就是 data/db 下的文件名（带扩展名，见 web/js/app.js fillExtendSelect），
    以前这里无条件 + ".sqlite" 会得到 xxx.sqlite.sqlite（bug m04115①）。
    """
    if db:
        return os.path.abspath(db)
    name = db_name or DEFAULT_DB_NAME
    if not name.lower().endswith(".sqlite"):
        name += ".sqlite"
    return os.path.join(DB_DIR, name)


def resolve_inputs(paths):
    """把「牌谱文件或目录」展开成排好序的 .xml 绝对路径（目录递归、去重）。"""
    files, seen = [], set()
    for p in paths:
        ap = os.path.abspath(p)
        if os.path.isdir(ap):
            for dirpath, _dirs, names in os.walk(ap):
                for fn in sorted(names):
                    if fn.lower().endswith(".xml"):
                        fp = os.path.join(dirpath, fn)
                        if fp not in seen:
                            seen.add(fp); files.append(fp)
        elif os.path.isfile(ap):
            if ap not in seen:
                seen.add(ap); files.append(ap)
        else:
            raise FileNotFoundError("找不到牌谱文件或目录：%s" % ap)
    if not files:
        raise FileNotFoundError("没有找到任何 .xml 牌谱文件")
    return sorted(files)


# ------------------------------------------------------------------ 打点
def python_records(games, on_progress=None, progress=None):
    """Python 一侧的打点（mjscore/mjlog.py + replay.py + feats.py）；逐局上报进度。"""
    recs = []
    for i, game in enumerate(games):
        lid = game["log_id"]
        rounds = game.get("rounds") or []
        if progress:
            progress(stage="打点", files_done=i, current=lid, rounds_done=0, rounds_total=len(rounds))
        n = 0
        for ri in range(len(rounds)):
            rs = feats.records_for_round(game, ri)
            for r in rs:
                r["path"] = game["path"]; r["tool"] = "python"
            recs.extend(rs)
            n += len(rs)
            if progress:
                progress(rounds_done=ri + 1, records=len(recs))
        if on_progress:
            on_progress(i + 1, len(games), lid, n)
        if progress:
            progress(files_done=i + 1, records=len(recs))
    return recs


def second_class_pass(games, on_progress=None, progress=None):
    """逐帧算第二类 17 项（只取 feats 里 s_* 那部分）。

    js 侧没有实现第二类特征 ⇒ --tool node 时用它补列。返回
    {(log_id, round_index, ev_index, seat): {key: value, ...}}。
    """
    out = {}
    for i, game in enumerate(games):
        lid = game["log_id"]
        rounds = game.get("rounds") or []
        if progress:
            progress(stage="打点（第二类特征）", files_done=i, current=lid,
                     rounds_done=0, rounds_total=len(rounds))
        n = 0
        for ri in range(len(rounds)):
            rs = feats.records_for_round(game, ri)
            for r in rs:
                out[(r["log_id"], r["round_index"], r["ev_index"], r["seat"])] = r["feats"]
            n += len(rs)
            if progress:
                progress(rounds_done=ri + 1, records=n)
        if on_progress:
            on_progress(i + 1, len(games), lid, n)
        if progress:
            progress(files_done=i + 1)
    return out


def merge_second_class(records, extra):
    """把 python 算的第二类特征合进 node 打点行（键 = 特征码 + 局 + 事件序号 + 座位）。"""
    missing = []
    for rec in records:
        k = (rec.get("log_id"), rec.get("round_index"), rec.get("ev_index"), rec.get("seat"))
        src = extra.get(k)
        if src is None:
            missing.append(k)
            continue
        vals = rec.setdefault("feats", {})
        for key in feats.SECOND_KEYS:
            vals[key] = src[key]
    if missing:
        raise ValueError("node 打点行里有 %d 行在 python 侧找不到对应帧（第二类特征补不上），例如 %s"
                         % (len(missing), missing[0]))
    return len(records)


def fill_second_class(records, games, warnings, on_progress=None, progress=None):
    """node 只打第一类 16 项特征，第二类 17 项由 python 逐帧补齐。"""
    warnings.append("--tool node：第一类特征来自 node，第二类 17 项由 python 补齐（js 侧没有实现）")
    extra = second_class_pass(games, on_progress=on_progress, progress=progress)
    merge_second_class(records, extra)
    return records


def build_records(files, games, tool="auto", node=None, warnings=None, on_progress=None, progress=None):
    """按 --tool 选择打点工具；auto = 有 node 用 node，node 失败则退回 python。

    node（web/js/mjsfeat.js）只实现第一类 16 项特征 ⇒ 之后由 python 补齐第二类 17 项。
    """
    warnings = warnings if warnings is not None else []
    if tool == "python":
        return "python", python_records(games, on_progress, progress=progress)
    if tool == "node":
        if not nodeharness.available():
            raise nodeharness.NodeMissing("--tool node 但找不到 node.exe")
        recs = nodeharness.node_records(files, node=node)
        return "node", fill_second_class(recs, games, warnings, on_progress, progress)
    if nodeharness.available():
        try:
            recs = nodeharness.node_records(files, node=node)
            return "node", fill_second_class(recs, games, warnings, on_progress, progress)
        except (nodeharness.NodeMissing, nodeharness.NodeFailed) as exc:
            warnings.append("node 打点不可用，自动退回 python：%s" % exc)
    else:
        warnings.append("未找到 node.exe，使用 python 打点")
    return "python", python_records(games, on_progress, progress=progress)


def analyze(inputs, db=None, db_name=None, tool="auto", full=False, node=None,
            on_progress=None, fixture=None, extend=False):
    """打点并写库；进度写进 cli.PROGRESS（前端轮询 /api/analyze-progress）。

    extend=True 时扩充已有数据库（库里已有的牌谱自动跳过），见 _analyze。
    返回结果摘要 dict（server.py 也调这个函数）。
    """
    progress_reset(running=True, stage="解析牌谱", tool=tool, db=db_path_of(db, db_name),
                   files_total=0, files_done=0, current="", rounds_done=0, rounds_total=0,
                   records=0, events_done=0, events_total=0, skipped=0, extend=bool(extend),
                   started_at=time.time())
    try:
        res = _analyze(inputs, db=db, db_name=db_name, tool=tool, full=full, node=node,
                       on_progress=on_progress, fixture=fixture, progress=progress_update,
                       extend=extend)
    except Exception as exc:
        progress_update(running=False, done=True, ok=False, stage="失败",
                        error="%s: %s" % (type(exc).__name__, exc))
        raise
    nf = len(res.get("files") or [])
    progress_update(running=False, done=True, ok=True, stage="完成", tool=res.get("tool", ""),
                    db=res.get("db", ""), files_total=nf, files_done=nf, current="",
                    records=res.get("annotations", 0), rounds_done=res.get("rounds", 0),
                    rounds_total=res.get("rounds", 0),
                    skipped=len(res.get("skipped") or []))
    return res


def _analyze(inputs, db=None, db_name=None, tool="auto", full=False, node=None,
             on_progress=None, fixture=None, progress=None, extend=False):
    """打点并写库的内部实现。返回结果摘要 dict（server.py 也调 analyze()）。

    extend=True（「扩充现有数据库」）：目标库必须已存在、结构版本与软件版本都匹配；
    库里 source 表已记录过的牌谱（特征码相同）直接跳过，只把新牌谱追加进去。
    """
    t0 = time.time()
    db_path = db_path_of(db, db_name)
    warnings = []
    skipped = []
    existing = set()
    prev_full = False
    if extend:
        if fixture:
            raise ValueError("fixture 入库不能与扩充模式同时使用")
        if not os.path.isfile(db_path):
            raise FileNotFoundError("要扩充的数据库不存在：%s（请先新建数据库）" % db_path)
        conn0 = store.connect(db_path, create=False)      # 同时校验结构版本 / 软件版本
        try:
            existing = store.source_ids(conn0)
            prev_full = str(store.get_meta(conn0).get("full") or "") == "1"
        finally:
            conn0.close()
        if not existing:
            warnings.append("要扩充的数据库还没有任何牌谱记录，本次按新建处理")
    if fixture:
        files = [os.path.abspath(fixture)]
        records = [dict(r) for r in nodeharness.parse_jsonl(
            open(files[0], "r", encoding="utf-8").read())]
        used_tool = "fixture"
        games = []
        by_id = {}
        for r in records:
            r.setdefault("tool", "fixture")
            r.setdefault("path", "")
            if r["log_id"] not in by_id:
                by_id[r["log_id"]] = r
        games = []
        for lid, r in by_id.items():
            games.append({"log_id": lid, "path": r.get("path", ""), "rounds": [], "meta": {"names": []}})
    else:
        files = resolve_inputs(inputs)
        if extend:
            keep = []
            for f in files:
                lid = mjlog.log_id_of(f)
                if lid in existing:
                    skipped.append(lid)
                else:
                    keep.append(f)
            files = keep
            if progress:
                progress(skipped=len(skipped))
            if not files:
                raise FileNotFoundError(
                    "这 %d 个牌谱都已经在数据库里了，没有需要扩充的新牌谱" % len(skipped))
        if progress:
            progress(stage="解析牌谱", files_total=len(files), current="")
        games = [mjlog.game_from_file(f) for f in files]
        if progress:
            progress(rounds_total=sum(len(g.get("rounds") or []) for g in games))
        used_tool, records = build_records(files, games, tool=tool, node=node,
                                          warnings=warnings, on_progress=on_progress,
                                          progress=progress)
        if progress:
            progress(stage="写库", files_done=len(files), current="", events_total=len(records))

    log_full = bool(full)
    if progress:
        progress(stage="写库")
    conn = store.open_db(db_path)
    try:
        store.write_feature_defs(conn)
        ts = now_str()
        # 局表 / 牌谱表
        rounds_by_log = {}
        for game in games:
            if not game.get("rounds"):
                continue
            store.insert_rounds(conn, game, used_tool)
            rounds_by_log[game["log_id"]] = len(game["rounds"])
        # 打点行
        counts = {}
        kind_counts = {}
        for rec in records:
            store.insert_records(conn, [rec], tool=used_tool, log_path=rec.get("path", ""),
                                 added_at=ts, full=log_full)
            counts[rec["log_id"]] = counts.get(rec["log_id"], 0) + 1
            k = rec.get("kind") or "draw"
            kind_counts[k] = kind_counts.get(k, 0) + 1
            done = sum(counts.values())
            if progress and len(records) >= 200 and done % 200 == 0:
                progress(events_done=done, records=done)
        # 重分析同一牌谱时 frame 行会换成新 idx ⇒ 清掉 frame_full 里取不到的旧原始数据
        store.prune_frame_full(conn)
        for game in games:
            lid = game["log_id"]
            if not game.get("rounds"):
                continue
            store.insert_source(conn, game, counts.get(lid, 0), used_tool, ts)
        for lid, n in counts.items():
            if not any(g["log_id"] == lid for g in games):
                continue
        conn.commit()
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) c FROM frame").fetchone()["c"]
        src_count = cur.execute("SELECT COUNT(*) c FROM source").fetchone()["c"]
        round_count = cur.execute("SELECT COUNT(*) c FROM round").fetchone()["c"]
        files_json = json.dumps([{"log_id": g["log_id"], "path": g["path"],
                                  "rounds": len(g.get("rounds") or []), "annotations": counts.get(g["log_id"], 0)}
                                 for g in games], ensure_ascii=False)
        create = store.get_meta(conn).get("created_at") or ts
        store.set_meta(conn, "schema_version", store.SCHEMA_VERSION)
        store.set_meta(conn, "app_version", store.APP_VERSION)
        store.set_meta(conn, "created_at", create)
        store.set_meta(conn, "updated_at", ts)
        store.set_meta(conn, "tool", used_tool)
        store.set_meta(conn, "record_count", total)
        store.set_meta(conn, "source_count", src_count)
        store.set_meta(conn, "round_count", round_count)
        store.set_meta(conn, "full", "1" if (log_full or prev_full) else "0")
        store.set_meta(conn, "doukou", store.DOUKOU)
        store.set_meta(conn, "full_note", store.FULL_NOTE if log_full else "")
        store.set_meta(conn, "sources_json", files_json)
        store.set_meta(conn, "last_batch", json.dumps(
            {"tool": used_tool, "files": files, "annotations": sum(counts.values()),
             "extend": bool(extend), "skipped": skipped, "full": log_full,
             "at": ts}, ensure_ascii=False))
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True, "db": db_path, "tool": used_tool, "full": log_full,
        "extend": bool(extend), "skipped": skipped,
        "files": files, "logs": len(games), "annotations": sum(counts.values()),
        "rows_draw": kind_counts.get("draw", 0),
        "rows_call": kind_counts.get("chi", 0) + kind_counts.get("pon", 0),
        "db_total": total, "sources": src_count, "rounds": round_count,
        "elapsed_ms": int((time.time() - t0) * 1000), "warnings": warnings,
        "detail": [{"log_id": g["log_id"], "path": g["path"],
                    "rounds": len(g.get("rounds") or []), "annotations": counts.get(g["log_id"], 0)}
                   for g in games],
    }


# ------------------------------------------------------------------ 检索
def resolve_feature(token):
    t = (token or "").strip().lstrip("﻿")
    if t in feats.BY_KEY:
        return feats.BY_KEY[t]
    for f in feats.FEATURES:
        if f["name"] == t:
            return f
    raise ValueError("未知的牌谱特征：%s" % t)


def feat_value_text(key, value):
    """特征值对外的显示文本。

    向听数内部取值为 3 表示「>=3 向听」，对外一律显示成 >=3（用户 m04115②）；
    其余特征直接 str。
    """
    if key in feats.SHANTEN_KEYS and value == 3:
        return ">=3"
    return str(value)


def parse_condition_lines(text):
    """把「特征名=条件」逐行解析成 conds。

    特征名可以是中文名（如「巡目」）或 key（如 junme）；条件可用
    = / == / : / != / > / >= / < / <= 与逗号列表（如 `>=2,<=4`）。
    """
    conds = []
    for line in text.splitlines():
        s = line.strip().lstrip('\ufeff')
        if not s or s.startswith('#'):
            continue
        m = re.match(r'^(.+?)\s*(>=|<=|!=|==|>|<|=|:)\s*(.*)$', s)
        if not m:
            raise ValueError('条件行格式应为「特征名=条件」：%s' % s)
        name, op, val = m.group(1), m.group(2), m.group(3).strip()
        if op in (':', '=='):
            op = '='
        f = resolve_feature(name)
        conds.append({'key': f['key'], 'expr': val if op == '=' else (op + val)})
    return conds


def run_query(db_path, conds, limit=200, offset=0):
    conn = store.connect(db_path, create=False)
    try:
        return store.query(conn, conds, limit=limit, offset=offset)
    finally:
        conn.close()


def list_dbs():
    out = []
    if not os.path.isdir(DB_DIR):
        return out
    for fn in sorted(os.listdir(DB_DIR)):
        if not fn.lower().endswith(".sqlite"):
            continue
        p = os.path.join(DB_DIR, fn)
        try:
            conn = store.connect(p, create=False)
            meta = store.get_meta(conn)
            conn.close()
        except Exception as exc:
            meta = {"error": str(exc)}
            # 版本不匹配时 store.connect 会直接抛错，但库文件本身是好的：
            # 用 raw sqlite3 读 meta 表拿到 app_version，界面才能显示「版本不匹配」
            # 而不是把库当成来源不明的旧文件。
            try:
                _raw = sqlite3.connect(p)
                try:
                    meta.update(dict(_raw.execute("SELECT k, v FROM meta").fetchall()))
                finally:
                    _raw.close()
            except Exception:
                pass
        ver = meta.get("app_version") or ""
        out.append({"name": fn, "path": p, "size": os.path.getsize(p), "meta": meta,
                    "app_version": ver,
                    "compatible": (not ver) or ver == store.APP_VERSION})
    return out


# ------------------------------------------------------------------ capture
def capture(files, out_dir, node=None):
    """用 Node 生成 JSONL fixture（打点行 / 帧快照 / 不变量校验）。"""
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for f in files:
        lid = os.path.splitext(os.path.basename(f))[0]
        rp = os.path.join(out_dir, lid + ".records.jsonl")
        nodeharness.node_records([f], node=node, out_path=rp)
        made.append(rp)
        fp = os.path.join(out_dir, lid + ".frames.jsonl")
        nodeharness.node_frames([f], node=node, out_path=fp)
        made.append(fp)
    ip = os.path.join(out_dir, "_invariants.jsonl")
    nodeharness.run("invariants", files, node=node, out_path=ip)
    made.append(ip)
    return made


# ------------------------------------------------------------------ CLI
def _out(text):
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="tools/analyze.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="天凤牌谱分析：对给定本地牌谱（文件或目录）里的每一个「非自摸的摸牌帧」和「吃/碰后等待出牌的帧」打点，写入 SQLite 数据库，并支持按特征检索。",
        epilog="示例：\n"
               "  python tools/analyze.py data\\*.xml --db-name demo\n"
               "  python tools/analyze.py \"D:\\paipu\" --db-name demo --full --tool node\n"
               "  python tools/analyze.py --list-dbs\n"
               "  echo 巡目=3,供托>=1000 | python tools/analyze.py --query --db-name demo\n"
               "  python tools/analyze.py --serve\n")
    ap.add_argument("paths", nargs="*", help="牌谱 .xml 文件或包含牌谱的目录（绝对路径，可多个）")
    ap.add_argument("--db", help="数据库文件路径（默认 data/db/<name>.sqlite）")
    ap.add_argument("--db-name", help="数据库名（默认 paipu）")
    ap.add_argument("--tool", choices=("auto", "node", "python"), default="auto",
                    help="打点工具：auto=有 node 用 node，失败退回 python（默认）；node=Node 端 js 解析器；python=本包实现")
    ap.add_argument("--full", action="store_true", help="同时写入原始数据：把该帧的手牌/副露/宝牌/分数存进 frame_full（以后新增特征可重算）")
    ap.add_argument("--extend", action="store_true", help="扩充现有数据库：目标库必须已存在且版本匹配，库里已有的牌谱自动跳过")
    ap.add_argument("--version", action="version", version="%s v%s" % (APP_NAME, APP_VERSION))
    ap.add_argument("--fixture", help="用已有的 JSONL 打点 fixture 入库（不解析 XML，测试用）")
    ap.add_argument("--capture", help="用 Node 生成 JSONL fixture 到指定目录（测试用）")
    ap.add_argument("--list-dbs", action="store_true", help="列出 data/db 下的数据库")
    ap.add_argument("--delete-db", help="删除指定数据库文件")
    ap.add_argument("--features", action="store_true", help="打印 33 个特征定义（16 个第一类 + 17 个第二类）")
    ap.add_argument("--values", help="打印某个特征在库里的取值分布（配合 --db/--db-name）")
    ap.add_argument("--query", action="store_true", help="从 stdin 读检索条件（每行「特征名=条件」），执行检索")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--export", help="导出数据库为 JSON 文件（- = 标准输出）")
    ap.add_argument("--json", dest="json_out", help="把结果 JSON 写到文件（- = 标准输出）")
    ap.add_argument("--serve", action="store_true", help="启动本地服务（前端 + /api）")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    def emit(obj, human=None):
        if not args.quiet and human:
            _out(human)
        if args.json_out:
            text = json.dumps(obj, ensure_ascii=False, indent=1)
            if args.json_out == "-":
                _out(text)
            else:
                with open(os.path.abspath(args.json_out), "w", encoding="utf-8") as fh:
                    fh.write(text)

    try:
        if args.features:
            emit({"features": feats.FEATURES, "doukou": store.DOUKOU},
                 "\n".join("%2d. %-18s [%s] %s" % (i + 1, f["name"], f["kind"],
                                                   " / ".join(map(str, f.get("values") or []))
                                                   or "%s..%s" % (f.get("min"), f.get("max")))
                           for i, f in enumerate(feats.FEATURES)))
            return 0
        if args.list_dbs:
            dbs = list_dbs()
            emit({"dbs": dbs}, "\n".join("%-28s %8d B  %s 打点 %s 行  版本 %s%s" % (
                d["name"], d["size"], d["meta"].get("tool", "-"), d["meta"].get("record_count", "-"),
                d.get("app_version") or "（未记录）",
                "" if d.get("compatible") else "  ⚠ 版本不匹配")
                for d in dbs) or "（data/db 下还没有数据库）")
            return 0
        if args.delete_db:
            p = os.path.abspath(args.delete_db)
            if os.path.isfile(p):
                os.remove(p)
                emit({"ok": True, "deleted": p}, "已删除 %s" % p)
                return 0
            emit({"ok": False, "error": "文件不存在"}, "文件不存在：%s" % p)
            return 1
        if args.capture:
            files = resolve_inputs(args.paths or [os.path.join(ROOT, "data")])
            made = capture(files, args.capture)
            emit({"ok": True, "files": made}, "已生成 %d 个 fixture 文件到 %s" % (len(made), os.path.abspath(args.capture)))
            return 0
        if args.serve:
            from . import server
            return server.serve(port=args.port)
        if args.values:
            f = resolve_feature(args.values)
            conn = store.open_db(db_path_of(args.db, args.db_name))
            try:
                vals = store.list_feature_values(conn, f["key"])
            finally:
                conn.close()
            human = "\n".join("%-8s %6d 帧" % (feat_value_text(f["key"], v["value"]), v["count"])
                               for v in vals)
            if f["key"] in feats.SHANTEN_KEYS:
                human += ("\n（向听数的内部取值 -1 / 0 / 1 / 2 / 3，3 表示 >=3；"
                          "检索条件仍按内部整数匹配：填 3、3-5、>=3 都会命中内部值 3）")
            emit({"feature": f["name"], "values": vals}, human)
            return 0
        if args.query:
            text = sys.stdin.read().lstrip("﻿")
            conds = parse_condition_lines(text)
            res = run_query(db_path_of(args.db, args.db_name), conds, limit=args.limit, offset=args.offset)
            emit(res, json.dumps(res, ensure_ascii=False, indent=1))
            return 0
        if args.export:
            conn = store.open_db(db_path_of(args.db, args.db_name))
            try:
                data = store.export_json(conn)
            finally:
                conn.close()
            if args.export == "-":
                _out(json.dumps(data, ensure_ascii=False))
            else:
                with open(os.path.abspath(args.export), "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=1)
            emit({"ok": True, "export": args.export, "frames": len(data["frames"])},
                 "已导出 %d 行到 %s" % (len(data["frames"]), args.export))
            return 0
        if args.fixture:
            res = analyze([args.fixture], db=args.db, db_name=args.db_name, fixture=args.fixture)
            res["tool"] = "fixture"
            emit(res, "已用 fixture 入库：%s（%d 行）" % (res["db"], res["db_total"]))
            return 0
        if not args.paths:
            ap.print_help()
            return 2
        res = analyze(args.paths, db=args.db, db_name=args.db_name, tool=args.tool,
                      full=args.full, extend=args.extend)
        human = ("已入库 %s\n  工具 %s ｜ 牌谱 %d 个 ｜ 局 %d ｜ 本次打点 %d 行"
                 "（摸牌帧 %d + 副露帧 %d）｜ 库内共 %d 行 ｜ %dms"
                 % (res["db"], res["tool"], res["logs"], res["rounds"], res["annotations"],
                    res.get("rows_draw", 0), res.get("rows_call", 0),
                    res["db_total"], res["elapsed_ms"]))
        if res.get("extend"):
            human += "\n  扩充模式：跳过已入库牌谱 %d 个" % len(res.get("skipped") or [])
        for w in res["warnings"]:
            human += "\n  [警告] " + w
        emit(res, human)
        return 0
    except Exception as exc:
        obj = {"ok": False, "error": str(exc), "type": type(exc).__name__}
        if args.json_out:
            emit(obj, None)
        else:
            emit(obj, None)
        sys.stderr.write("[错误] %s\n" % exc)
        return 1