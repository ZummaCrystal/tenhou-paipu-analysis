#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""server.py —— 启动本地服务（前端 + /api），实现在 mjscore/server.py。

用法：
    python server.py               # http://127.0.0.1:8770/
    python server.py --port 9000
启动后用浏览器打开上面打印的地址（前端页面在 web/index.html），
「牌谱分析」与「牌谱检索」两个入口才会生效。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mjscore import server

if __name__ == "__main__":
    sys.exit(server.serve(argv=sys.argv[1:]))