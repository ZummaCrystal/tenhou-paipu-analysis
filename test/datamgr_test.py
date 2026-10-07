# -*- coding: utf-8 -*-
"""本地数据管理自检：mjscore/datamgr.py + mjscore/paths.py + /api/fs-* 接口。

重点验证用户 m00590 的硬约束：
  * 牌谱文件不能移出 data/paipu，数据库文件不能移出 data/db（含 `..`、绝对路径、
    盘符、非法字符、软链接/目录联接等绕过手段）；
  * 数据根本身不可删；
  * 迁移到 %LOCALAPPDATA%/tenhou-paipu-analysis/data 之后，真实服务仍能正常读取。

用法（项目根执行）：
  python test/datamgr_test.py
"""

import json
import os
import shutil
import subprocess
import sys
import uuid
import threading
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)

from mjscore import datamgr, paths, server   # noqa: E402

PASS = [0]
FAIL = []


def ok(cond, msg):
    if cond:
        PASS[0] += 1
    else:
        FAIL.append(msg)


def raises(fn, *a, **kw):
    """调用应抛 DataError；返回错误文本，不该抛则返回 None。"""
    try:
        fn(*a, **kw)
    except datamgr.DataError as exc:
        return str(exc)
    except Exception as exc:                      # noqa: BLE001
        return "!!未预期异常 %s: %s" % (type(exc).__name__, exc)
    return None


def has(text, *words):
    return text is not None and all(w in text for w in words)


def sec(name):
    print("---- %s ----" % name)


# ================= 1. paths：数据根解析 =================
sec("1. mjscore/paths.py 数据根")
TMPBASE = os.path.join(PROJ, "test", "_tmp")
os.makedirs(TMPBASE, exist_ok=True)
# 注意：这里不用 tempfile.mkdtemp()：它建出来的目录在 Windows 上带「仅所有者」ACL，
# 受限令牌下反而写不进去（本机实测 WinError 5）。
tmp = os.path.join(TMPBASE, "datamgr-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8]))
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp)
old_env = os.environ.get("MJSCORE_DATA_ROOT")
os.environ["MJSCORE_DATA_ROOT"] = tmp
ok(paths.data_root() == os.path.abspath(tmp), "MJSCORE_DATA_ROOT 应优先")
ok(paths.data_dir() == os.path.join(os.path.abspath(tmp), "data"), "data_dir 应拼 data")
ok(paths.db_dir() == os.path.join(os.path.abspath(tmp), "data", "db"), "db_dir 应拼 data/db")
ok(paths.paipu_root() == os.path.join(os.path.abspath(tmp), "data", "paipu"), "paipu_root 应拼 data/paipu")
os.environ.pop("MJSCORE_DATA_ROOT", None)
if old_env is not None:
    os.environ["MJSCORE_DATA_ROOT"] = old_env
ok(paths.data_root() == PROJ, "源码运行时 data_root 应等于项目根")
ok(paths.resource_root() == PROJ, "源码运行时 resource_root 应等于项目根")

# ================= 2. datamgr：越界与操作 =================
sec("2. mjscore/datamgr.py 越界拦截与增删移")
base = os.path.join(tmp, "data")
pd, dd = os.path.join(base, "paipu"), os.path.join(base, "db")
os.makedirs(os.path.join(pd, "2026"))
os.makedirs(os.path.join(dd))
with open(os.path.join(pd, "2026", "a.xml"), "wb") as f:
    f.write(b"<mjloggm ver=\"2.3\"/>")
with open(os.path.join(dd, "20261007_test.sqlite"), "wb") as f:
    f.write(b"SQLite format 3\x00")

real_root_dir = datamgr.root_dir


def fake_root_dir(root):
    if root == "paipu":
        return pd
    if root == "db":
        return dd
    return real_root_dir(root)


datamgr.root_dir = fake_root_dir
try:
    ok(has(raises(datamgr.root_dir, "paipu2"), "未知的数据根"), "未知数据根应报错")
    ok(datamgr.norm_rel("a\\b/./c") == "a/b/c", "反斜杠/点应规范化")
    ok(datamgr.norm_rel("") == "", "空相对路径 = 根")
    ok(has(raises(datamgr.norm_rel, "../x"), ".."), ".. 应被拒")
    ok(has(raises(datamgr.norm_rel, "a/../../x"), ".."), "夹在中间的 .. 应被拒")
    ok(has(raises(datamgr.norm_rel, "C:/Windows/x"), "相对路径"), "盘符应被拒")
    ok(has(raises(datamgr.norm_rel, "/etc/passwd"), "相对路径"), "绝对路径应被拒")
    ok(has(raises(datamgr.norm_rel, "\\\\server\\share"), "相对路径"), "UNC 应被拒")
    ok(has(raises(datamgr.norm_rel, "a*b"), "非法字符"), "非法字符应被拒")
    ok(datamgr.norm_rel(' x ') == 'x', '整条路径首尾空格应被自动去掉')
    ok(has(raises(datamgr.norm_rel, 'a/ b/c'), '空格'), '中间段名首尾空格应被拒')
    ok(has(raises(datamgr.norm_rel, "" , allow_empty=False), "路径为空"), "allow_empty=False")
    ok(datamgr._abs_of("paipu", "") == os.path.abspath(pd), "_abs_of 根")
    ok(datamgr._abs_of("paipu", "2026") == os.path.abspath(os.path.join(pd, "2026")), "_abs_of 子目录")
    ok(has(raises(datamgr._abs_of, "db", "../paipu"), ".."), "db 根里 .. 到 paipu")
    ok(has(raises(datamgr._abs_of, "db", "..\\..\\Windows"), ".."), "db 根里 ..\\..")
    ok(has(raises(datamgr._abs_of, "paipu", "C:\\\\Windows"), "相对路径"), "_abs_of 绝对路径")

    # 迁移/移动（同根内）
    r = datamgr.move("paipu", "2026/a.xml", "")
    ok(r["to"] == "a.xml" and os.path.isfile(os.path.join(pd, "a.xml")), "文件应移到根")
    r = datamgr.move("paipu", "a.xml", "2026")
    ok(r["to"] == "2026/a.xml" and os.path.isfile(os.path.join(pd, "2026", "a.xml")), "文件应移回子目录")
    ok(has(raises(datamgr.move, "paipu", "2026/a.xml", "../.."), ".."), "dest=../.. 应被拒")
    ok(has(raises(datamgr.move, "paipu", "2026/a.xml", "C:/Windows"), "相对路径"), "dest=绝对路径应被拒")
    ok(has(raises(datamgr.move, "paipu", "2026/a.xml", "nope"), "目标目录不存在"), "dest 不存在应报错")
    os.makedirs(os.path.join(pd, "2026", "sub"))
    ok(has(raises(datamgr.move, "paipu", "2026", "2026/sub"), "不能把目录移动到"), "目录移进自己子目录应被拒")
    ok(has(raises(datamgr.move, "paipu", "2026", "2026"), "不能把目录移动到"), "目录原地移动应被拒")
    with open(os.path.join(pd, "2026", "b.xml"), "wb") as f:
        f.write(b"x")
    with open(os.path.join(pd, "b.xml"), "wb") as f:
        f.write(b"x")
    ok(has(raises(datamgr.move, "paipu", "2026/b.xml", ""), "同名"), "同名冲突应被拒")
    os.remove(os.path.join(pd, "b.xml"))

    # 数据库根：数据库既不能上移出根，也不能跨到 paipu
    ok(has(raises(datamgr.move, "db", "20261007_test.sqlite", "../paipu"), ".."), "数据库不能跨根移动")
    ok(has(raises(datamgr.move, "db", "20261007_test.sqlite", "..\\..\\paipu"), ".."), "数据库不能跨根移动(反斜杠)")
    ok(has(raises(datamgr.move, "db", "20261007_test.sqlite", ""), "相同"), "数据库在根目录时不能移出")
    ok(has(raises(datamgr.remove, "paipu", "2026"), "是目录"), "remove 目录应被拒")
    ok(has(raises(datamgr.rmdir, "paipu", ""), "路径为空"), "不能删数据根本身")
    ok(has(raises(datamgr.rmdir, "db", ""), "路径为空"), "不能删数据库根本身")
    ok(has(raises(datamgr.rmdir, "paipu", "nope"), "目录不存在"), "rmdir 不存在")
    ok(has(raises(datamgr.mkdir, "paipu", "", "a/b"), "分隔符"), "mkdir 名字带分隔符应被拒")
    ok(has(raises(datamgr.mkdir, "paipu", "", ".."), "不能是"), "mkdir 名字 .. 应被拒")
    ok(has(raises(datamgr.mkdir, "db", "", "x<y"), "非法字符"), "mkdir 非法字符应被拒")
    r = datamgr.mkdir("paipu", "2026", "newdir")
    ok(r["created"] == "2026/newdir", "mkdir 返回完整相对路径")
    ok(has(raises(datamgr.mkdir, "paipu", "2026", "newdir"), "已经存在同名"), "mkdir 重名应被拒")
    ok(datamgr.listing("db")["files"][0]["path"] == "20261007_test.sqlite", "listing 文件带 path")
    ok(all(not f["name"].endswith(".sqlite") for f in datamgr.listing("paipu")["files"]),
       "paipu 根里不该有数据库（数据隔离）")

    # 软链接 / 目录联接逃逸
    jail = os.path.join(tmp, "jail")
    os.makedirs(jail)
    with open(os.path.join(jail, "escape.xml"), "wb") as f:
        f.write(b"x")
    link = os.path.join(pd, "link")
    made = subprocess.run(["cmd", "/c", "mklink", "/J", link, jail],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if made and os.path.isdir(link):
        msg = raises(datamgr._abs_of, "paipu", "link")
        ok(has(msg, "越界"), "目录联接指向外面应被判越界（实际：%s）" % (msg,))
        msg2 = raises(datamgr.move, "paipu", "link", "")
        ok(msg2 is not None, "通过联接移动应被拒")
        os.rmdir(link) if False else None
        try:
            subprocess.run(["cmd", "/c", "rmdir", link], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except Exception:
            pass
    else:
        print("   （跳过软链接测试：本环境无法创建目录联接）")
finally:
    datamgr.root_dir = real_root_dir

# ================= 3. 真实服务 + 迁移后的数据目录 =================
sec("3. 迁移后的 %LOCALAPPDATA% 数据 + 真实 /api/fs-* 接口")
local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "tenhou-paipu-analysis")
mig_data = os.path.join(local, "data")
mig_paipu, mig_db = os.path.join(mig_data, "paipu"), os.path.join(mig_data, "db")
if not (os.path.isdir(mig_paipu) and os.path.isdir(mig_db)):
    print("   （跳过：%s 不存在）" % mig_data)
else:
    xmls = []
    for dirpath, _dirs, files in os.walk(mig_paipu):
        xmls += [os.path.join(dirpath, f) for f in files if f.lower().endswith(".xml")]
    sqlites = [f for f in os.listdir(mig_db) if f.lower().endswith(".sqlite")]
    print("   迁移目录: %s 牌谱 %d 个 / 数据库 %d 个" % (mig_data, len(xmls), len(sqlites)))
    os.environ["MJSCORE_DATA_ROOT"] = local
    httpd = server.make_server(0, "127.0.0.1")
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    origin = "http://127.0.0.1:%d" % port

    def req(path, payload=None):
        url = origin + path
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        r = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {"raw": body}

    try:
        st, health = req("/api/health")
        ok(st == 200 and health.get("ok"), "/api/health 正常")
        ok(os.path.normcase(health.get("data_root", "")) == os.path.normcase(local),
           "health.data_root 应指向迁移目录（实际 %s）" % health.get("data_root"))
        ok(os.path.normcase(health.get("paipu_dir", "")) == os.path.normcase(mig_paipu), "health.paipu_dir")
        ok(os.path.normcase(health.get("db_dir", "")) == os.path.normcase(mig_db), "health.db_dir")

        st, scan = req("/api/scan?dir=" + urllib.parse.quote(mig_paipu))
        ok(st == 200, "/api/scan 正常")
        ok(scan.get("count") == len(xmls), "scan 数量应与磁盘一致（%s vs %s）" % (scan.get("count"), len(xmls)))
        ok(all(os.path.isabs(f) for f in (scan.get("files") or [])), "scan 应返回绝对路径")

        st, dl = req("/api/fs-list?root=paipu&rel=")
        ok(st == 200 and dl.get("root_dir") and os.path.normcase(dl["root_dir"]) == os.path.normcase(mig_paipu),
           "fs-list(paipu) 根路径正确")
        ok("20261007-165558" in [d["name"] for d in dl.get("dirs", [])], "fs-list(paipu) 有牌谱子目录")
        st, ldb = req("/api/fs-list?root=db&rel=")
        ok(st == 200 and sqlites and sqlites[0] in [f["name"] for f in ldb.get("files", [])],
           "fs-list(db) 能看到数据库文件")

        # 必须被拒的越界请求（拒绝时不得改动任何文件）
        before = sorted(os.listdir(mig_db))
        st, e1 = req("/api/fs-move", {"root": "paipu", "rel": "20261007-165558/../..", "dest": ""})
        ok(st == 400, "fs-move rel 带 .. 应 400（实际 %s）" % st)
        st, e2 = req("/api/fs-move", {"root": "db", "rel": sqlites[0], "dest": "../../paipu"})
        ok(st == 400, "数据库跨根移动应 400（实际 %s）" % st)
        st, e3 = req("/api/fs-move", {"root": "db", "rel": sqlites[0], "dest": "C:/Windows"})
        ok(st == 400, "dest 用绝对路径应 400（实际 %s）" % st)
        st, e4 = req("/api/fs-move", {"root": "paipu", "rel": "..\\..\\x.xml", "dest": ""})
        ok(st == 400, "rel 反斜杠 .. 应 400（实际 %s）" % st)
        st, e5 = req("/api/fs-rmdir", {"root": "paipu", "rel": ""})
        ok(st == 400, "删牌谱根本身应 400（实际 %s）" % st)
        st, e6 = req("/api/fs-rmdir", {"root": "db", "rel": ""})
        ok(st == 400, "删数据库根本身应 400（实际 %s）" % st)
        st, e7 = req("/api/fs-delete", {"root": "paipu", "rel": "../db/%s" % sqlites[0]})
        ok(st == 400, "delete 跨根应 400（实际 %s）" % st)
        st, e8 = req("/api/fs-mkdir", {"root": "db", "rel": "..", "name": "evil"})
        ok(st == 400, "mkdir rel=.. 应 400（实际 %s）" % st)
        after = sorted(os.listdir(mig_db))
        ok(before == after, "被拒的请求不应改动数据库目录")
        ok(os.path.isfile(os.path.join(mig_db, sqlites[0])), "数据库文件仍在原处")
        print("   400 示例：%s | %s" % (e1.get("error", e1), e2.get("error", e2)))
    finally:
        httpd.shutdown()
        httpd.server_close()
        os.environ.pop("MJSCORE_DATA_ROOT", None)

shutil.rmtree(tmp, ignore_errors=True)

sec("结果")
print("通过 %d 项，失败 %d 项" % (PASS[0], len(FAIL)))
for f in FAIL:
    print("  FAIL: %s" % (f,))
sys.exit(1 if FAIL else 0)