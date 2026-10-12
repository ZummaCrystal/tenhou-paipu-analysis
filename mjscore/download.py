# -*- coding: utf-8 -*-
"""牌谱下载（第 21 轮）：核心逻辑从tools/download_tenhou.py 搬进包内，
「界面 → POST /api/download」与tools/download_tenhou.py 共用同一实现。

口径（用户 m02959 / m05545）：
  * 存储位置：<项目根>/data/paipu/<子目录名>。「data/paipu」这段固定，
    子目录名由用户指定，默认是带时间戳的目录名（如 20260920-153012）。
  * 文件名后缀按来源区分（用户 m05545 ②），内容仍是各来源的原格式：
      天凤 mjlog        -> <log_id>.tenhou     （XML 文本；旧后缀 .xml 仍认）
      NAGA / ricochet   -> <report_id>.naga    （原样 gzip 字节；旧后缀 .json.gz / .json 仍认）
      Mortal            -> <report_id>.mortal-a / -b / -c（mjai JSON 文本）
                           后缀按风格区分（4.1a 避四 / 4.1b 平衡 / 4.1c 争一，用户 m05806 ②）
  * 天凤牌谱：本地已有同名 <log_id>.tenhou（或旧的 .xml）就跳过、不重复下载
    （用户 m05480）。
  * 下载结束给出「待下载 / 下载成功 / 下载失败」数量。
  * naga / ricochet 两类 url（用户 m00268 / m00418）：按**完整的 report_id** 判重
    （url 里的 tw=0/1/2/3 是主视角、不参与判重；report_id 结尾的 v2_2 属于 id 本身）；
    与天凤特征码互不判重。
  * 两种来源撞到同一个 report_id 时（用户 m05392）：官方来源（naga.dmv.nico）发现本地已有
    同名文件就跳过、不重复下载；ricochet 来源（带 mtd，模型更全）在允许覆盖时**重新下载并覆盖**
    同名文件。同一次下载里同一来源的重复 url 仍按重复处理。
  * mortal 报告（用户 m05545 ①）：端点 = https://mjai.ekyu.moe/report/<report_id>.json（明文 JSON，
    不需 Referer / 特殊 UA；killerducky 的 ?data=/report/xxx.json 也能解析出同一个 report_id）。
     只有这一个来源，所以判重口径与天凤 / naga 官方一致：本地已有同名报告
     （.mortal-a / -b / -c 任意一种）就跳过、不重复下载。

对外接口：
  extract_log_id(text) / build_download_url(log_id) / fetch_log(log_id, ...)
  looks_like_mjlog(data) / save_log(log_id, data, out_dir, overwrite=True)
  paipu_root() / default_subdir() / resolve_out_dir(sub=None)
  read_url_lines(text) / collect_urls(items)
  run_download(urls, out_dir, overwrite=True, on_item=None, progress=None)
  start_download(urls, out_dir, overwrite=True) / download_snapshot()

naga / ricochet（用户 m00268）：
  looks_like_naga_url(text) / parse_naga_url(text) / naga_report_key(report_id)
  build_naga_url(form, report_id, mtd=None) / fetch_naga_report(target, ...)
  save_naga_report(report_id, data, out_dir, overwrite=True) / find_naga_files(out_dir, key)
  下载判重：天凤与 naga 官方来源都是「本地已有同名文件就跳过」
  （天凤：用户 m05480；naga 官方：用户 m05392），ricochet 来源则重新下载、覆盖同名文件

mortal（用户 m05545 ①）：
  looks_like_mortal_url(text) / parse_mortal_url(text) / mortal_report_key(report_id)
  build_mortal_url(report_id) / mortal_model_info(data) / fetch_mortal_report(target, ...)
  save_mortal_report(report_id, data, out_dir, overwrite=True) / find_mortal_files(out_dir, key)
"""

import gzip
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import paths

ROOT = paths.resource_root()

# Tenhou 的原始 mjlog 走明文 HTTP：本机 python 没有可用的 CA 包，https 会失败。
DOWNLOAD_ENDPOINT = "http://tenhou.net/0/log/?{log_id}"
USER_AGENT = "Mozilla/5.0 (compatible; tenhou-paipu-analysis/0.1)"

LOG_ID_RE = re.compile(r"^\d{10}gm-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8}$")
LOG_ID_ANY_RE = re.compile(r"\d{10}gm-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8}")

PAIPU_SUB = os.path.join("data", "paipu")

# 文件名后缀（用户 m05545 ②）：只改本地叫法，内容仍是各来源的原格式。
# 后缀表统一放在 mjscore/paths.py（server / cli / naga 共用一份），这里保留同名别名。
TENHOU_FILE_SUFFIX = paths.TENHOU_SUFFIX
TENHOU_LEGACY_SUFFIXES = paths.TENHOU_LEGACY_SUFFIXES
TENHOU_FILE_SUFFIXES = paths.TENHOU_SUFFIXES


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
    """写 <output_dir>/<log_id>.tenhou（内容仍是 mjlog XML，用户 m05545 ②）。返回 (path, written)。"""
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "%s%s" % (log_id, TENHOU_FILE_SUFFIX))
    if os.path.exists(path) and not overwrite:
        return path, False
    with open(path, "wb") as fh:
        fh.write(data)
    return path, True


# ---------------------------------------------------------------------------
# 存储位置
# ---------------------------------------------------------------------------
def paipu_root():
    """固定的存储根：源码运行 = <项目根>/data/paipu；打包后 = %LOCALAPPDATA%\\<AppName>\\data\\paipu。"""
    return paths.paipu_root()


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
# naga / ricochet 牌谱（用户 m00268）
#   * 下载端点：官方 https://naga.dmv.nico/reports/<report_id>.json.gz
#              代理 https://ricochet.cn/api/naga/proxy/reports/<report_id>.json.gz
#   * 两种形式各按原样重建 url：代理的 mtd 参数只在 ricochet 侧生效（会多出 Mortal 系模型），
#     官方域完全忽略 mtd。
#   * 落盘 = <output_dir>/<report_id>.naga（原样的 gzip 字节；用户 m05545 ② 之前是 .json.gz）。
#   * 两种来源各有价值（用户 m05392）：官方 = 纯净报告；ricochet + mtd = 多出 Mortal 系模型。
#     所以撞到同一个 report_id 时，官方来源「本地已有同名文件就跳过」，ricochet 来源「下载并覆盖」。
#   * 判重键 = **完整的 report_id**（用户 m00418：换主视角的是 url 的 tw 参数，与 report_id 无关；
#     report_id 里的 v2_2 后缀是报告格式的一部分，不剥掉）。
# ---------------------------------------------------------------------------
NAGA_HOST_NATIVE = "naga.dmv.nico"
NAGA_HOST_PROXY = "ricochet.cn"
NAGA_NATIVE_ENDPOINT = "https://naga.dmv.nico/reports/{report_id}.json.gz"
NAGA_PROXY_ENDPOINT = "https://ricochet.cn/api/naga/proxy/reports/{report_id}.json.gz"
NAGA_FILE_SUFFIX = paths.NAGA_SUFFIX   # 新后缀（用户 m05545 ②）：两种来源共用
# 旧后缀：只用于读取 / 判重兼容（不再写出）
NAGA_LEGACY_SUFFIXES = paths.NAGA_LEGACY_SUFFIXES
NAGA_FILE_SUFFIXES = paths.NAGA_SUFFIXES
NAGA_ID_BODY_LEN = 64
# 文本里的 naga report_id（主体 ≥64 个十六进制字符；天凤特征码是 10 位数字，不会误伤）
NAGA_ID_ANY_RE = re.compile(r"[0-9a-fA-F]{%d,}(?:v\d+(?:_\d+)*)?" % NAGA_ID_BODY_LEN)
# report_id = <十六进制主体><可选 v2_2 这类格式后缀（属于 report_id 的一部分）>
NAGA_ID_RE = re.compile(r"^(?P<body>[0-9a-fA-F]{%d,})(?P<suffix>v\d+(?:_\d+)*)?$" % NAGA_ID_BODY_LEN)
NAGA_URL_HINT_RE = re.compile(r"report_id=|naga\.dmv\.nico|ricochet\.cn|/api/naga/|\.json\.gz|\.naga\b", re.I)


def looks_like_naga_url(text):
    """是不是 naga / ricochet 的牌谱 url（或裸 report_id，而不是天凤特征码）。"""
    value = str(text or "").strip()
    if not value:
        return False
    if NAGA_URL_HINT_RE.search(value):
        return True
    return bool(NAGA_ID_RE.match(value))


def naga_report_key(report_id):
    """report_id 的判重键 = **完整的一串**（含结尾 v2_2 这类格式后缀，只去掉文件后缀）。

    用户 m00418：改变主视角的是 url 里的 tw=0/1/2/3 参数，与 report_id 无关，
    所以 report_id 判重必须用完整序列（tw 不参与判重）。
    """
    value = str(report_id or "").strip()
    low = value.lower()
    for suffix in NAGA_FILE_SUFFIXES:
        if low.endswith(suffix):
            value = value[: -len(suffix)]
            break
    match = NAGA_ID_RE.match(value)
    if not match:
        raise ValueError("无法解析 naga report_id：「%s」" % value[:120])
    return value.lower()


def build_naga_url(form, report_id, mtd=None):
    """按来源形式重建下载 url（ricochet 的 mtd 原样带上）。"""
    report_id = str(report_id or "").strip()
    if str(form) == "ricochet":
        url = NAGA_PROXY_ENDPOINT.format(report_id=report_id)
        if mtd:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"mtd": mtd})
        return url
    return NAGA_NATIVE_ENDPOINT.format(report_id=report_id)


def parse_naga_url(text):
    """naga / ricochet 的 url（或裸 report_id）-> {form, report_id, key, mtd, url}。"""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("输入为空")
    parsed = urllib.parse.urlparse(raw)
    query = urllib.parse.parse_qs(parsed.query)
    report_id = ""
    for name in ("report_id", "reportId", "report", "id"):
        if query.get(name):
            report_id = query[name][0].strip()
            break
    if not report_id:
        path = (parsed.path or raw).rstrip("/")
        low = path.lower()
        for suffix in NAGA_FILE_SUFFIXES:
            if low.endswith(suffix):
                path = path[: -len(suffix)]
                break
        tail = path.split("/")[-1]
        if NAGA_ID_RE.match(tail):
            report_id = tail
    if not report_id:
        match = NAGA_ID_ANY_RE.search(raw)
        if match:
            report_id = match.group(0)
    if not report_id:
        raise ValueError("无法从「%s」里解析出 naga 牌谱 report_id" % raw[:120])
    host = (parsed.netloc or "").lower()
    form = "ricochet" if (NAGA_HOST_PROXY in host or "/api/naga/proxy" in raw) else "naga"
    mtd = (query.get("mtd") or [None])[0]
    return {"form": form, "report_id": report_id, "key": naga_report_key(report_id),
            "mtd": mtd, "url": build_naga_url(form, report_id, mtd)}


def _ssl_context():
    """https 用的 SSLContext：优先用 certifi 的 CA 包，拿不到就用系统默认证书。"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def split_naga_bytes(raw):
    """把响应体规整成 (gzip 字节, 明文 json 字节)。"""
    if raw[:2] == b"\x1f\x8b":
        try:
            return raw, gzip.decompress(raw)
        except (OSError, EOFError) as exc:
            raise DownloadError("naga 报告解压失败：%s" % exc)
    return gzip.compress(raw), raw


def fetch_naga_report(target, timeout=30.0, retries=3):
    """下载 naga 报告，返回 (gzip 字节, json 字节)。

    target 可以是 url，也可以是 parse_naga_url() 的结果 dict。
    """
    info = target if isinstance(target, dict) else parse_naga_url(target)
    url = info["url"]
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                raw = response.read()
            data, body = split_naga_bytes(raw)
            try:
                parsed = json.loads(body.decode("utf-8", "replace"))
            except ValueError as exc:
                raise DownloadError("naga 报告不是 JSON（%d 字节）：%s" % (len(body), exc))
            if not isinstance(parsed, dict) or not (parsed.get("pred") or parsed.get("player_info")):
                raise DownloadError("内容不像 naga 报告（%d 字节，可能是 404 页面）" % len(body))
            return data, body
        except DownloadError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            sys.stderr.write("  ! 第 %d/%d 次尝试失败：%s\n" % (attempt, retries, exc))
    raise DownloadError("下载 %s 失败：%s" % (url, last_error))


def save_naga_report(report_id, data, output_dir, overwrite=True):
    """写 <output_dir>/<report_id>.naga（原样的 gzip 字节，用户 m05545 ②）。返回 (path, written)。"""
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "%s%s" % (report_id, NAGA_FILE_SUFFIX))
    if os.path.exists(path) and not overwrite:
        return path, False
    with open(path, "wb") as fh:
        fh.write(data)
    return path, True


def find_naga_files(output_dir, key):
    """列出 output_dir 里判重键（report_id 主体）相同的 naga 报告文件（含旧后缀 .json.gz / .json）。"""
    out = []
    if not os.path.isdir(output_dir):
        return out
    want = str(key or "").lower()
    output_dir = os.path.abspath(output_dir)
    for name in sorted(os.listdir(output_dir)):
        if not name.lower().endswith(NAGA_FILE_SUFFIXES):
            continue
        try:
            if naga_report_key(name) == want:
                out.append(os.path.join(output_dir, name))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# mortal 牌谱（用户 m05545 ①）
#   * 下载端点：https://mjai.ekyu.moe/report/<report_id>.json（明文 JSON，不需要 Referer）
#     killerducky 的查看页 ?data=/report/<report_id>.json 也能解析出同一个 report_id。
#   * report_id = 16 位十六进制（如 fb13c2973c0eabb3）。
#   * 落盘 = <output_dir>/<report_id>.mortal-a / -b / -c（原样的 JSON 文本）：
#     后缀按 review.model_tag 区分风格 —— 4.1a 避四 / 4.1b 平衡 / 4.1c 争一
#     （用户 m05806 ②）；tag 认不出来时退回通用的 .mortal。
#   * 只有 ekyu.moe 一个来源，所以判重口径与天凤 / naga 官方一致：
#     本地已有同名报告（任意 .mortal-a / -b / -c）就跳过、不重复下载。
#   * 报告里的 review.model_tag 就是模型版本（4.1a / 4.1b / 4.1c），
#     ekyu.moe 上传页把风格写成 defensive / balanced / aggressive
#     ⇒ 对应 避四 / 平衡 / 争一（用户 m05545 ① 询问的「区分风格的关键字」）。
# ---------------------------------------------------------------------------
MORTAL_HOST = "mjai.ekyu.moe"
MORTAL_ENDPOINT = "https://mjai.ekyu.moe/report/{report_id}.json"
MORTAL_FILE_SUFFIX = paths.MORTAL_SUFFIX               # 通用后缀（老文件 / 认不出的 tag）
MORTAL_FILE_SUFFIXES = paths.MORTAL_SUFFIXES
MORTAL_STYLE_SUFFIXES = paths.MORTAL_STYLE_SUFFIXES
MORTAL_SUFFIX_BY_TAG = paths.MORTAL_SUFFIX_BY_TAG
MORTAL_ID_RE = re.compile(r"^[0-9a-fA-F]{16}$")
MORTAL_ID_ANY_RE = re.compile(r"[0-9a-fA-F]{16}")
MORTAL_URL_HINT_RE = re.compile(r"mjai\.ekyu\.moe|killerducky|/report/[0-9a-fA-F]{16}\.json", re.I)
# model_tag -> 风格（来自 ekyu.moe 上传页的 <select id="mortal-model-tag"> 选项文案）
MORTAL_MODEL_STYLES = {"4.1a": "避四", "4.1b": "平衡", "4.1c": "争一"}
MORTAL_MODEL_LABELS = {"4.1a": "defensive", "4.1b": "balanced", "4.1c": "aggressive"}


def mortal_suffix_for(model_tag):
    """model_tag（4.1a / 4.1b / 4.1c）-> 落盘后缀（用户 m05806 ②）。"""
    tag = str(model_tag or "").strip().lower()
    return MORTAL_SUFFIX_BY_TAG.get(tag, MORTAL_FILE_SUFFIX)


# 判重 / 剥后缀按「长后缀优先」：.mortal-b 必须先于 .mortal 匹配（用户 m05806 ②）
_MORTAL_STRIP_SUFFIXES = tuple(sorted(MORTAL_FILE_SUFFIXES + (".json",), key=len, reverse=True))


def _strip_mortal_name(name):
    """文件名 / url 末段 -> report_id 主体（剥掉 .mortal-a|b|c / .mortal / .json）。"""
    text = str(name or "")
    low = text.lower()
    for suffix in _MORTAL_STRIP_SUFFIXES:
        if low.endswith(suffix):
            return text[: -len(suffix)]
    return text


def looks_like_mortal_url(text):
    """是不是 mortal（ekyu.moe）的牌谱 url（或裸 report_id）。"""
    value = str(text or "").strip()
    if not value:
        return False
    if MORTAL_URL_HINT_RE.search(value):
        return True
    return bool(MORTAL_ID_RE.match(value))


def mortal_report_key(report_id):
    """report_id 的判重键（16 位十六进制，小写；顺手剥掉文件后缀）。"""
    value = str(report_id or "").strip()
    low = value.lower()
    for suffix in _MORTAL_STRIP_SUFFIXES:
        if low.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if not MORTAL_ID_RE.match(value):
        raise ValueError("无法解析 mortal report_id：「%s」" % value[:120])
    return value.lower()


def build_mortal_url(report_id):
    return MORTAL_ENDPOINT.format(report_id=report_id)


def parse_mortal_url(text):
    """mortal url / killerducky 查看页 / 裸 report_id -> {form, report_id, key, url}。"""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("输入为空")
    parsed = urllib.parse.urlparse(raw)
    query = urllib.parse.parse_qs(parsed.query)
    report_id = ""
    for name in ("report_id", "reportId", "report", "id", "data"):
        if query.get(name):
            tail = _strip_mortal_name(query[name][0].strip().rstrip("/").split("/")[-1])
            if MORTAL_ID_RE.match(tail):
                report_id = tail
                break
    if not report_id:
        path = (parsed.path or raw).rstrip("/")
        tail = _strip_mortal_name(path.split("/")[-1])
        if MORTAL_ID_RE.match(tail):
            report_id = tail
    if not report_id:
        match = MORTAL_ID_ANY_RE.search(raw)
        if match:
            report_id = match.group(0)
    if not report_id:
        raise ValueError("无法从「%s」里解析出 mortal 牌谱 report_id" % raw[:120])
    return {"form": "mortal", "report_id": report_id, "key": mortal_report_key(report_id),
            "url": build_mortal_url(report_id)}


def mortal_model_info(data):
    """报告字节 -> {model_tag, style, style_en, temperature}（认不出返回 {}）。

    model_tag 在 review.model_tag（4.1a / 4.1b / 4.1c），风格名来自 ekyu.moe 上传页。
    """
    try:
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
        parsed = json.loads(text)
    except (ValueError, AttributeError):
        return {}
    review = parsed.get("review") if isinstance(parsed, dict) else None
    if not isinstance(review, dict):
        return {}
    tag = str(review.get("model_tag") or "").strip()
    info = {"temperature": review.get("temperature")}
    if tag:
        info["model_tag"] = tag
        info["style"] = MORTAL_MODEL_STYLES.get(tag, tag)
        info["style_en"] = MORTAL_MODEL_LABELS.get(tag, tag)
    return info


def fetch_mortal_report(target, timeout=30.0, retries=3):
    """下载 mortal 报告，返回 (原始 JSON 字节, 模型信息 dict)。"""
    info = target if isinstance(target, dict) else parse_mortal_url(target)
    url = info["url"]
    headers = {"User-Agent": USER_AGENT}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                raw = response.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            data = raw
            try:
                parsed = json.loads(data.decode("utf-8", "replace"))
            except ValueError as exc:
                raise DownloadError("mortal 报告不是 JSON（%d 字节）：%s" % (len(data), exc))
            if not isinstance(parsed, dict) or not (parsed.get("mjai_log") or parsed.get("review")):
                raise DownloadError("内容不像 mortal 报告（%d 字节，可能是 404 页面）" % len(data))
            enriched = dict(info)
            enriched.update(mortal_model_info(data))
            return data, enriched
        except DownloadError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            sys.stderr.write("  ! 第 %d/%d 次尝试失败：%s\n" % (attempt, retries, exc))
    raise DownloadError("下载 %s 失败：%s" % (url, last_error))


def save_mortal_report(report_id, data, output_dir, overwrite=True, model_tag=None):
    """写 <output_dir>/<report_id>.mortal-a|b|c（按 model_tag，用户 m05806 ②）。

    返回 (path, written)。
    """
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "%s%s" % (report_id, mortal_suffix_for(model_tag)))
    if os.path.exists(path) and not overwrite:
        return path, False
    with open(path, "wb") as fh:
        fh.write(data)
    return path, True


def find_mortal_files(output_dir, key):
    """列出 output_dir 里判重键相同的 mortal 报告文件。"""
    out = []
    if not os.path.isdir(output_dir):
        return out
    want = str(key or "").lower()
    output_dir = os.path.abspath(output_dir)
    for name in sorted(os.listdir(output_dir)):
        low = name.lower()
        if not any(low.endswith(sfx) for sfx in MORTAL_FILE_SUFFIXES):
            continue
        try:
            if mortal_report_key(name) == want:
                out.append(os.path.join(output_dir, name))
        except ValueError:
            continue
    return out
# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------
def run_download(urls, out_dir, overwrite=True, on_item=None, progress=None):
    """同步下载（天凤 mjlog、naga / ricochet 报告、mortal 报告可以混在同一个列表里）。
    返回 {dir,total,saved,failed,skipped,duplicate,results}。

    判重（用户 m00268 / m00418）：naga / ricochet 两类 url 按**完整的 report_id** 判重
    （主视角是 url 的 tw 参数、与 report_id 无关），与天凤特征码、mortal report_id 互不判重。

    同名文件的取舍（新后缀 .tenhou / .naga / .mortal-a|b|c，用户 m05545 ② / m05806 ②）：天凤牌谱发现本地已有同名
    <log_id>.tenhou（或旧后缀 .xml）就跳过、不发请求（用户 m05480）；mortal 只有一个来源，
    同样同名跳过；naga 官方来源（naga.dmv.nico）发现本地已有该 report_id 的报告就跳过（用户 m05392）；
    ricochet 来源在 overwrite=True 时忽略本地同名文件、重新下载并覆盖（ricochet 带 mtd 时模型更全）。
    同一次下载里同一个来源的重复 url 仍然算重复。

    on_item(entry) 每下载完一个就回调一次（顺序输出用）；
    progress(**kw) 给界面进度用，kw = done/total/current/saved/failed/skipped/duplicate。
    """
    urls = list(urls or [])
    out = os.path.abspath(out_dir)
    if not os.path.isdir(out):
        os.makedirs(out, exist_ok=True)
    results = []
    saved = failed = skipped = duplicate = 0
    total = len(urls)
    seen = {}                       # 判重键 -> 已下载文件的绝对路径
    seen_forms = {}                 # naga 判重键 -> 本次已下载过的来源形式集合（用户 m05392）
    for i, item in enumerate(urls):
        entry = {"input": item, "ok": False, "kind": "tenhou", "log_id": None, "report_id": None,
                 "form": None, "key": None, "path": None, "bytes": 0, "written": False,
                 "duplicate": False, "error": None, "model_tag": None, "style": None}
        try:
            if looks_like_mortal_url(item):
                info = parse_mortal_url(item)
                entry.update({"kind": "mortal", "form": info["form"],
                              "report_id": info["report_id"], "key": info["key"]})
                kept = None
                if info["key"] in seen:
                    kept = seen[info["key"]]            # 本次下载里已经下过这条牌谱
                else:
                    found = find_mortal_files(out, info["key"])
                    if found:
                        kept = found[0]                 # 只有 ekyu.moe 一个来源 ⇒ 同名跳过
                if kept is not None:
                    entry.update({"ok": True, "duplicate": True, "path": kept})
                    duplicate += 1
                    skipped += 1
                else:
                    data, minfo = fetch_mortal_report(info)
                    path, written = save_mortal_report(info["report_id"], data, out,
                                                       overwrite=overwrite, model_tag=minfo.get("model_tag"))
                    seen[info["key"]] = path
                    entry.update({"ok": True, "path": path, "bytes": len(data), "written": written,
                                  "model_tag": minfo.get("model_tag"), "style": minfo.get("style")})
                    if written:
                        saved += 1
                    else:
                        skipped += 1
            elif looks_like_naga_url(item):
                info = parse_naga_url(item)
                entry.update({"kind": "naga", "form": info["form"],
                              "report_id": info["report_id"], "key": info["key"]})
                kept = None
                if info["form"] in (seen_forms.get(info["key"]) or ()):
                    kept = seen.get(info["key"])        # 本次下载里同一个来源已经下过这张牌谱
                else:
                    for path in find_naga_files(out, info["key"]):
                        # 官方来源：本地已有同名报告就不再重复下载（用户 m05392）；
                        # ricochet 来源：允许覆盖时忽略本地同名文件，重新下载并覆盖它
                        #（ricochet 带 mtd 会多出 NAGA-超副露 / Mortal 系模型）。
                        if info["form"] == "ricochet" and overwrite:
                            continue
                        kept = path
                        break
                if kept is not None:
                    entry.update({"ok": True, "duplicate": True, "path": kept})
                    duplicate += 1
                    skipped += 1
                else:
                    data, _body = fetch_naga_report(info)
                    path, written = save_naga_report(info["report_id"], data, out, overwrite=overwrite)
                    seen[info["key"]] = path
                    seen_forms.setdefault(info["key"], set()).add(info["form"])
                    entry.update({"ok": True, "path": path, "bytes": len(data), "written": written})
                    if written:
                        saved += 1
                    else:
                        skipped += 1
            else:
                log_id = extract_log_id(item)
                entry["log_id"] = log_id
                entry["key"] = log_id
                kept = None
                if log_id in seen:
                    kept = seen[log_id]            # 本次下载里已经下过这条牌谱
                else:
                    # 天凤牌谱：本地已有同名 <log_id>.tenhou（或旧后缀 .xml）就跳过、不重复下载
                    #（用户 m05480 / m05545 ②；不再像以前那样直接覆盖，也不再发请求）。
                    for _sfx in (TENHOU_FILE_SUFFIX,) + TENHOU_LEGACY_SUFFIXES:
                        _p = os.path.join(out, "%s%s" % (log_id, _sfx))
                        if os.path.exists(_p):
                            kept = _p
                            break
                if kept is not None:
                    entry.update({"ok": True, "duplicate": True, "path": kept})
                    duplicate += 1
                    skipped += 1
                else:
                    data = fetch_log(log_id)
                    if not looks_like_mjlog(data):
                        raise DownloadError("下载内容不像 mjlog 牌谱（%d 字节）" % len(data))
                    path, written = save_log(log_id, data, out, overwrite=overwrite)
                    seen[log_id] = path
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
            progress(done=i + 1, total=total,
                     current=(entry.get("report_id") or entry.get("log_id") or item),
                     saved=saved, failed=failed, skipped=skipped, duplicate=duplicate)
    return {"dir": out, "total": total, "saved": saved, "failed": failed,
            "skipped": skipped, "duplicate": duplicate, "results": results}


# 后台下载进度（服务端 GET /api/download-progress 用；与 cli.PROGRESS 同构）
DOWNLOAD = {}
DOWNLOAD_LOCK = threading.Lock()


def download_reset(**kw):
    with DOWNLOAD_LOCK:
        DOWNLOAD.clear()
        now = time.time()
        DOWNLOAD.update({"running": False, "done": False, "total": 0, "done_n": 0,
                         "current": "", "saved": 0, "failed": 0, "skipped": 0, "duplicate": 0,
                         "dir": "", "error": None, "started_at": now, "updated_at": now,
                         "elapsed_ms": 0})
        coerce = {"done_n": int, "total": int, "saved": int, "failed": int,
                  "skipped": int, "duplicate": int}
        for k, v in kw.items():
            if k in coerce and v is not None:
                v = coerce[k](v)
            DOWNLOAD[k] = v
        DOWNLOAD["updated_at"] = time.time()


def download_update(**kw):
    with DOWNLOAD_LOCK:
        if kw.get("started_at") is None and not DOWNLOAD.get("started_at"):
            DOWNLOAD["started_at"] = time.time()
        coerce = {"done_n": int, "total": int, "saved": int, "failed": int,
                  "skipped": int, "duplicate": int}
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
                        failed=kw.get("failed"), skipped=kw.get("skipped"),
                        duplicate=kw.get("duplicate"))

    def _worker():
        try:
            res = run_download(urls, out, overwrite=overwrite, progress=_progress)
            download_update(running=False, done=True, total=res["total"], done_n=res["total"],
                            current="", saved=res["saved"], failed=res["failed"],
                            skipped=res["skipped"], duplicate=res["duplicate"],
                            dir=res["dir"])
        except Exception as exc:
            download_update(running=False, done=True, error="%s: %s" % (type(exc).__name__, exc))

    thread = threading.Thread(target=_worker, name="paipu-download", daemon=True)
    thread.start()
    return {"ok": True, "started": True, "dir": out, "total": len(urls)}