# -*- coding: utf-8 -*-
"""本地服务：托管前端静态文件 + 提供 /api 接口。

浏览器出于安全不能直接读写本地磁盘、也不能拉起 python，所以「牌谱分析 / 牌谱检索」
都经由这个本地服务完成：

    GET  /                       302 跳转到 /web/index.html（页面在 web/，素材在 media/）
    GET  /api/health             {ok:true, name, version, author, author_email}（软件名 / 版本号 v0.1.0 / 作者）
    GET  /api/features           33 个特征定义（16 个第一类 + 17 个第二类，m02959）+ 打点口径
    GET  /api/dbs                已建数据库列表（data/db/*.sqlite）
    GET  /api/scan?dir=<绝对路径>  列出一个目录（递归）下的牌谱 .xml
    GET  /api/read?path=<绝对路径>  读出牌谱文件文本（前端解析不了时用）
    POST /api/analyze            {paths:[], db_name, db, tool, full, extend}  -> 打点入库（同步阻塞）
                                 extend=true = 扩充已有数据库（库里已有的牌谱自动跳过）
    GET  /api/analyze-progress   分析进度（前端轮询；{progress:{...}}）
    POST /api/query             {db_name, db, conds:[{key,expr}], limit, offset} -> 检索
    POST /api/browse            {db_name, db, limit, offset} -> 全部浏览（按特征码顺序；limit<=0 = 全部）
    POST /api/detail            {db_name, db, idx} -> 单行详情
    POST /api/round-frames      {db_name, db, log_id, round_index} -> 一局内的打点行
    POST /api/frame-feats       {db_name, db, log_id, round_index, frame_index, seat} -> 单帧 33 个特征值
    POST /api/download          {url | text | url_file, subdir} -> 下载牌谱到 data/paipu/<子目录>（后台线程）
    GET  /api/download-progress 牌谱下载进度（前端轮询；{progress:{...}}）
    POST /api/delete-db         {name, db_name} -> 删除数据库
    GET  /api/fs-list?root=paipu|db&rel=<相对路径>  本地数据管理：列目录（子目录 / 文件 / 上级）
    POST /api/fs-mkdir          {root, rel, name} -> 新建子目录
    POST /api/fs-move           {root, rel, dest} -> 移动文件 / 目录（dest='' 表示数据根）
    POST /api/fs-delete         {root, rel} -> 删除文件
    POST /api/fs-rmdir          {root, rel} -> 删除子目录（连同里面的内容）

只监听本机回环地址；静态文件根目录固定为项目根（页面在 web/、前端 js 在 web/js/、
素材在 media/）。用户数据（data/db、data/paipu）的根目录见 mjscore/paths.py：源码运行
时就是项目根，打包后是 %LOCALAPPDATA%\\<AppName>；所以前端读写数据一律传**绝对路径**
（数据管理接口用 root=paipu|db + 相对路径，由服务端自己拼根目录）。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

import argparse
import json
import os
import posixpath
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import cli, datamgr, download, feats, paths, store
from . import APP_NAME, AUTHOR, AUTHOR_EMAIL, __version__ as APP_VERSION

ROOT = cli.ROOT
DEFAULT_PORT = 8770
DEFAULT_HOST = "127.0.0.1"
MAX_TEXT = 16 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def _abs(p):
    p = str(p or "")
    if not p:
        raise ApiError("路径为空")
    if not os.path.isabs(p):
        p = os.path.join(ROOT, p)
    return os.path.abspath(p)


def _db_of(payload):
    db = payload.get("db")
    if db:
        p = _abs(db)
        if not os.path.isfile(p):
            raise ApiError("数据库文件不存在：%s" % p)
        return p
    name = (payload.get("db_name") or cli.DEFAULT_DB_NAME).strip()
    if not name:
        raise ApiError("数据库名为空")
    if os.path.sep in name or "/" in name:
        p = _abs(name)
        if not os.path.isfile(p):
            raise ApiError("数据库文件不存在：%s" % p)
        return p
    # 库名统一交给 cli.db_path_of（它会补 .sqlite、且不重复追加），
    # 避免「检索能打开、扩充说库不存在」这种两套解析器不一致的 bug（m04115①）。
    return cli.db_path_of(None, name)


def _scan_dir(path):
    if not os.path.isdir(path):
        raise ApiError("目录不存在：%s" % path)
    files = []
    for dirpath, _dirs, names in os.walk(path):
        for fn in sorted(names):
            if fn.lower().endswith(".xml"):
                files.append(os.path.join(dirpath, fn))
    return {"dir": path, "count": len(files), "files": files}


def _browse(conn, limit, offset):
    """limit <= 0 表示不加 LIMIT（前端「全部浏览」要一次取全）。"""
    total = conn.execute("SELECT COUNT(*) c FROM frame").fetchone()["c"]
    sql = "SELECT %s FROM frame ORDER BY log_id, round_index, ev_index, seat" % ", ".join(store.RESULT_COLS)
    params = ()
    if limit and limit > 0:
        sql += " LIMIT ? OFFSET ?"
        params = (limit, offset)
    rows = conn.execute(sql, params).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "rows": [dict(r) for r in rows]}


def api_analyze(payload):
    paths = payload.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        raise ApiError("请先选择要分析的牌谱文件或目录")
    files = [_abs(p) for p in paths]
    tool = payload.get("tool") or "auto"
    if tool not in ("auto", "node", "python"):
        raise ApiError("打点工具只能是 auto / node / python")
    res = cli.analyze(files, db=payload.get("db") or None,
                      db_name=payload.get("db_name") or None,
                      tool=tool, full=bool(payload.get("full")),
                      extend=bool(payload.get("extend")))
    return res


def api_query(payload):
    conds = payload.get("conds")
    if conds is None and payload.get("lines"):
        conds = cli.parse_condition_lines(payload["lines"])
    if not conds:
        raise ApiError("请先添加并填写牌谱特征条件")
    res = cli.run_query(_db_of(payload), conds,
                        limit=int(payload.get("limit") or 200),
                        offset=int(payload.get("offset") or 0))
    return res


def api_browse(payload):
    limit = payload.get("limit")
    limit = 200 if limit is None else int(limit)
    conn = store.connect(_db_of(payload), create=False)
    try:
        return _browse(conn, limit, int(payload.get("offset") or 0))
    finally:
        conn.close()


def api_detail(payload):
    conn = store.connect(_db_of(payload), create=False)
    try:
        return {"row": store.query_detail(conn, int(payload.get("idx")))}
    finally:
        conn.close()


def api_round_frames(payload):
    conn = store.connect(_db_of(payload), create=False)
    try:
        return {"rows": store.round_frames(conn, payload.get("log_id"), int(payload.get("round_index")))}
    finally:
        conn.close()


def api_delete_db(payload):
    name = payload.get("name") or payload.get("db_name") or payload.get("db")
    if not name:
        raise ApiError("没有指定要删除的数据库")
    p = _db_of({"db": name} if os.path.isabs(str(name)) else {"db_name": name})
    if os.path.isfile(p):
        os.remove(p)
        return {"ok": True, "deleted": p}
    raise ApiError("数据库不存在：%s" % p)


def api_frame_feats(payload):
    conn = store.connect(_db_of(payload), create=False)
    try:
        row = store.frame_feats(conn, payload.get("log_id"),
                               payload.get("round_index"),
                               payload.get("frame_index"),
                               payload.get("seat"))
    finally:
        conn.close()
    return {"row": row}


def api_download(payload):
    """下载一个 / 一批牌谱到 data/paipu/<子目录>（后台线程，进度见 /api/download-progress）。"""
    out = download.resolve_out_dir(payload.get("subdir") or payload.get("dir_sub")
                                   or payload.get("sub_dir"))
    urls = []
    single = payload.get("url")
    if single:
        urls.append(str(single))
    text = payload.get("text")
    if text:
        urls.extend(download.read_url_lines(text))
    path = payload.get("url_file")
    if path:
        p = _abs(path)
        if not os.path.isfile(p):
            raise ApiError("URL 文本文件不存在：%s" % p)
        urls.extend(download.read_url_file(p))
    items = payload.get("urls")
    if items:
        if isinstance(items, str):
            items = download.read_url_lines(items)
        urls.extend(items)
    urls = download.collect_urls(urls)
    if not urls:
        raise ApiError("请先输入一个牌谱 URL，或选择一个「每行一个 URL」的文本文件")
    res = download.start_download(urls, out, overwrite=True)
    res["urls"] = len(urls)
    return res


def _data_root_of(payload):
    """取数据根参数（'paipu' 牌谱 / 'db' 数据库），缺省 paipu。"""
    return str(payload.get("root") or "paipu")


def api_fs_list(q):
    """本地数据管理：列出某个数据根下的一层目录内容（用户 m00178 第 9 条）。"""
    return datamgr.listing((q.get("root") or ["paipu"])[0], (q.get("rel") or [""])[0])


def api_fs_mkdir(payload):
    """在指定目录下新建一个子目录。"""
    return datamgr.mkdir(_data_root_of(payload), payload.get("rel"), payload.get("name"))


def api_fs_move(payload):
    """把文件 / 目录移动到另一个目录（dest='' = 数据根，也支持上级目录 / 子目录）。"""
    return datamgr.move(_data_root_of(payload), payload.get("rel"), payload.get("dest"))


def api_fs_delete(payload):
    """删除一个文件。"""
    return datamgr.remove(_data_root_of(payload), payload.get("rel"))


def api_fs_rmdir(payload):
    """删除一个子目录（连同里面的内容）。"""
    return datamgr.rmdir(_data_root_of(payload), payload.get("rel"),
                         recursive=bool(payload.get("recursive", True)))


GET_ROUTES = {
    "/api/health": lambda q: {"ok": True, "root": ROOT, "name": APP_NAME, "version": APP_VERSION, "author": AUTHOR, "author_email": AUTHOR_EMAIL,
                               "data_root": paths.data_root(), "db_dir": paths.db_dir(), "paipu_dir": paths.paipu_root()},
    "/api/features": lambda q: {"features": feats.FEATURES, "doukou": store.DOUKOU,
                                "full_note": store.FULL_NOTE,
                                "schema_version": store.SCHEMA_VERSION,
                                "name": APP_NAME, "version": APP_VERSION, "author": AUTHOR, "author_email": AUTHOR_EMAIL},
    "/api/dbs": lambda q: {"dbs": cli.list_dbs(), "dir": cli.DB_DIR},
    "/api/fs-list": api_fs_list,
    "/api/scan": lambda q: _scan_dir(_abs((q.get("dir") or [paths.data_dir()])[0])),
    "/api/analyze-progress": lambda q: {"progress": cli.progress_snapshot()},
    "/api/download-progress": lambda q: {"progress": download.download_snapshot()},
}

POST_ROUTES = {
    "/api/analyze": api_analyze,
    "/api/query": api_query,
    "/api/browse": api_browse,
    "/api/detail": api_detail,
    "/api/round-frames": api_round_frames,
    "/api/frame-feats": api_frame_feats,
    "/api/download": api_download,
    "/api/delete-db": api_delete_db,
    "/api/fs-mkdir": api_fs_mkdir,
    "/api/fs-move": api_fs_move,
    "/api/fs-delete": api_fs_delete,
    "/api/fs-rmdir": api_fs_rmdir,
}


class Handler(SimpleHTTPRequestHandler):
    server_version = "mjscore/%s" % APP_VERSION
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # -------------------------------------------------- 工具
    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if not raw.strip():
            return {}
        try:
            return json.loads(raw.decode("utf-8").lstrip("\ufeff"))
        except Exception as exc:
            raise ApiError("请求体不是合法 JSON：%s" % exc)

    def _query(self):
        parsed = urllib.parse.urlparse(self.path)
        return urllib.parse.parse_qs(parsed.query), parsed.path

    def log_message(self, fmt, *args):
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    # -------------------------------------------------- 路由
    def end_headers(self):
        # 前端页面搬家过（index.html 在 web/ 下）：HTML 一律不缓存，避免浏览器拿旧页面
        # 里的相对引用去取 /style.css、/js/*.js 而 404（用户 m04553）。
        try:
            head = b"".join(self._headers_buffer)
            if b"text/html" in head and b"Cache-Control" not in head:
                self.send_header("Cache-Control", "no-store, must-revalidate")
        except Exception:
            pass
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        q, path = self._query()
        if path == "/api/read":
            try:
                p = _abs((q.get("path") or [""])[0])
                if not os.path.isfile(p):
                    raise ApiError("文件不存在：%s" % p)
                if os.path.getsize(p) > MAX_TEXT:
                    raise ApiError("文件过大（>16MB）：%s" % p)
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                return self._send_json({"path": p, "text": text})
            except ApiError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, exc.code)
        # 前端页面在 web/ 下（项目根只放 server.py）：/ 与 /index.html 用 302 跳到 /web/index.html。
        # 必须真正跳转（不能内部改写 URL），否则页面里的相对引用
        # （style.css、js/*.js）会解析成 /style.css / /js/*.js —— 那是改造前的旧路径，现在都在 web/ 下，会 404（用户 m04553）。
        if path in ("/", "/index.html"):
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            loc = "/web/index.html" + (("?" + qs) if qs else "")
            body = b""
            self.send_response(302)
            self.send_header("Location", loc)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in GET_ROUTES:
            try:
                return self._send_json(GET_ROUTES[path](q))
            except ApiError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, exc.code)
            except ValueError as exc:
                # datamgr.DataError 是 ValueError 子类：非法输入按 400 回，不要落 500
                return self._send_json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:
                return self._send_json({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}, 500)
        if path.startswith("/api/"):
            return self._send_json({"ok": False, "error": "未知接口：%s" % path}, 404)
        # 兼容改造前的旧路径（浏览器缓存里可能还是旧的 index.html，其相对引用是 /style.css、/js/*.js）：
        # 根目录没有、而 web/ 下有同名文件时，302 跳到 /web/…（用户 m04553 复盘）。
        rel = posixpath.normpath(path.lstrip("/"))
        legacy = os.path.join(ROOT, "web", rel)
        if (not rel.startswith("..")) and os.path.isfile(legacy):
            body = b""
            self.send_response(302)
            self.send_header("Location", "/web/" + rel)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_HEAD(self):
        return super().do_HEAD()

    def do_POST(self):
        q, path = self._query()
        fn = POST_ROUTES.get(path)
        if fn is None:
            return self._send_json({"ok": False, "error": "未知接口：%s" % path}, 404)
        try:
            payload = self._read_json()
            return self._send_json(fn(payload))
        except ApiError as exc:
            return self._send_json({"ok": False, "error": str(exc)}, exc.code)
        except (ValueError, FileNotFoundError) as exc:
            return self._send_json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:
            return self._send_json({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}, 500)


def make_server(port=DEFAULT_PORT, host=DEFAULT_HOST):
    return ThreadingHTTPServer((host, port), Handler)


def serve(port=None, host=None, argv=None):
    if argv is not None:
        ap = argparse.ArgumentParser(prog="server.py", description="天凤牌谱分析本地服务")
        ap.add_argument("--port", type=int, default=DEFAULT_PORT)
        ap.add_argument("--host", default=DEFAULT_HOST)
        a = ap.parse_args(argv)
        port, host = a.port, a.host
    port = int(port or DEFAULT_PORT)
    host = host or DEFAULT_HOST
    httpd = make_server(port, host)
    url = "http://%s:%d/" % (host, httpd.server_address[1])
    sys.stderr.write("天凤牌谱分析服务已启动：%s\n" % url)
    sys.stderr.write("  静态根目录 %s（前端页面 web/index.html）\n  （Ctrl+C 停止）\n" % ROOT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n已停止。\n")
    finally:
        httpd.server_close()
    return 0