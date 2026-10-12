# -*- coding: utf-8 -*-
r"""subset_font.py - 从官方 NAGA viewer 的 Noto Sans JP Black 生成「大字」子集字体

用途: 生成 media/fonts/NotoSansJP-Black.subset.otf（随包发布，见 web/style.css 的 @font-face）。

字体来源 = 官方 viewer 的 vocalization 字体（SIL OFL 1.1，可再分发；许可证全文见
media/fonts/LICENSE-NotoSansJP-OFL.txt）:
  https://naga.dmv.nico/static/fonts/NotoSansJP-Black.9a73d583.otf   (4,896,876 B, 魔数 OTTO)

只保留大字用得到的 9 个字形「チ ー ポ ン カ ツ モ ロ ン リ」（约 5.5 KB），避免把 4.9 MB 的
全量字体塞进安装包。以后要加字（例如立直的「リーチ」已经含在内）改 --text 后重跑本脚本即可。

依赖: fonttools（pip install fonttools）。子集化在**进程内**调用 fontTools.subset.main，
不走子进程管道（受限环境里匿名管道可能被拒绝，见 log.md 的踩坑）。

用法:
  python tools\subset_font.py                       # 本地没有全量字体时自动下载到临时目录
  python tools\subset_font.py --source D:\tmp\NotoSansJP-Black.otf
  python tools\subset_font.py --text "チーポンカツモロンリ" --out media\fonts\xx.otf
"""
import argparse
import os
import sys
import tempfile
import urllib.request

URL = 'https://naga.dmv.nico/static/fonts/NotoSansJP-Black.9a73d583.otf'
DEFAULT_TEXT = 'チーポンカツモロンリ'
DEFAULT_OUT = os.path.join('media', 'fonts', 'NotoSansJP-Black.subset.otf')


def fetch(url, dst):
    """下载全量字体（官方域不需要 Referer / 特殊 UA）。"""
    print('下载', url)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    with open(dst, 'wb') as f:
        f.write(data)
    print('  写入', dst, len(data), 'B')
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(description='生成大字（vocalization）子集字体')
    ap.add_argument('--source', default=None, help='本地全量字体；不给则先下载')
    ap.add_argument('--text', default=DEFAULT_TEXT, help='要保留的字符（默认 9 个大字字形）')
    ap.add_argument('--out', default=DEFAULT_OUT, help='输出路径')
    a = ap.parse_args(argv)

    src = a.source
    if not src:
        src = os.path.join(tempfile.gettempdir(), os.path.basename(URL))
        if not os.path.exists(src):
            fetch(URL, src)
        else:
            print('复用临时文件', src)

    if not os.path.exists(src):
        print('找不到全量字体:', src, file=sys.stderr)
        return 2

    try:
        from fontTools import subset
    except ImportError:
        print('需要 fonttools: pip install fonttools', file=sys.stderr)
        return 3

    out_dir = os.path.dirname(os.path.abspath(a.out))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # --desubroutinize / --no-hinting：去掉 CFF 子程序与 hinting，浏览器兼容性最好
    # --name-IDs=* ：保留字体名（SIL OFL 要求保留版权与名称声明）
    args = [src, '--text=' + a.text, '--output-file=' + a.out,
            '--no-hinting', '--desubroutinize', '--name-IDs=*', '--drop-tables+=DSIG']
    print('子集化', len(a.text), '个字符 ->', a.out)
    subset.main(args)

    from fontTools.ttLib import TTFont
    f = TTFont(a.out)
    cmap = f.getBestCmap()
    missing = [c for c in a.text if ord(c) not in cmap]
    print('  输出 %d B / 字形 %d 个 / 缺字 %s'
          % (os.path.getsize(a.out), len(f.getGlyphOrder()), ('、'.join(missing) or '无')))
    if missing:
        print('警告: 全量字体里没有这些字，请检查 --text', file=sys.stderr)
        return 4
    return 0


if __name__ == '__main__':
    sys.exit(main())
