# -*- coding: utf-8 -*-
"""天凤牌谱分析 —— 后端（PyInstaller）打包器。

把 server.py + web/ + media/ + mjscore/node_harness.js（+ node.exe）打成一个 onedir
目录 dist\\pyi\\tenhou-paipu-analysis-server\\：

    <python> packaging\\pyi_build.py

脚本会把等价的 PyInstaller 命令行打印出来（参数就那一份，避免 README、build.ps1、
手敲命令三处各写一遍）。决策 1：内嵌 node.exe（默认探测常见安装路径，用 --node-exe
指定或 --skip-node 关掉）；决策 2：onedir。

受限环境（禁止创建匿名管道）下 PyInstaller 6.x 的 hook 发现在隔离子进程里跑会直接报：

    PermissionError: [WinError 5] 拒绝访问
    File "...\\PyInstaller\\isolated\\_parent.py", line 224, in create_pipe

此时加 --in-process：脚本先设 sys._pyi_isolated_subprocess = True，让 hook 发现改成
在本进程内执行（PyInstaller\\isolated\\_parent.py:215 读这个标记，:219 的 __enter__ 直接
no-op、:308 的 call() 走进程内分支）。产物与正常模式一致，只是少了隔离。

退出码：0 成功；非 0 = PyInstaller 的退出码。
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "tenhou-paipu-analysis-server"


def default_node():
    """按 mjscore\\nodeharness.py 的候选顺序找 node.exe。"""
    cands = [
        r"D:\Program Files\nodejs\node.exe",
        r"C:\Program Files\nodejs\node.exe",
        r"D:\Program Files (x86)\nodejs\node.exe",
    ]
    pf = os.environ.get("ProgramFiles")
    if pf:
        cands.insert(1, os.path.join(pf, "nodejs", "node.exe"))
    la = os.environ.get("LOCALAPPDATA")
    if la:
        cands.insert(2, os.path.join(la, "Programs", "nodejs", "node.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which("node") or ""


def build_args(a):
    """组装 PyInstaller 参数（路径全部绝对，sep 用 ';' 是本项目的 Windows 目标）。"""
    args = [
        os.path.join(ROOT, "server.py"),
        "--onedir",
        "--console",
        "--name", NAME,
        "--distpath", a.distpath,
        "--workpath", a.workpath,
        "--specpath", a.specpath,
        "--noconfirm",
        "--log-level", a.log_level,
        # 只读资源：前端、牌面素材、node 桥接脚本
        "--add-data", os.path.join(ROOT, "web") + ";web",
        "--add-data", os.path.join(ROOT, "media") + ";media",
        "--add-data", os.path.join(ROOT, "mjscore", "node_harness.js") + ";mjscore",
    ]
    if a.clean:
        args.append("--clean")
    if not a.skip_node:
        node = a.node_exe or default_node()
        if not node or not os.path.isfile(node):
            raise SystemExit("找不到 node.exe（决策 1 要求内嵌）：用 --node-exe 指定，或加 --skip-node")
        args += ["--add-binary", node + ";node"]
        a._node = node
    return args


def main(argv=None):
    ap = argparse.ArgumentParser(description="打包天凤牌谱分析后端（onedir + 内嵌 node）")
    ap.add_argument("--python-exe", default=sys.executable, help="仅用于打印等价命令")
    ap.add_argument("--node-exe", default="", help="要内嵌的 node.exe；默认自动探测")
    ap.add_argument("--skip-node", action="store_true", help="不内嵌 node.exe")
    ap.add_argument("--distpath", default=os.path.join(ROOT, "dist", "pyi"))
    ap.add_argument("--workpath", default=os.path.join(ROOT, "build", "pyi"))
    ap.add_argument("--specpath", default=os.path.join(ROOT, "packaging"))
    ap.add_argument("--log-level", default="WARN", choices=["TRACE", "DEBUG", "INFO", "WARN", "DEPRECATION", "ERROR", "FATAL"])
    ap.add_argument("--no-clean", dest="clean", action="store_false", help="不传 --clean 给 PyInstaller")
    ap.add_argument("--in-process", action="store_true", help="禁用 PyInstaller 的隔离子进程（受限环境兜底）")
    a = ap.parse_args(argv)

    args = build_args(a)
    os.makedirs(a.distpath, exist_ok=True)
    os.makedirs(a.workpath, exist_ok=True)
    os.makedirs(a.specpath, exist_ok=True)

    print("项目根   : " + ROOT)
    print("解释器   : " + a.python_exe)
    print("内嵌 node: " + (getattr(a, "_node", "") or "（不内嵌）"))
    print("等价命令 : " + subprocess.list2cmdline([a.python_exe, "-m", "PyInstaller"] + args))
    if a.in_process:
        print("模式     : --in-process（hook 发现改在本进程内执行）")
        sys._pyi_isolated_subprocess = True  # noqa: SLF001 —— PyInstaller 的私有开关

    os.chdir(ROOT)
    from PyInstaller.__main__ import run
    try:
        run(args)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())