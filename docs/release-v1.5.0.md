# v1.5.0

v1.5.0（**1.5.x 线的首个正式版**）。

## 新增

- **跨来源 `[mix]` 合并**（第 80 轮）：同一场实际对局可能有天凤牌谱、NAGA 报告、多个 Mortal 视角或多个分析模型的文件。下载后程序按牌局进程哈希判重，并把 AI 分析合并成一个 `[mix]` 前缀的文件；后缀沿用最早下载的那份文件。支持四家 Mortal 视角与多模型槽位，前端可直接解析合并后的容器。
- **假想摸进 5 的赤 / 普通区分**（第 82 轮，用户 m00398）：期望打点不再把假想摸进的和了张一律当作普通 5。程序扫描四家副露、牌河（含被鸣走的牌）和宝牌指示牌，判断赤 5 是否已公开；赤 5 尚未出现时，按剩余未见张数对「赤 5 在门清手牌 / 赤 5 为和了张 / 普通 5」加权。赤 5 已在自己手牌或已公开时，不再枚举赤 5 为和了张。

## 修正

- **期望打点补回赤 5**（第 81 轮，用户 m00001）：`mjscore/expect.py` 原先把真实手牌压成 34 计数后用 `tiles_of()` 重建牌 id，重建出的 5 永远是非赤，导致门清手牌里的赤 5 与赤 5 和了张都不计入赤宝牌；副露里的赤 5 却仍会计入，口径不一致。现在门清手牌、副露、已和牌和了张都按真实赤 5 计算，6 个期望打点特征（`furo_ron_score` / `furo_tsumo_score` / `riichi_ron_score` / `riichi_tsumo_score` / `damaten_ron_score` / `damaten_tsumo_score`）随之修正。
- 例：`123m 4m0m6m 234p 66p 45s` 听 3s/6s，立直荣和由 2000 修正为 3900，立直自摸 2700 → 5200，默听荣和 1000 → 2000，默听自摸 1500 → 2700。

## 兼容性

- **数据库结构版本仍是 11，本版没有表结构变化**。
- 但期望打点口径变化会改变已入库的特征值，因此本版按规则升**中版本**：`1.5.x` 的库可以互相加载；`1.4.x`（含 v1.4.4）建的库会被 `store.check_version()` 以「大 / 中版本不同」拒绝，**需要删除后重新分析**，没有自动迁移 / 回填。
- 删除方式：`python tools\analyze.py --delete-db <库名>`，或直接删除 `%LOCALAPPDATA%\tenhou-paipu-analysis\data\db\` 下对应的 `.sqlite`。
- 用户数据（牌谱 / 数据库 / 日志）仍在 `%LOCALAPPDATA%\tenhou-paipu-analysis\`，卸载不会删除。

## 下载

| 文件 | 体积 | SHA256 |
| --- | --- | --- |
| `tenhou-paipu-analysis-1.5.0-setup.exe` | 143,338,298 B | `02FC1BEEA464F3294C636046F05E15A14A40472B1F4CBBE6C4CD96F31879CBD6` |

上一稳定版：`tenhou-paipu-analysis-1.4.4-setup.exe`（143,292,183 B / SHA256 `D764F5CF0BC39B0431D82B0A7976EFDDC9D250D5356F1C7B59875A3C82D3B190`）。更早 v1.4.3：`tenhou-paipu-analysis-1.4.3-setup.exe`（143,292,338 B / SHA256 `36A06F2E9B5F43BCB38C99D5E155F23FD6988F0543AFF54BC4AD64D5D48448ED`）。源码：tag `v1.5.0`。

## 安装与升级

- Windows 安装包（NSIS 向导），只支持 Windows x64。
- 从 1.4.x 升级后，旧数据库会提示版本不匹配；删除旧库并重新分析即可。牌谱文件本身不需要重新下载。
- 后端自检：`/api/health` 返回 `version 1.5.0`。

## 校验

```powershell
certutil -hashfile tenhou-paipu-analysis-1.5.0-setup.exe SHA256
```

## 其它

- 版本线：本版是 1.5.x 线的首个正式版；1.4.x 线的稳定版为 v1.4.4（维护分支 `stable/1.4.4`），1.3.x 线为 v1.3.1（`stable/1.3.1`）。
- 使用说明见仓库 `readme.md`；开发过程记录见 `docs/readme-dev.md` 与 `log.md`。
