# v1.4.4

v1.4.4（**1.4.x 线的稳定版**）。

## 修正

- **检索结果 / 全部浏览的条目显示真实文件名**（用户 m10331）：从这两处打开一份牌谱时，左上角与下方信息条的文件名原先把后缀固定拼成 `<特征码>.tenhou` —— NAGA 的 `…v2_2.naga` 与 Mortal 的 `….mortal-a|b|c` 因此被误标（列表里的条目名、`复制url`、特征码本来就是对的）。现在改用条目记录里的真实路径（`log_path`）与 `/api/read` 返回的 `path` 取 basename，三种来源各自显示真实后缀：`.tenhou` / `.naga` / `.mortal-a|b|c`。
- 影响面只有「显示名」：「同一份牌谱不重复载入」的判断、`复制url` 拼接、特征码、静态帧特征串全部沿用原口径（这些位置都会先剥掉后缀）。

## 兼容性

- **数据库结构版本仍是 11，本版没有任何结构变化**：v1.4.0 / v1.4.1 / v1.4.2 / v1.4.3 / v1.4.4 之间可以互相加载、继续扩充增量库；v1.3.x 与 v1.4.x 之间不互通。
- 用户数据（牌谱 / 数据库 / 日志）仍在 `%LOCALAPPDATA%\tenhou-paipu-analysis\`，卸载不会删除。

## 下载

| 文件 | 体积 | SHA256 |
| --- | --- | --- |
| `tenhou-paipu-analysis-1.4.4-setup.exe` | 143,292,183 B | `D764F5CF0BC39B0431D82B0A7976EFDDC9D250D5356F1C7B59875A3C82D3B190` |

上一版：`tenhou-paipu-analysis-1.4.3-setup.exe`（143,292,338 B / SHA256 `36A06F2E9B5F43BCB38C99D5E155F23FD6988F0543AFF54BC4AD64D5D48448ED`）。稳定版：`tenhou-paipu-analysis-1.3.1-setup.exe`（143,288,931 B / SHA256 `38A7BA82E5C37FE12B24570627914F25A67575F7618C97AC61E3DA35791C44A7`）。源码：tag `v1.4.4`。

## 安装与升级

- Windows 安装包（NSIS 向导），安装到当前用户目录。
- 本版是前端显示名的修正，**不需要重新分析牌谱**，也不影响已有数据库。

## 校验

```powershell
certutil -hashfile tenhou-paipu-analysis-1.4.4-setup.exe SHA256
```

## 其它

- 版本线：本版是 1.4.x 线的稳定版（维护分支 `stable/1.4.4`）；1.3.x 线的稳定版为 v1.3.1（维护分支 `stable/1.3.1`）。
- 使用说明见仓库 `readme.md`；开发过程记录见 `docs/readme-dev.md` 与 `log.md`。
- 命令行：`python tools/analyze.py --help`。
