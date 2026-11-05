# v1.6.0

v1.6.0（**1.6.x 线首个正式版**）：新增 6 个「直接进张」特征与轻量数据库。

## 新增

- **6 个「直接进张」特征**（第 85 轮）：第二类特征从 17 项增加到 23 项，总特征数 42 → 48，可填特征 34 → 40。
  - `furo_tsumo_advance_avail` / `furo_tsumo_advance_abs`：副露自摸直接进张枚数 / 绝对枚数。
  - `furo_ron_advance_avail` / `furo_ron_advance_abs`：副露荣和直接进张枚数 / 绝对枚数。
  - `menzen_advance_avail` / `menzen_advance_abs`：立直/默听直接进张枚数 / 绝对枚数。
  - 计算嵌入现有 `Expect.node()` 进张枚举：d=0 复用 `tp`，d=1 复用 `kids` 的 `tp > 0` 判役，14 张出牌帧在 `keep` 的各切牌节点中分别取 max；不新开枚举。
  - 只在 d≤1 有值（d≥2 为 0）；按剩余张数累计，不按牌种数；副露假设与立直/默听假设分别判定。
- **轻量数据库**：新建库默认「轻量」，也可用 `--standard` 新建标准库。
  - 轻量库只把三种向听数的内部上限从 3 改成 2（`2` 显示 `>=2`）；其余 45 个特征与标准库相同。
  - `Expect.max_shanten` 在轻量/标准库中都保持 1。
  - 扩充已有数据库时，目标库 `meta.db_type` 始终权威（包括空库）；类型冲突只 warning，不改库类型。
- **当前帧特征面板**：34 → 40 行，一屏显示，无滚动条。

## 变更

- 删除 `--full` 参数和界面「同时写入原始数据」复选框；数据库**始终写入** `frame_full`。
- schema 11 → **12**；新增 6 个 `s_*_advance_*` 特征列与 `meta.db_type`。
- 检索仍按内部整数值匹配：轻量库 `2` 命中 `>=2`；`3` / `>=3` / `4` 返回空；不做跨库优先。

## 修正

- **扩充空库的类型口径**：目标库已有 `meta.db_type` 时，即使还没有任何牌谱记录，也按目标库类型执行并保留原类型。
- `/api/analyze` 的 `light` 请求值改为显式布尔解析，避免字符串 `"false"` 被当成 True。

## 兼容性

- **数据库结构版本为 12**。v1.5.x / schema 11 及以前的库不再支持，需要删除后重新分析；牌谱文件不必重新下载。
- v1.6.x 同大/中版本的库可以继续扩充 / 检索；补丁版本不同不影响。
- 用户数据（牌谱 / 数据库 / 日志）仍在 `%LOCALAPPDATA%\tenhou-paipu-analysis\`，卸载不会删除。

## 下载

| 文件 | 体积 | SHA256 |
| --- | --- | --- |
| `tenhou-paipu-analysis-1.6.0-setup.exe` | 143,352,742 B | `B03DA57B102990648F4678F86ABDE1E3E4DE56B3DB86D6CA2C29549A6CBC99A9` |

上一版：`tenhou-paipu-analysis-1.5.1-setup.exe`（143,348,426 B / SHA256 `ABF8DBA0FF2AF77FC9AEE75CA6877DBA3002EF3285612D6DD338E3EA6D05DC1A`）。1.5.x 首个正式版：`tenhou-paipu-analysis-1.5.0-setup.exe`（143,338,298 B / SHA256 `02FC1BEEA464F3294C636046F05E15A14A40472B1F4CBBE6C4CD96F31879CBD6`）。1.4.x 稳定版：`tenhou-paipu-analysis-1.4.4-setup.exe`（143,292,183 B / SHA256 `D764F5CF0BC39B0431D82B0A7976EFDDC9D250D5356F1C7B59875A3C82D3B190`）。源码：tag `v1.6.0`。

## 安装与升级

- Windows 安装包（NSIS 向导），只支持 Windows x64。
- 从 v1.5.x 升级后旧数据库会提示版本不兼容；删除旧库并重新分析即可。
- 后端自检：`/api/health` 返回 `version 1.6.0`。

## 校验

```powershell
certutil -hashfile tenhou-paipu-analysis-1.6.0-setup.exe SHA256
```

## 其它

- 版本线：本版是 1.6.x 线首个正式版；1.5.x 上一版为 v1.5.1（1.5.x 补丁版，v1.5.0 为首个正式版）；1.4.x 稳定版为 v1.4.4（维护分支 `stable/1.4.4`），1.3.x 为 v1.3.1（`stable/1.3.1`）。
- 使用说明见仓库 `readme.md`；开发过程记录见 `docs/readme-dev.md` 与 `log.md`。
