# v1.6.0 交接文档：直接进张 6 项 + 轻量数据库

> 交接时间：v1.5.1 之后、v1.6.0 开发开始前。  
> 基线：commit `715a6bf` / v1.5.1 / schema 11 / 42 个特征。  
> 目标：v1.6.0 / schema 12 / 48 个特征（第二类 23 个、可填 40 个）。  
> **配套实施方案：`docs/impl-plan-v1.6.0-advance-features.md`。先读实施方案，再读本文。**

## 1. 一句话目标

在第二类特征中新增 6 条「直接进张」（副露自摸 / 副露荣和 / 立直默听 × 枚数 / 绝对枚数），并把它们**嵌入现有 `Expect.node()` 进张枚举**，不新开枚举；同时新增轻量数据库类型（只把三种向听数的内部上限从 3 改成 2，`Expect.max_shanten` 在轻量/标准都保持 1）。

## 2. 当前仓库状态

- 版本：v1.5.1（`mjscore/__init__.py`、`package.json`）。
- 数据库结构版本：`store.SCHEMA_VERSION = 11`。
- 特征总数：42 = 7 第零类 + 17 第一类 + 17 第二类 + 1 第三类。
- 可填特征：34 = 17 第一类 + 17 第二类。
- 三种向听数：`shanten.CAP = 3`，内部值 `-1/0/1/2/3`，`3` 表示 `>=3`。
- 期望特征枚举上限：`expect.DEFAULT_MAX_SHANTEN = 1`（标准库也只有 1）。
- 当前帧特征面板：17 第一类 + 17 第二类 = 34 行。
- `--full` 仍是可选参数；不勾选时不写 `frame_full`。
- 数据库类型：无 `db_type`，只有 standard 概念。

## 3. 本次已达成共识（不要再改）

### 3.1 新增特征

只新增 **6 条**，不是 12 条；不按国士/七対/面子拆分。

| # | 中文名 | key | 类型 | 范围 |
| --- | --- | --- | --- | --- |
| 1 | 副露自摸直接进张枚数 | `furo_tsumo_advance_avail` | int | 0..136 |
| 2 | 副露自摸直接进张绝对枚数 | `furo_tsumo_advance_abs` | int | 0..136 |
| 3 | 副露荣和直接进张枚数 | `furo_ron_advance_avail` | int | 0..136 |
| 4 | 副露荣和直接进张绝对枚数 | `furo_ron_advance_abs` | int | 0..136 |
| 5 | 立直/默听直接进张枚数 | `menzen_advance_avail` | int | 0..136 |
| 6 | 立直/默听直接进张绝对枚数 | `menzen_advance_abs` | int | 0..136 |

顺序：3 个向听 → 6 个直接进张 → 6 个期望听牌 → 6 个期望打点 → 2 个危险。第二类共 23，总 48，可填 40。

### 3.2 直接进张定义

- 当前 13-3n 张手牌（14-3n 张出牌帧先按现有规则打一张）。
- 逐牌种 `t`：摸入后，若存在一张可打的牌使 13-3n 张手牌的内部向听数 == 当前内部向听数 - 1，则该牌种计入。
- 按**剩余张数**计，不按牌种数 +1。
- `advance_avail`：`avail[t] = 4 - 可见张数`（自己手牌 + 四家副露 + 四家牌河（被鸣走的不算） + 宝牌指示牌）。
- `advance_abs`：`4 - 自己手牌张数[t] - 自己副露张数[t]`。
- 赤 5 与普通 5 同种。
- 不考虑振听。
- 只考虑自摸进张，不考虑鸣牌进张。
- **候选牌种集合沿用现有 `node()` 的进张循环**：`avail[t] == 0` 的牌种不会进入 `advance_abs`。`advance_abs` 只是在合格牌种上把枚数从 `avail[t]` 换成 `4 - 自己持有`；如果要求绝对口径连候选判定都忽略公共信息，需要另开 shape-only 枚举，不在本轮范围。
- 6 个 `da` 值必须是整数：d=0 时 `int(tp)`，d=1 时累加 `al[t]` / `4 - counts[t] - meldc[t]`。

### 3.3 覆盖范围

**方案 A：直接进张只在 `d ∈ {-1, 0, 1}` 有值，`d >= 2` 一律 0。**

- d=-1：0；
- d=0：等于现有对应 `tp`；
- d=1：统计摸入后能到 d=0 的牌种；
- d>=2：0。

### 3.4 假设

| 组 | 适用帧 | 判别器入参 |
| --- | --- | --- |
| 副露自摸 | 所有帧（门清帧也按副露假设） | `state=FURO, menzen=False, tsumo=True` |
| 副露荣和 | 所有帧（门清帧也按副露假设） | `state=FURO, menzen=False, tsumo=False` |
| 立直/默听 | 仅当前门清帧 | `state=RIICHI, menzen=True, riichi=self.riichi or 1` |

- 副露帧的立直/默听 2 项 = 0。
- 不需要 `force_open` 向听模式：d=0 子节点的 `_eval` 已经用 `state=FURO, menzen=False` 判役；d=1 读子节点 `tp > 0` 即可。

### 3.5 14 张出牌帧

- 沿用现有 `keep`：所有打到最小整体向听数的切牌。
- 对每个 `keep` 后的 13 张手牌调用现有 `node(h)`。
- 6 个直接进张特征分别在 `keep` 的节点中取 **max**。
- 不是 sum；不是期望打点 argmax 的单手。

### 3.6 轻量数据库

- `meta.db_type = "standard" | "light"`。
- 轻量：`shanten.CAP = 2`，向听值 `{-1,0,1,2}`，`2` 显示 `>=2`。
- 标准：`shanten.CAP = 3`，`{-1,0,1,2,3}`，`3` 显示 `>=3`。
- **`Expect.max_shanten` 在轻量/标准都保持 1**。轻量只改 `shanten.CAP`，不改期望特征枚举深度。
- 因此：
  - 6 个直接进张在轻量/标准库完全相同；
  - 12 个期望特征在轻量/标准库完全相同；
  - 唯一差异是 3 个向听列。
- 新建库默认轻量；扩充时按目标库类型自动勾选/禁用；类型不匹配拒绝。
- 检索按内部整数值匹配：轻量 `2` 命中 `>=2`；`3` / `>=3` / `4` 返回空；不做特殊映射。
- 展示只用当前选中的库，不做跨库优先。

### 3.7 版本与数据库

- v1.6.0；schema 12。
- 拒绝 v1.5.x / schema 11 的旧库。
- 删除 `--full`；数据库始终写 `frame_full`。
- `meta.full` 恒为 `"1"`。

### 3.8 UI

- 新建库默认勾选「开启轻量分析」。
- 扩充时自动按目标库类型勾选/禁用。
- 删除「同时写入原始数据（--full）」复选框。
- 当前帧特征面板 40 行，一屏显示完，无滚动条。

## 4. 为什么这样设计（关键代码事实）

这一节是本次交接最重要的部分。上一轮讨论中曾把「向听数枚举」和「期望特征枚举」混为一谈，下面用两个真实局面钉死。

### 4.1 图1：2 向听来自 shanten 枚举，不是 Expect 树

局面：東1局 0本場 4巡目 東家，`round_index=0, ev_index=24, seat=0`，手牌：

```
3388m 3346p 233467s
```

`shanten_at()` 返回：

```
国士無双 3，七対子 2，面子手 2
```

面子手的 2 向听来自 `shanten.mentsu_need()` 的最优拆解：

```
目标形：333m 888m 456p 33p 234s
缺的张：3m、8m、5p
不用的当前牌：3s、6s、7s
```

`need = 3` → 向听数 2。这是「打 → 摸 ×3」的组合等价物。

但同一帧的 6 个期望听牌枚数、6 个期望打点**全是 0**，因为 `Expect.node()`：

```python
if d < 0 or d > self.max:
    return zeros
```

而 `DEFAULT_MAX_SHANTEN = 1`。

**结论**：

- 标准库能识别 2 向听**数值**；
- 标准库不会为 2 向听帧计算**期望特征**（当前 max=1）；
- 轻量库不需要再为 2 向听帧做额外处理；标准/轻量的 12 个期望特征在 2 向听都是 0。

### 4.2 图2：六项期望特征如何使用判别器

局面：東3局 0本場 9巡目 北家，`round_index=2, ev_index=76, seat=1`。

摸牌后 14 张：

```
55789m 34556p 444s 北
```

`Expect` 的 `d0=0`，`keep` 只有一手：**打北**。打完后 13 张：

```
55789m 34556p 444s
```

听 4p / 7p。可见张数：4p 自己 1 张（avail 3，绝对 3）；7p 牌河 1 张（avail 3，绝对 4）；合计 **6 / 7**。

判别器逐张结果：

| 假设 | 判别器入参 | 结果 |
| --- | --- | --- |
| 副露自摸 | `state=FURO, menzen=False, tsumo=True` | 4p/7p 都无役 → None |
| 副露荣和 | `state=FURO, menzen=False, tsumo=False` | 4p/7p 都无役 → None |
| 立直荣和 | `state=RIICHI, menzen=True, riichi=1, tsumo=False` | 立直 + 宝牌 + 赤宝牌 → 5200 |
| 立直自摸 | `state=RIICHI, menzen=True, riichi=1, tsumo=True` | 立直 + 门前清自摸 + 宝牌 + 赤宝牌 → 7900 |
| 默听荣和 | `state=DAMATEN, menzen=True, riichi=0, tsumo=False` | 只有宝牌/赤宝牌，无役 → 0 |
| 默听自摸 | `state=DAMATEN, menzen=True, riichi=0, tsumo=True` | 门前清自摸 + 宝牌 + 赤宝牌 → 4000 |

**结论**：

- 副露 4 项为 0，是因为 `state=FURO, menzen=False` 下这手牌没有副露役，不是「门清所以不算副露」。
- 门清项和非零打点来自同一个判别器，只是 `state/menzen/riichi` 入参不同。
- 因此 d=1 的直接进张不需要 `force_open` 向听：d=0 子节点的 `tp` 已经用正确的假设判过役。

### 4.3 直接进张为什么能嵌入现有枚举

`node()` 只在 `d <= max_shanten` 时展开。`max_shanten=1`，所以：

- d=1：现有进张循环已经对每个 `t` 算了 `dist(newc)`，并生成 `kids`（d=0 子节点）；
- d=0：现有叶子已经算了 `tp`（有役和牌张枚数）；
- d>=2：本来就直接返回 0。

因此：

- d=0：直接进张 = 现有 `tp`；
- d=1：对每个合格 `t`，如果 `kids` 里存在一个子节点在对应假设下 `tp > 0`，就把 `al[t]` / `4 - counts[t] - meldc[t]` 累加；
- d>=2：0；
- 13 张：`_assign_all` 的 `nodes` 只有一个节点，直接取该节点的 `da`；
- 14 张：`nodes` 是 `keep` 的全部节点，6 个 `da` 分别取 max。

**不需要新开一层枚举，不需要额外 `shanten_of`，不需要 `force_open`。**

### 4.4 为什么 `max_shanten` 必须是 1

如果轻量把 `max_shanten` 改成 0：

- d=1 的 `node()` 会直接返回 0，不再生成 `kids`；
- 直接进张失去现成的 d=0 子节点；
- 只能新开一层 34 次向听调用，违反「嵌入现有枚举」的原则；
- 轻量分析反而可能变慢。

所以：**`Expect.max_shanten` 无论轻量还是标准都保持 1。轻量只改 `shanten.CAP 3→2`。** 已在 `expect.py` 的 `DEFAULT_MAX_SHANTEN` 下方加入第 85 轮共识注释；实现时保留，不要删除。`log.md` 第 85 轮也已记录。

## 5. 代码地图（按修改顺序）

### 5.1 `mjscore/shanten.py`

关键：

- `CAP = 3`；
- `cap(need)`；
- `shanten_of(counts, ..., cap=CAP)`；
- `shanten_at(state, seat, cap=CAP)`；
- `mentsu_need(counts, ...)` 内部按 need 枚举，最后由 `cap()` 映射到上限。

改动：

- `cap(need, cap=CAP)`；
- `shanten_of(..., cap=CAP)` 传给 `cap()`；
- `shanten_at(..., cap=CAP)` 传给 `shanten_of()`；
- 标准 cap=3，轻量 cap=2；
- 不改变 `SENTINEL` 语义。

### 5.2 `mjscore/expect.py`

关键函数：

- `Expect.__init__`：`self.max = max_shanten`；
- `Expect.dist`：`shanten.min_shanten(shanten.shanten_of(..., avail=...))`；
- `Expect.node`：
  - `d = self.dist(counts, used)`；
  - `d < 0 or d > self.max` → `_zeros()`；
  - d=0 叶子：`waits`、`got`、`tp` / `tq` / `sc` / `ms`；
  - d>=1：进张循环、`kids`、打牌选择、`tp/tq/sc/ms` 聚合；
- `Expect.compute`：
  - 13-3n：`node(counts)`；
  - 14-3n：先算 `dmin` / `keep`，再 `node(h)`；
  - `_assign_all` 摊到 12 个期望项 + 6 个直接进张项（共 18 项）。
- `_eval`：三种假设的判别器入参。

改动：

- 新增独立的 `ADVANCE_FEATURES` 6 条（现有 `FEATURES` 保持 12 条期望特征，避免 `feats.EXPECT_FEATURES` 重复注册）；
- `ADVANCE_KEYS`；`compute()` 返回 `ADVANCE_KEYS + KEYS` 共 18 项；
- `_zeros()` 加 6 个 `("da", ...)` 键；
- d=0：`da = tp`；
- d=1：进张循环里按 `kids` 的 `tp > 0` 累加；
- `_assign_all()` 里新增 `_assign_advance(feats, nodes)`：13/14 张统一对 6 个 `da` 取 `max(nodes)`（13 张只有一个 node，14 张是 `keep` 列表）；
- `Expect.__init__(..., shanten_cap=3)`；`dist` 用它；
- `values_both` / `values` 透传 `shanten_cap`；
- 注释 `DEFAULT_MAX_SHANTEN` 永远为 1；
- 更新 docstring（12 → 18 项）。

### 5.3 `mjscore/feats.py`

关键：

- `SHANTEN_FEATURES` 3 条；
- `EXPECT_FEATURES` 12 条；
- `DANGER_FEATURES` 2 条；
- `SECOND_FEATURES = SHANTEN + EXPECT + DANGER`；
- `second_class(st, seat, log)`；
- `records_for_round` / `make_record` / `draw_record` / `call_record` / `wait_record`；
- `second_class_pass`（`--tool node` 时 Python 补第二类）。

改动：

- 新增 `ADVANCE_FEATURES` 6 条，数据来自 `expect.ADVANCE_FEATURES`；
- `EXPECT_FEATURES` 继续使用 `expect.FEATURES`（12 条），不要重复注册；
- `SECOND_FEATURES = SHANTEN + ADVANCE + EXPECT + DANGER`；
- `second_class(..., light=False)` 透传 `shanten_at(cap=...)` 和 `expect.values(shanten_cap=...)`；
- `records_for_round(..., light=False)` 及下游透传；
- `second_class_pass(..., light=False)` 透传；
- 更新数量注释。

### 5.4 `mjscore/store.py`

关键：

- `SCHEMA_VERSION`；
- `TABLES` / `_feature_columns_ddl()` 自动从 `feats.FEATURES` 生成；
- `insert_records(..., full=False)`；
- `frame_full`；
- `query` / `query_detail` / `frame_feats`；
- `check_version` / `version_compatible`。

改动：

- schema 12；
- 新增 `get_db_type(conn)`；
- `insert_records` 删除 full 参数，始终写 frame_full；
- `FULL_NOTE` 改成「始终写入原始数据」；
- 错误提示更新；
- 服务端响应加 db_type（可在 server 层加）。

### 5.5 `mjscore/cli.py`

关键：

- `analyze` / `_analyze`；
- `python_records` / `build_records` / `fill_second_class` / `second_class_pass`；
- `list_dbs`；
- `feat_value_text`；
- argparse 的 `--full`。

改动：

- `analyze(..., light=True)`；删除 full；
- 新建库默认 light=True；CLI `--standard` 关闭；
- 扩充读目标库 db_type，强制按目标库类型；
- 写 meta `db_type` / `full="1"`；
- `list_dbs` 返回 db_type；
- `feat_value_text(..., db_type)`；`--values` / 检索输出先读 `store.get_db_type(conn)`；
- `--features` 48；
- 删除 `--full`；
- 透传 light 到 `fill_second_class` / `second_class_pass`。

### 5.6 `mjscore/server.py`

关键 API：

- `/api/analyze`；
- `/api/dbs`；
- `/api/query`；
- `/api/detail`；
- `/api/frame-feats`；
- `/api/features`。

改动：

- analyze 接受 `light`，删除 `full`；
- dbs 返回 `db_type`；
- query/detail/frame-feats 在响应**顶层**返回 `db_type`（不要只塞进 row；前端统一从顶层取）；
- features 自动 48；
- docstring/数量更新。

### 5.7 前端

- `web/js/mjsfeat.js`：重复的 `SECOND_FEATURES` 注册表，必须手动加 6 条；更新 42/17 注释。
- `web/index.html`：
  - 分析页：删 `anFull`，加 `anLight`（默认 checked）；
  - 检索页：DB 下拉显示轻量/标准；34→40、42→48 文案。
- `web/js/app.js`：
  - `doAnalyze` 发 light，不发 full；
  - 扩充自动勾选/禁用；
  - `runQuery` 从响应顶层读 `db_type` 存 `Sc.dbType`；
  - `syncFeatPanel` 从 `/api/detail` / `/api/frame-feats` 顶层读 `db_type` 存 `FeatPanel.dbType`；
  - `fmtFeatValue(key, v, dbType)`；
  - `featHint` 轻量提示；
  - `renderFeatPanel` 40 行；
  - DB 类型状态。
- `web/style.css`：
  - 40 行一屏；先按实施方案的 13px/1.15/1px 试，再微调。

### 5.8 版本/文档

- `mjscore/__init__.py` → 1.6.0；
- `package.json` → 1.6.0；
- `readme.md`：48/23/40、schema 12、轻量库、无 `--full`、v1.6.0；
- `docs/readme-dev.md` 同步；
- `log.md` 第 85 轮记录。

## 6. 实施清单（checkbox）

### 6.1 核心算法

- [ ] `test/expect_test.py` 的 `node_keys()` 36 → 42；「12 个特征」docstring/断言 → 18。
- [ ] 遍历 `expect.KEYS` 的测试改为 `expect.ADVANCE_KEYS + expect.KEYS`；`startswith("furo")` / `sum(f.values())` 断言区分旧 6 项和新 6 项。
- [ ] `shanten.cap` / `shanten_of` / `shanten_at` 支持 `cap` 参数。
- [ ] `Expect` 支持 `shanten_cap`，标准 3、轻量 2。
- [ ] `expect.FEATURES` 加 6 条，顺序在期望听牌之前。
- [ ] `_zeros()` 加 6 个 `da` 键。
- [ ] d=0：`da = tp`。
- [ ] d=1：`kids` 的 `tp > 0` 判定 + 枚数累加。
- [ ] 14 张：`compute()` 对 `da` 取 max。
- [x] `DEFAULT_MAX_SHANTEN` 注释：轻量/标准都保持 1（已在基线加入，保留）。
- [ ] `test/expect_test.py` 新增直接进张 section，全部通过。

### 6.2 注册表/入库

- [ ] `feats.ADVANCE_FEATURES` 6 条。
- [ ] `SECOND_FEATURES` 顺序正确，第二类 23。
- [ ] `second_class(light)` 透传 cap。
- [ ] `records_for_round` / `second_class_pass` 透传 light。
- [ ] `store.SCHEMA_VERSION = 12`。
- [ ] `store.get_db_type`。
- [ ] `insert_records` 始终 full。
- [ ] `FULL_NOTE` 更新。
- [ ] `feature_def` 48。
- [ ] `test/mjscore_test.py` 建库/检索/旧库拒绝通过。

### 6.3 CLI/服务

- [ ] `analyze` 默认 light=True，删除 full。
- [ ] `--standard` 关闭轻量。
- [ ] 扩充自动按目标库类型。
- [ ] meta db_type / full="1"。
- [ ] `list_dbs` 返回 db_type。
- [ ] `feat_value_text` 按 db_type 格式化。
- [ ] `--features` 48。
- [ ] `/api/analyze` 接受 light，删除 full。
- [ ] `/api/dbs` / query / detail / frame-feats 返回 db_type。
- [ ] server 文档字符串更新。

### 6.4 前端

- [ ] `mjsfeat.js` 6 条 + 数量注释。
- [ ] 分析页 `anLight` 默认 checked；删 `anFull`。
- [ ] 扩充自动勾选/禁用。
- [ ] `doAnalyze` payload `{paths, db_name, extend, light}`。
- [ ] DB 下拉显示轻量/标准。
- [ ] `fmtFeatValue` 轻量 2→`>=2`，标准 3→`>=3`。
- [ ] `featHint` 轻量提示。
- [ ] 当前帧特征面板 40 行，无滚动条。
- [ ] `test/apptest.js` / `test/uitest.js` 通过。

### 6.5 版本/文档/构建

- [ ] `__version__ = "1.6.0"`。
- [ ] `package.json` 1.6.0。
- [ ] readme 48/23/40、schema 12、轻量、无 `--full`。
- [ ] `log.md` 第 85 轮。
- [ ] `test/mjscore_test.py` 全量（约 10 分钟）。
- [ ] `test/agari_test.py` / `test/shanten_test.py` / `test/expect_test.py`。
- [ ] `node test/apptest.js` / `selftest.js` / `uitest.js`。
- [ ] 打包/冒烟（按项目惯例）。

## 7. 测试与验收命令

### 7.1 基线（改动前先跑一遍）

```bash
python test/expect_test.py
python test/shanten_test.py
python test/agari_test.py
python test/mjscore_test.py          # 约 10 分钟
node test/apptest.js
node test/selftest.js
node test/uitest.js
```

注意：`test/agari_test.py` 的语料计数断言写死过 71 个 `.tenhou`，当前工作区可能只有 69 个，历史上有 3 项语料基线漂移失败；先记录基线，不要把既有失败当成回归。

### 7.2 本次新增

```bash
python test/expect_test.py           # 直接进张 section
python test/shanten_test.py          # cap=2
python test/mjscore_test.py          # schema 12 / db_type / light 查询
node test/apptest.js                 # 轻量复选框 / 无 --full / 40 行
node test/uitest.js
```

### 7.3 手工/接口探针

1. 新建轻量库：
   - `db_type == "light"`；
   - 3 个向听列最大 2；
   - `frame_full` 有数据；
   - 面板向听 2 显示 `>=2`。
2. 新建标准库：
   - `db_type == "standard"`；
   - 3 个向听列最大 3；
   - 面板 2 显示 `2`、3 显示 `>=3`。
3. 扩充：
   - 选轻量库 → 复选框自动勾选/禁用；
   - 选标准库 → 自动取消/禁用；
   - 切回新建 → 默认勾选。
4. 检索：
   - 轻量库 `面子手向听数 = 2` 有结果；
   - 轻量库 `面子手向听数 = 3` / `>=3` 无结果；
   - 标准库 `= 3` 有结果。
5. 旧库：
   - schema 11 → 拒绝；
   - app_version 1.5.x → 拒绝；
   - 错误提示包含「v1.6.0 / 重新分析」。
6. 面板：
   - 40 行；
   - 在截图窗口（CSS 约 1764×959）和 1920×1080 下 `featPanelList.scrollHeight <= featPanelList.clientHeight`。

## 8. 已知坑 / 绝对不要做

1. **不要改 `max_shanten`。** 轻量/标准都保持 1。轻量只改 `shanten.CAP`。
2. **不要新开直接进张枚举。** d=1 复用 `kids`，d=0 复用 `tp`，14 张复用 `keep`。
3. **`node()` 末尾的 `p` 加权循环必须跳过 `da` 键。** 直接进张是枚数计数，不能乘 `p`；`da` 的元组形状也不是 `(kind, assume, agg, mode, measure)`，不跳过会把 `kk[2]` 当成 `agg` 并算错。
4. **不要给副露加 `force_open` 向听。** d=0 子节点的 `_eval` 已经用 `state=FURO, menzen=False` 判役；d=1 读 `tp > 0` 即可。
5. **14 张不要 sum。** 6 个直接进张分别取 `keep` 节点的 max。
6. **不要按牌种数 +1。** 按剩余张数累加。
7. **不要做 `>=3 -> >=2` 映射。** 轻量库 `3` / `>=3` 就是空结果。
8. **不要做跨库展示。** 只展示当前选中的库。
9. **不要忘记 `mjsfeat.js` 是第二份注册表**，以及 42/17/34 的硬编码。
10. **不要忘记 `--full` 的所有引用**：
   - `cli.py` argparse / `analyze` / `_analyze` / `insert_records`；
   - `server.py` `/api/analyze`；
   - `store.FULL_NOTE` / `meta.full` / `last_batch`；
   - `web/index.html` `anFull` / `anFullHelp` / `anFullNote`；
   - `web/js/app.js` `doAnalyze` / `loadMeta`；
   - readme / docs / tests。
11. **不要忘记 `db_type` 的前端格式化链路**：
    - `/api/dbs` 返回 db_type；
    - query / detail / frame-feats 返回 db_type；
    - `App.dbType` / `Sc.dbType`；
    - `fmtFeatValue(key, v, dbType)`。
12. **不要忘记面板 CSS 实测**；40 行必须无滚动条。

## 9. 复现两个追踪局面的命令

### 9.1 载入示例牌谱

示例文件：

```
data/paipu/naga-new/010b6cc06e02d1346909a3831ca7400dd0399fb91eaa94a613882f87a2839f43v2_2.naga
```

通用加载：

```python
from mjscore import cli, replay, agari, shanten, expect, mjlog

p = 'data/paipu/naga-new/010b6cc06e02d1346909a3831ca7400dd0399fb91eaa94a613882f87a2839f43v2_2.naga'
g = cli.game_from_file(p)

def state_at(ri, evi):
    st = replay.initial_state(g, ri)
    for i, ev in enumerate(g['rounds'][ri]['events']):
        replay.apply_event(st, ev)
        if i == evi:
            break
    return st
```

### 9.2 图1

```python
st = state_at(0, 24)
seat = 0
print(mjlog.names_to_str(st['players'][seat]['hand']))
print(shanten.shanten_at(st, seat))
e = expect.Expect(st, seat)
print(e.dist(e.counts), e.compute()[0])
```

预期：

- 手牌 `2s 3p 4s 8m 3s 7s 6s 3m 6p 3p 3s 4p 8m 3m`；
- shanten `{kokushi:3, chiitoi:2, mentsu:2}`；
- `dist=2`；
- 12 个期望特征全 0。

### 9.3 图2

```python
st = state_at(2, 76)
seat = 1
e = expect.Expect(st, seat)
counts = agari.counts_of(st['players'][seat]['hand'])
print(mjlog.names_to_str(st['players'][seat]['hand']))
print(e.dist(counts), sorted(e.waits(counts)))
print(e.compute()[0])
```

预期：

- 手牌 `7m 4s 4p 6p 5p 5m 5p 4s 4s 8m 3p 北 0m 9m`；
- `dist=0`，waits 4p/7p；
- `menzen_tenpai_expect=6.0`，`menzen_tenpai_abs=7.0`；
- 副露 4 项全 0；
- `riichi_ron_score=5200`，`riichi_tsumo_score≈7900`，`damaten_ron_score=0`，`damaten_tsumo_score≈4000`。

### 9.4 图1 的 mentsu 拆解

如果需要复现 2 向听的拆解，可参考 `shanten.mentsu_need` 的递归：它枚举 `(4-n)` 组面子 + 雀头，优先用手牌，缺的算摸进。图1 的最优拆解是：

```
333m 888m 456p 33p 234s
```

缺 3m / 8m / 5p，弃 3s / 6s / 7s。

## 10. 交接阅读顺序

1. 本文第 3 节（共识）和第 4 节（为什么）。
2. `docs/impl-plan-v1.6.0-advance-features.md` 第 2、4、5 节。
3. `mjscore/expect.py`：
   - `DEFAULT_MAX_SHANTEN` / `MAX_SHANTEN`；
   - `Expect.__init__`；
   - `Expect.dist`；
   - `Expect.node` 的 d=0 / d>=1 分支；
   - `Expect.compute` 的 14 张分支；
   - `_eval` 的三种假设。
4. `mjscore/feats.py` 的 `SECOND_FEATURES` / `second_class` / `records_for_round`。
5. `mjscore/store.py` 的 schema / `insert_records` / `frame_feats` / `query`。
6. `web/js/app.js` 的 `doAnalyze` / `fillExtendSelect` / `fmtFeatValue` / `syncFeatPanel` / `renderFeatPanel`。
7. `web/style.css` 的 `.feat-panel*` / `.feat-row`。
8. 跑第 7.1 的基线测试，再按实施方案第 6 节顺序实现。

## 11. 交接检查清单

- [ ] 已读 `docs/impl-plan-v1.6.0-advance-features.md`。
- [ ] 已读本文第 3、4 节。
- [ ] 已确认 `DEFAULT_MAX_SHANTEN = 1`，并理解为什么轻量也不能改。
- [ ] 已确认直接进张只覆盖 d<=1，d>=2 为 0。
- [ ] 已确认 14 张用 `keep` + max。
- [ ] 已确认副露不需要 `force_open`，d=0 的 `tp` 已经判役。
- [ ] 已确认轻量库只改 3 个向听列，6 个直接进张 + 12 个期望特征两边相同。
- [ ] 已确认只展示当前选中的库，不做跨库。
- [ ] 已确认 `--full` 删除、始终写 `frame_full`。
- [ ] 已确认新建库默认轻量、扩充自动匹配。
- [ ] 已确认面板 40 行无滚动条。
- [ ] 已跑基线测试并记录既有失败。

## 12. 当前没有未决概念问题

本轮讨论已确认：

- 6 条，不是 12 条；
- 不做国士/七対/面子分类；
- 方案 A（d<=1）；
- `keep` + max；
- 枚数不是种类数；
- 副露是假设，立直/默听仅门清；
- 轻量只改 `shanten.CAP`，`max_shanten` 恒为 1；
- 检索按内部值匹配，不做特殊映射；
- 单库展示，不做跨库；
- v1.6.0 / schema 12 / 拒绝旧库；
- 删除 `--full`，始终写原始数据；
- 新建库默认轻量；
- key 使用 `advance`；
- 面板 40 行无滚动条。

实现中如果发现与上述任何一条冲突，先停下来记录到 `log.md`，不要自行改口径。
