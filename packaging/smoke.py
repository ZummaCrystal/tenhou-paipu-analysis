# -*- coding: utf-8 -*-
"""打包后的冒烟测试：启动冻结版后端 exe，轮询 /api/health，打印关键信息，然后收掉进程树。

    <python> packaging\\smoke.py --exe dist\\pyi\\tenhou-paipu-analysis-server\\tenhou-paipu-analysis-server.exe
                               [--host 127.0.0.1] [--port 8770] [--timeout 40]
                               [--data-root <临时数据根>] [--log build\\pyi\\smoke-backend.log]

为什么要这个小脚本：冻结后的后端拿到的是解包目录里的只读资源 + 用户数据目录
（%LOCALAPPDATA%\\tenhou-paipu-analysis），必须确认它真能起来、真能读到数据目录。
后端的 stdout/stderr 写文件而不是管道（受限环境里管道会报 WinError 5）。

退出码：0 = 健康检查通过；1 = 失败（日志在 --log 指向的文件里）。
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

KEYS = ("name", "version", "author", "root", "data_root", "db_dir", "paipu_dir")


def http_json(url, timeout=3.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def kill_tree(pid):
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/pid", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            return
        except Exception:
            pass
    try:
        os.kill(pid, 9)
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="冻结后端冒烟测试")
    ap.add_argument("--exe", required=True, help="冻结后的 tenhou-paipu-analysis-server.exe")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--timeout", type=float, default=40.0, help="等 /api/health 的总秒数")
    ap.add_argument("--data-root", default="", help="临时数据根（不传则用真实用户数据目录）")
    ap.add_argument("--log", default=os.path.join("build", "pyi", "smoke-backend.log"))
    a = ap.parse_args(argv)

    exe = os.path.abspath(a.exe)
    if not os.path.isfile(exe):
        print("找不到后端 exe：" + exe)
        return 1
    logp = os.path.abspath(a.log)
    os.makedirs(os.path.dirname(logp), exist_ok=True)

    env = dict(os.environ)
    if a.data_root:
        env["MJSCORE_DATA_ROOT"] = os.path.abspath(a.data_root)
    base = "http://%s:%d" % (a.host, a.port)
    print("启动 : " + exe)
    print("监听 : " + base)
    print("日志 : " + logp)
    if a.data_root:
        print("数据 : " + env["MJSCORE_DATA_ROOT"])

    with open(logp, "wb") as lf:
        proc = subprocess.Popen([exe, "--host", a.host, "--port", str(a.port)],
                                cwd=os.path.dirname(exe), env=env,
                                stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT)
        health = None
        last = "未尝试"
        deadline = time.time() + a.timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                last = "后端进程已退出（退出码 %s），先看日志" % proc.returncode
                break
            try:
                health = http_json(base + "/api/health")
                break
            except Exception as e:
                last = "%s: %s" % (type(e).__name__, e)
                time.sleep(0.5)

        rc = 0
        if health is None:
            print("失败 : /api/health 拿不到 —— " + last)
            rc = 1
        else:
            print("就绪 : %s 用时 %.1fs" % (base, a.timeout - max(0.0, deadline - time.time())))
            for k in KEYS:
                if k in health:
                    print("  %-9s %s" % (k, health[k]))
            if not health.get("data_root"):
                print("失败 : health 里没有 data_root（mjscore/server.py 的 /api/health 应暴露它）")
                rc = 1
            elif not os.path.isdir(health["data_root"]):
                print("注意 : data_root 目录还不存在（首次运行会按需创建）：" + health["data_root"])
            try:
                dbs = http_json(base + "/api/dbs")
                items = dbs.get("dbs") if isinstance(dbs, dict) else dbs
                items = items or []
                names = ", ".join(str(x.get("name", "?")) for x in items) or "无"
                print("  dbs       %d 个（%s）" % (len(items), names))
            except Exception as e:
                print("  dbs       /api/dbs 读不了（不致命）：%s: %s" % (type(e).__name__, e))
        try:
            proc.terminate()
        except Exception:
            pass
        kill_tree(proc.pid)
    return rc


if __name__ == "__main__":
    sys.exit(main())