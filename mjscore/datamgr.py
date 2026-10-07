# -*- coding: utf-8 -*-
"""本地数据管理：对 `data/paipu`（牌谱）与 `data/db`（数据库）做目录/文件操作。

前端「本地数据管理」视图（牌谱管理 / 数据库管理）经 /api/fs-* 接口落到这里。
背景（用户 m00178 第 9 条）：数据目录将来固定在 `%LOCALAPPDATA%\\<AppName>\\data` 下，
用户不方便自己开资源管理器，所以界面里要能：新建目录 / 移动位置（含移动到子目录、
上级目录）/ 删除文件 / 删除子目录。

安全口径：唯一入口 `_abs_of()` —— 相对路径先规范化，禁止绝对路径、盘符、`..`、
名字里的非法字符，最后再用 `commonpath` + `realpath` 复核结果确实落在该数据根下面（软链接/目录联接也不行）；
`rmdir` 只允许删根下面的子目录，绝不允许删数据根本身。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

import os
import shutil

# 两个数据根（前端 data-root 属性 / API 的 root 参数取值）
ROOTS = ("paipu", "db")
ROOT_LABELS = {"paipu": "牌谱（data/paipu）", "db": "数据库（data/db）"}
# Windows 文件名非法字符（Linux/macOS 只禁 "/"，但数据目录要跨平台安全）
BAD_CHARS = '<>:"|?*'


class DataError(ValueError):
    """数据管理的非法输入（服务端按 400 返回，前端直接显示 message）。"""


def root_dir(root):
    """'paipu' / 'db' -> 该数据根的绝对路径（测试里可 monkeypatch 本函数）。"""
    from . import paths
    if root == "paipu":
        return paths.paipu_root()
    if root == "db":
        return paths.db_dir()
    raise DataError("未知的数据根：%s（只能是 paipu / db）" % (root,))


def roots_info():
    """两个数据根的绝对路径，供界面显示 / 请求参数用。"""
    return {r: root_dir(r) for r in ROOTS}


def norm_rel(rel, allow_empty=True):
    """把用户输入的相对路径规范化；返回统一用 '/' 分隔的相对路径。"""
    s = str(rel if rel is not None else "").strip().replace("\\", "/")
    if s in ("", ".", "/"):
        if allow_empty:
            return ""
        raise DataError("路径为空")
    if s.startswith("/") or os.path.isabs(s) or (len(s) >= 2 and s[1] == ":"):
        raise DataError("只能是数据目录下的相对路径，收到「%s」" % (rel,))
    parts = []
    for raw in s.split("/"):
        if raw in ("", "."):
            continue
        if raw == "..":
            raise DataError("相对路径里不能出现 ..（用「移动到」的目录下拉选上级），收到「%s」" % (rel,))
        if raw.strip() != raw:
            raise DataError("名字首尾不能有空格：「%s」" % (raw,))
        if any(c in raw for c in BAD_CHARS):
            raise DataError("名字里有非法字符（%s）：「%s」" % (BAD_CHARS, raw))
        parts.append(raw)
    return "/".join(parts)


def check_name(name):
    """新建目录 / 重命名用的单个名字校验。"""
    n = str(name if name is not None else "").strip()
    if not n:
        raise DataError("名字不能为空")
    if n in (".", ".."):
        raise DataError("名字不能是「%s」" % (n,))
    if "/" in n or "\\" in n:
        raise DataError("名字里不能有路径分隔符：「%s」" % (n,))
    if any(c in n for c in BAD_CHARS):
        raise DataError("名字里有非法字符（%s）：「%s」" % (BAD_CHARS, n))
    return n


def _rel(base, path):
    """绝对路径 -> 相对 base 的 '/' 路径（base 自身返回 ''）。"""
    r = os.path.relpath(os.path.abspath(path), os.path.abspath(base))
    r = r.replace("\\", "/")
    return "" if r == "." else r


def _abs_of(root, rel):
    """(数据根, 相对路径) -> 绝对路径；越界/非法一律 DataError。"""
    base = os.path.abspath(root_dir(root))
    n = norm_rel(rel)
    path = os.path.abspath(base if not n else os.path.join(base, *n.split("/")))
    if path != base:
        try:
            inside = os.path.commonpath([base, path]) == base
        except ValueError:          # 不同盘符
            inside = False
        if not inside:
            raise DataError("路径越界：%s" % (rel,))
        # 二次复核：堵住「数据根里的软链接/目录联接（junction）指向外面」这条绕过路径，
        # 保证「牌谱只能待在 data/paipu、数据库只能待在 data/db」这条硬约束（用户 m00590）。
        real_base = os.path.realpath(base)
        real_path = os.path.realpath(path)
        if real_base != real_path:
            try:
                if os.path.commonpath([real_base, real_path]) != real_base:
                    raise DataError("路径越界（软链接指向数据根之外）：%s" % (rel,))
            except ValueError:
                raise DataError("路径越界（软链接指向数据根之外）：%s" % (rel,))
    return path


def dirs_of(root):
    """该数据根下所有目录的相对路径（含 '' 表示根），按层级排序 —— 供「移动到」下拉用。"""
    base = os.path.abspath(root_dir(root))
    out = [""]
    if os.path.isdir(base):
        for dirpath, dirnames, _files in os.walk(base):
            dirnames.sort()
            r = _rel(base, dirpath)
            if r:
                out.append(r)
    return sorted(set(out), key=lambda s: (s.count("/"), s))


def listing(root, rel=""):
    """列出一个目录：子目录 + 文件 + 上级目录 + 可选目标目录。"""
    base = os.path.abspath(root_dir(root))
    cur = norm_rel(rel)
    path = _abs_of(root, cur)
    if not os.path.isdir(path):
        raise DataError("目录不存在：%s" % (cur or "/",))
    dirs, files = [], []
    try:
        names = sorted(os.listdir(path))
    except OSError as exc:
        raise DataError("读不了目录 %s：%s" % (cur or "/", exc))
    for name in names:
        p = os.path.join(path, name)
        try:
            if os.path.isdir(p):
                try:
                    count = len(os.listdir(p))
                except OSError:
                    count = 0
                dirs.append({"name": name, "path": _rel(base, p), "entries": count})
            elif os.path.isfile(p):
                st = os.stat(p)
                files.append({"name": name, "path": _rel(base, p),
                              "size": st.st_size, "mtime": int(st.st_mtime),
                              "sqlite": name.lower().endswith(".sqlite")})
        except OSError:
            continue
    return {"root": root, "roots": roots_info(), "root_dir": base,
            "dir": cur, "parent": "" if not cur else "/".join(cur.split("/")[:-1]),
            "dirs": dirs, "files": files, "all_dirs": dirs_of(root)}


def mkdir(root, rel, name):
    """在 rel 下新建目录 name。"""
    n = check_name(name)
    base = os.path.abspath(root_dir(root))
    cur = norm_rel(rel)
    parent = _abs_of(root, cur)
    if not os.path.isdir(parent):
        raise DataError("目录不存在：%s" % (cur or "/",))
    path = _abs_of(root, _rel(base, os.path.join(parent, n)))
    if os.path.exists(path):
        raise DataError("已经存在同名目录或文件：%s" % (n,))
    os.makedirs(path)
    return {"ok": True, "root": root, "dir": cur, "created": _rel(base, path)}


def move(root, rel, dest):
    """把 rel 指向的条目移动到 dest 目录下（dest 可以是 '' 根、上级目录或子目录）。"""
    base = os.path.abspath(root_dir(root))
    src = _abs_of(root, rel)
    name = norm_rel(rel, allow_empty=False)
    if not os.path.exists(src):
        raise DataError("要移动的条目不存在：%s" % (name,))
    target_dir = _abs_of(root, dest)
    if not os.path.isdir(target_dir):
        raise DataError("目标目录不存在：%s" % (norm_rel(dest) or "/",))
    if os.path.isdir(src):
        if target_dir == src or os.path.commonpath([src, target_dir]) == src:
            raise DataError("不能把目录移动到它自己或它的子目录里")
    tgt = os.path.join(target_dir, os.path.basename(src))
    if os.path.abspath(tgt) == os.path.abspath(src):
        raise DataError("目标位置和原位置相同")
    if os.path.exists(tgt):
        raise DataError("目标目录里已经有同名条目：%s" % (os.path.basename(src),))
    os.rename(src, tgt)
    return {"ok": True, "root": root, "moved": name, "to": _rel(base, tgt)}


def remove(root, rel):
    """删除一个文件（目录请走 rmdir）。"""
    base = os.path.abspath(root_dir(root))
    cur = norm_rel(rel, allow_empty=False)
    path = _abs_of(root, cur)
    if os.path.isdir(path):
        raise DataError("「%s」是目录，请用「删除子目录」" % (cur,))
    if not os.path.isfile(path):
        raise DataError("文件不存在：%s" % (cur,))
    os.remove(path)
    return {"ok": True, "root": root, "deleted": cur}


def rmdir(root, rel, recursive=True):
    """删除一个子目录（默认连同里面的内容）。数据根本身不允许删。"""
    base = os.path.abspath(root_dir(root))
    cur = norm_rel(rel, allow_empty=False)
    path = _abs_of(root, cur)
    if not os.path.isdir(path):
        raise DataError("目录不存在：%s" % (cur,))
    files = sum(len(fs) for _d, _s, fs in os.walk(path))
    if not recursive:
        raise DataError("只能删除整个子目录（含里面的内容）")
    shutil.rmtree(path)
    return {"ok": True, "root": root, "deleted": cur, "files": files}
