# -*- coding: utf-8 -*-
"""目录解析：把「随程序分发的只读资源」与「用户数据」分开。

打包（PyInstaller）之后 `__file__` 指向的是解包出来的临时目录，不能再按「项目根 / data」
找用户数据；装到 Program Files 下更写不进去。所以这里统一两条根路径：

- `resource_root()`：只读资源（`web/`、`media/`、`mjscore/node_harness.js`）。
  源码运行 = 项目根；冻结后 = `sys._MEIPASS`（onedir 下即 exe 旁的 `_internal/`）。
- `data_root()`：用户数据（它下面才是 `data/db`、`data/paipu`）。
  源码运行 = 项目根 —— 与改造前完全一致，开发/测试零影响；
  冻结后 = `%LOCALAPPDATA%\\<APP_DIR_NAME>`（用户 m00178 决策 3；卸载时询问是否删除数据）。
  环境变量 `MJSCORE_DATA_ROOT` 优先（Electron 主进程 / 绿色版 / 测试用）。

作者：Zumma Crystal <z1025zzsg@sohu.com>。
"""

import os
import sys

# 打包后 %LOCALAPPDATA% 下的目录名（用户 m00178 决策 3）；正式打包时与 electron-builder
# 的 productName 对齐（见 build.ps1 / desktop/package.json）。
APP_DIR_NAME = "tenhou-paipu-analysis"


def resource_root():
    """只读资源根目录（`web/`、`media/`、`mjscore/` 都在它下面）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.abspath(meipass)
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root():
    """用户数据根目录（`data/db`、`data/paipu` 的上一级）。"""
    env = os.environ.get("MJSCORE_DATA_ROOT")
    if env:
        return os.path.abspath(env)
    if getattr(sys, "frozen", False):
        base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                or os.path.expanduser("~"))
        return os.path.join(base, APP_DIR_NAME)
    return resource_root()


def data_dir():
    """`data/` 目录（`paipu/` 与 `db/` 的父目录）。"""
    return os.path.join(data_root(), "data")


def db_dir():
    """`data/db` —— 分析结果 SQLite 的固定存放目录。"""
    return os.path.join(data_dir(), "db")


def paipu_root():
    """`data/paipu` —— 下载的牌谱 .xml 的固定存放根。"""
    return os.path.join(data_dir(), "paipu")
