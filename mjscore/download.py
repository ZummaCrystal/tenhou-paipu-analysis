# -*- coding: utf-8 -*-
"""牌谱下载（第 21 轮）：核心逻辑从tools/download_tenhou.py 搬进包内，
「界面 → POST /api/download」与tools/download_tenhou.py 共用同一实现。

口径（用户 m02959）：
  * 存储位置：<项目根>/data/paipu/<子目录名>。「data/paipu」这段固定，
    子目录名由用户指定，默认是带时间戳的目录名（如 20260920-153012）。
  * 同名文件直接覆盖。
  * 下载结束给出「待下载 / 下载成功 / 下载失败」数量。

对外接口：
  extract_log_id(text) / build_download_url(log_id) / fetch_log(log_id, ...)
  looks_like_mjlog(data) / save_log(log_id, data, out_dir, overwrite=True)
  paipu_root() / default_subdir() / resolve_out_dir(sub=None)
  read_url_lines(text) / collect_urls(items)
  run_download(urls, out_dir, overwrite=True, on_item=None, progress=None)
  start_download(urls, out_dir, overwrite=True) / download_snapshot()
"""

import gzip
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tenhou 的原始 mjlog 走明文 HTTP：本机 python 没有可用的 CA 包，https 会失败。
DOWNLOAD_ENDPOINT = "http://tenhou.net/0/log/?{log_id}"
USER_AGENT = "Mozilla/5.0 (compatible; tenhou-paipu-analysis/0.1)"

LOG_ID_RE = re.compile(r"^\d{10}gm-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8}$")
LOG_ID_ANY_RE = re.compile(r"\d{10}gm-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8}")

PAIPU_SUB = os.path.join("data", "paipu")


class DownloadError(RuntimeError):
    """牌谱下载失败 / 内容不像 mjlog 时抛出。"""


# ---------------------------------------------------------------------------
# url / 特征码
# ---------------------------------------------------------------------------
def extract_log_id(text):
    """从一段文本里取出天凤牌谱特征码。"""
    text = str(text or "").strip()
    if not text:
        raise ValueError("输入为空")
    if LOG_ID_RE.match(text):
        return text
    parsed = urllib.parse.urlparse(text)
    query = urllib.parse.parse_qs(parsed.query)
    if "log" in query and query["log"]:
        candidate = query["log"][0].strip()
        if LOG_ID_RE.match(candidate):
            return candidate
    if "/log/" in text:
        tail = text.split("/log/", 1)[1].lstrip("?").strip()
        candidate = tail.split("&", 1)[0]
        if LOG_ID_RE.match(candidate):
            return candidate
    match = LOG_ID_ANY_RE.search(text)
    if match:
        return match.group(0)
    raise ValueError("无法从「%s」里解析出牌谱特征码" % text[:120])


def build_download_url(log_id):
    return DOWNLOAD_ENDPOINT.format(log_id=log_id)


def fetch_log(log_id, timeout=30.0, retries=3):
    url = build_download_url(log_id)
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.URLError, TimeoutError, OSError, gzip.BadGzipFile) as exc:
            last_error = exc
            sys.stderr.write("  ! 第 %d/%d 次尝试失败：%s\n" % (attempt, retries, exc))
    raise DownloadError("下载 %s 失败：%s" % (log_id, last_error))


def looks_like_mjlog(data):
    head = data[:512].lstrip()
    return b"<mjloggm" in head or head.startswith(b"<?xml")


def save_log(log_id, data, output_dir, overwrite=True):
    """写 <output_dir>/<log_id>.xml。返回 (path, written)。"""
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "%s.xml" % log_id)
    if os.path.exists(path) and not overwrite:
        return path, False
    with open(path, "wb") as fh:
        fh.write(data)
    return path, True


# ---------------------------------------------------------------------------
# 存储位置
# ---------------------------------------------------------------------------
def paipu_root():
    """固定的存储根 <项目根>/data/paipu。"""
    return os.path.join(ROOT, PAIPU_SUB)


def default_subdir(now=None):
    """默认子目录名 = 带时间戳（如 20260920-153012）。"""
    t = now or time.localtime()
    return time.strftime("%Y%m%d-%H%M%S", t)


def resolve_out_dir(sub=None):
    """子目录名 -> 绝对路径（强制落在 data/paipu 下）。"""
    name = str(sub or "").strip().strip('"').strip("'")
    for prefix in ("data/paipu/", "data\\paipu\\", "data/paipu", "data\\paipu", "paipu/"):
        if name.lower().startswith(prefix.lower()):
            name = name[len(prefix):]
            break
    name = name.strip().strip("/").strip("\\")
    if not name:
        name = default_subdir()
    if os.path.isabs(name) or ".." in name or "/" in name or "\\" in name:
        raise ValueError("存储地址只能是 data/paipu 下的子目录名（不含路径分隔符或 ..），收到「%s」" % name)
    return os.path.join(paipu_root(), name)


# ---------------------------------------------------------------------------
# 输入整理
# ---------------------------------------------------------------------------
def read_url_lines(text):
    """文本 -> url/特征码列表（跳过空行与 # 注释行）。"""
    out = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def read_url_file(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return read_url_lines(fh.read())


def collect_urls(items):
    """去重（保序）。"""
    seen = set()
    out = []
    for item in items or ():
        item = str(item or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------
def run_download(urls, out_dir, overwrite=True, on_item=None, progress=None):
    """同步下载。返回 {dir,total,saved,failed,skipped,results}。

    on_item(entry) 每下载完一个就回调一次（顺序输出用）；
    progress(**kw) 给界面进度用，kw = done/total/current/saved/failed。
    """
    urls = list(urls or [])
    out = os.path.abspath(out_dir)
    if not os.path.isdir(out):
        os.makedirs(out, exist_ok=True)
    results = []
    saved = failed = skipped = 0
    total = len(urls)
    for i, item in enumerate(urls):
        entry = {"input": item, "ok": False, "log_id": None, "path": None, "bytes": 0,
                 "written": False, "error": None}
        log_id = None
        try:
            log_id = extract_log_id(item)
            entry["log_id"] = log_id
            data = fetch_log(log_id)
            if not looks_like_mjlog(data):
                raise DownloadError("下载内容不像 mjlog 牌谱（%d 字节）" % len(data))
            path, written = save_log(log_id, data, out, overwrite=overwrite)
            entry.update({"ok": True, "path": path, "bytes": len(data), "written": written})
            if written:
                saved += 1
            else:
                skipped += 1
        except Exception as exc:
            entry.update({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
            failed += 1
        results.append(entry)
        if on_item is not None:
            on_item(entry)
        if progress is not None:
            progress(done=i + 1, total=total, current=(log_id or item), saved=saved,
                     failed=failed, skipped=skipped)
    return {"dir": out, "total": total, "saved": saved, "failed": failed,
            "skipped": skipped, "results": results}


# 后台下载进度（服务端 GET /api/download-progress 用；与 cli.PROGRESS 同构）
DOWNLOAD = {}
DOWNLOAD_LOCK = threading.Lock()


def download_reset(**kw):
    with DOWNLOAD_LOCK:
        DOWNLOAD.clear()
        now = time.time()
        DOWNLOAD.update({"running": False, "done": False, "total": 0, "done_n": 0,
                         "current": "", "saved": 0, "failed": 0, "skipped": 0,
                         "dir": "", "error": None, "started_at": now, "updated_at": now,
                         "elapsed_ms": 0})
        coerce = {"done_n": int, "total": int, "saved": int, "failed": int, "skipped": int}
        for k, v in kw.items():
            if k in coerce and v is not None:
                v = coerce[k](v)
            DOWNLOAD[k] = v
        DOWNLOAD["updated_at"] = time.time()


def download_update(**kw):
    with DOWNLOAD_LOCK:
        if kw.get("started_at") is None and not DOWNLOAD.get("started_at"):
            DOWNLOAD["started_at"] = time.time()
        coerce = {"done_n": int, "total": int, "saved": int, "failed": int, "skipped": int}
        for k, v in kw.items():
            if k in coerce and v is not None:
                v = coerce[k](v)
            DOWNLOAD[k] = v
        DOWNLOAD["updated_at"] = time.time()


def download_snapshot():
    with DOWNLOAD_LOCK:
        snap = dict(DOWNLOAD)
    started = snap.get("started_at") or 0
    snap["elapsed_ms"] = int(max(0.0, time.time() - started) * 1000) if started else 0
    snap.pop("updated_at", None)
    return snap


def start_download(urls, out_dir, overwrite=True):
    """后台线程下载；立刻返回 {ok,started,dir,total}，进度看 download_snapshot()。"""
    urls = list(urls or [])
    out = os.path.abspath(out_dir)
    download_reset(running=True, done=False, total=len(urls), done_n=0, current="",
                   saved=0, failed=0, skipped=0, dir=out, error=None, started_at=time.time())

    def _progress(**kw):
        download_update(done_n=kw.get("done"), total=kw.get("total"),
                        current=kw.get("current"), saved=kw.get("saved"),
                        failed=kw.get("failed"), skipped=kw.get("skipped"))

    def _worker():
        try:
            res = run_download(urls, out, overwrite=overwrite, progress=_progress)
            download_update(running=False, done=True, total=res["total"], done_n=res["total"],
                            current="", saved=res["saved"], failed=res["failed"],
                            skipped=res["skipped"], dir=res["dir"])
        except Exception as exc:
            download_update(running=False, done=True, error="%s: %s" % (type(exc).__name__, exc))

    thread = threading.Thread(target=_worker, name="paipu-download", daemon=True)
    thread.start()
    return {"ok": True, "started": True, "dir": out, "total": len(urls)}