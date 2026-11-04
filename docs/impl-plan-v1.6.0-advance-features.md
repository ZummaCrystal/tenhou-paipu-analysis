# v1.6.0 实施方案：第二类「直接进张」6 项 + 轻量数据库

> 状态：**方案已与用户达成共识，尚未实现**。  
> 基线：v1.5.1 / commit `715a6bf` / schema 11 / 42 个特征。  
> 目标：v1.6.0 / schema 12 / 48 个特征（第二类 23 个、可填 40 个）。  
> 交接文档：`docs/handover-v1.6.0-advance-features.md`。

## 1. 目标与范围

### 1.1 本次新增

在第二类特征中新增 **6 条**「直接进张」特征，放在三种向听数之后、六个期望听牌枚数之前：

| # | 中文名 | key | 类型 | 范围 |
| --- | --- | --- | --- | --- |
| 1 | 副露自摸直接进张枚数 | `furo_tsumo_advance_avail` | int | 0..136 |
| 2 | 副露自摸直接进张绝对枚数 | `furo_tsumo_advance_abs` | int | 0..136 |
| 3 | 副露荣和直接进张枚数 | `furo_ron_advance_avail` | int | 0..136 |
| 4 | 副露荣和直接进张绝对枚数 | `furo_ron_advance_abs` | int | 0..136 |
| 5 | 立直/默听直接进张枚数 | `menzen_advance_avail` | int | 0..136 |
| 6 | 立直/默听直接进张绝对枚数 | `menzen_advance_abs` | int | 0..136 |

- 不再按「国士無双 / 七対子 / 面子手」拆分；直接进张沿用现有 `min_shanten()`（三牌型取最小）和现有起和役判别器。
- `advance_avail` = 直接进张枚数（考虑手牌 + 牌面公共信息）。
- `advance_abs` = 直接进张绝对枚数（只考虑自己手牌 + 自己副露，忽略公共信息）。

### 1.2 同时改动

- 新增**轻量数据库**类型：`db_type = "standard" | "light"`。
- 轻量分析只把三种向听数的内部上限从 `3` 改成 `2`（`2` 表示 `>=2`）；其余特征值不变。
- `Expect.max_shanten` **在轻量和标准中都保持 1**，不得改成 0；必须写代码注释并写入 `log.md`。
- 删除 `--full` 参数与界面「同时写入原始数据」复选框；数据库**始终写入原始数据**（`frame_full` 始终填充）。
- 版本升到 **v1.6.0**；schema 升到 **12**；拒绝 v1.5.x / schema 11 的旧库。
- 当前帧特征面板新增 6 行后共 40 行，必须一页显示完、不出现滚动条。

### 1.3 非目标

- 不做「同一帧同时出现在轻量库和标准库时以标准库为准」的跨库展示；本轮只展示当前选中的数据库。
- 不做轻量库的向听检索语义特殊映射：仍按代码内部整数值匹配。
- 不新增国士/七対/面子分类特征。
- 不改现有 6 个期望听牌枚数、6 个期望打点、2 个危险特征的算法。
- 不做旧库迁移；旧库一律拒绝，要求重新分析。

## 2. 已确认口径

### 2.1 直接进张的定义

对当前 13-3n 张手牌（14-3n 张出牌帧先按现有规则打一张，转为 13-3n 张），逐牌种 `t` 检查：

1. 摸入 `t` 后成为 14-3n 张；
2. 存在一张可打的牌，使打完后 13-3n 张手牌的内部向听数等于「当前内部向听数 - 1」；
3. 若满足，把该牌种的**剩余枚数**计入：
   - `advance_avail`：`avail[t] = 4 - 可见张数`（自己手牌 + 四家副露 + 四家牌河（被鸣走的不算） + 宝牌指示牌）；
   - `advance_abs`：`4 - 自己手牌张数[t] - 自己副露张数[t]`。

注意：

- **按剩余张数计，不按牌种数 +1。** 例如某进张牌种还剩 3 张，就计 3。
- 赤 5 与普通 5 同种计数。
- 不考虑振听、立直后固定听牌等限制；与现有期望特征一致。
- 只考虑自摸进张，不考虑鸣牌进张。
- **候选牌种集合沿用现有 `node()` 的进张循环**：`avail[t] == 0` 的牌种不会进入 `advance_abs`（与现有期望特征的路径一致）。`advance_abs` 只是在合格牌种上把枚数从 `avail[t]` 换成 `4 - 自己持有`。如果以后要求绝对口径在判定候选时也完全忽略公共信息，需要另开 shape-only 枚举，不在本轮范围。
- 6 个 `da` 值必须是整数：d=0 时 `int(tp)`，d=1 时累加 `al[t]` / `4 - counts[t] - meldc[t]`；DB 列类型 INTEGER。

### 2.2 向听数覆盖范围

**方案 A（已确认）：直接进张只在 `d ∈ {-1, 0, 1}` 有值，`d >= 2` 一律 0。**

- `d = -1`：0；
- `d = 0`：等于现有对应期望听牌枚数 `tp`（和牌张枚数）；
- `d = 1`：统计摸入后能到 `d = 0` 的牌种；
- `d >= 2`：0。

这与现有 `Expect.max_shanten = 1` 完全一致：`node()` 只在 `d <= 1` 时展开进张，所以直接进张可以完全复用现有枚举，不需要新开一层。

### 2.3 三种假设

| 特征组 | 适用条件 | 判别器入参 | 说明 |
| --- | --- | --- | --- |
| 副露自摸 | 所有帧（门清帧也按副露假设算） | `state=FURO, menzen=False, tsumo=True` | 副露役必须有役 |
| 副露荣和 | 所有帧（门清帧也按副露假设算） | `state=FURO, menzen=False, tsumo=False` | 副露役必须有役 |
| 立直/默听 | 仅当前门清帧 | `state=RIICHI, menzen=True, riichi=self.riichi or 1` | 保证有役；副露帧 2 项记 0 |

- 恒不成立的组合直接记 0（例如副露帧的立直/默听项）。
- 不需要新增 `force_open` 向听模式：副露是否有役由 d=0 子节点的现有 `tp` 已经判定，d=1 时直接读取子节点 `tp > 0` 即可。

### 2.4 14 张出牌帧

1. 沿用现有 `Expect.compute()` 的 `keep`：所有打到**最小整体向听数**的切牌；
2. 对每个 `keep` 后的 13 张手牌调用现有 `node(h)`；
3. 对每个直接进张特征，在 `keep` 的节点中取 **max**：

```python
value = max(node[direct_key] for node in nodes)
```

- 不是 sum；
- 不是「期望打点 argmax 的单手」；
- 六个特征分别取 max（枚数和绝对枚数各自选最大切牌）。

### 2.5 轻量数据库

- `meta.db_type = "standard" | "light"`。
- 轻量分析：`shanten` 内部上限 `CAP = 2`，三种向听数取值 `{-1, 0, 1, 2}`，`2` 对外显示 `>=2`。
- 标准分析：`CAP = 3`，取值 `{-1, 0, 1, 2, 3}`，`3` 对外显示 `>=3`。
- **`Expect.max_shanten` 在两种模式下都保持 1。** 轻量分析只改 `shanten.CAP`，不改期望特征枚举深度。
- 因此：
  - 6 个直接进张特征在轻量/标准库中**完全相同**（只用 d<=1 和 d=0）；
  - 12 个期望特征在轻量/标准库中**完全相同**（2 向听帧本来都是 0）；
  - 唯一差异是 3 个向听列：标准库精确到 2、`3` 表示 `>=3`；轻量库 `2` 表示 `>=2`。
- 新建库默认轻量；扩充时由目标库的 `db_type` 自动决定，界面自动勾选/禁用复选框；类型不匹配时服务端拒绝。
- 检索仍按代码内部值匹配：
  - 轻量库 `2` 命中 `>=2` 桶；
  - 轻量库 `3` / `>=3` / `4` 均返回空；
  - 不做 `>=3 -> >=2` 的特殊映射。
- 展示只使用当前选中的数据库，不做跨库优先。

## 3. 数据模型与 schema

### 3.1 `store.SCHEMA_VERSION`

从 `11` 升到 `12`。

旧库拒绝规则：

- `schema_version != 12` → 拒绝；
- `app_version` 的大/中版本不是 `1.6` → 拒绝（v1.5.x 全部拒绝）；
- 错误提示写清楚「v1.6.0 需要重新分析」。

### 3.2 `frame` 新列

由 `feats.FEATURES` 自动生成，新增：

```
s_furo_tsumo_advance_avail INTEGER
s_furo_tsumo_advance_abs   INTEGER
s_furo_ron_advance_avail   INTEGER
s_furo_ron_advance_abs     INTEGER
s_menzen_advance_avail     INTEGER
s_menzen_advance_abs       INTEGER
```

列顺序 = `SECOND_FEATURES` 顺序：3 个向听 → 6 个直接进张 → 6 个期望听牌 → 6 个期望打点 → 2 个危险。

### 3.3 meta

新增：

- `db_type`：`"standard"` / `"light"`；
- `full`：恒为 `"1"`（`--full` 删除后所有库都写原始数据）。

`store.get_db_type(conn)`：

- 读 `meta.db_type`；
- 缺失时按 `"standard"` 处理（仅用于容错，新库必须写）。

### 3.4 `frame_full`

`insert_records()` 删除 `full` 参数，始终写：

- `tiles`
- `melds`
- `dora`
- `scores`
- `names`

`store.FULL_NOTE` 改成「数据库始终写入原始数据」。

fixture 路径的记录可能没有 `tiles/melds/dora/scores/names`；`insert_records` 仍只写存在的字段，不要因为缺字段报错。正式 analyze 路径的 `make_record` 必须包含这些字段。

### 3.5 `feature_def`

`write_feature_defs()` 自动写入 48 条（7 + 17 + 23 + 1）。

## 4. 算法与代码改造

### 4.1 `mjscore/shanten.py`

1. 保留模块级 `CAP = 3` 作为默认值。
2. `cap(need, cap=CAP)`：允许传入上限。
3. `shanten_of(..., cap=CAP)`：把 cap 传给 `cap()`。
4. `shanten_at(..., cap=CAP)`：把 cap 传给 `shanten_of()`。
5. 不改变 `SENTINEL = CAP + 1` 的现有语义；cap=2 时 need>=3 一律映射到 2。
6. 新增测试：cap=2 时，精确 2 和 3+ 都返回 2；0/1 不变。

### 4.2 `mjscore/expect.py` —— 核心

#### 4.2.1 特征注册

新增**独立**的 `ADVANCE_FEATURES` 列表（6 条）；现有 `FEATURES` 保持 12 条期望特征不变，避免 `feats.EXPECT_FEATURES` 重复注册：

```python
ADVANCE_FEATURES = [
    ("furo_tsumo_advance_avail", "副露自摸直接进张枚数"),
    ("furo_tsumo_advance_abs",   "副露自摸直接进张绝对枚数"),
    ("furo_ron_advance_avail",   "副露荣和直接进张枚数"),
    ("furo_ron_advance_abs",     "副露荣和直接进张绝对枚数"),
    ("menzen_advance_avail",     "立直/默听直接进张枚数"),
    ("menzen_advance_abs",       "立直/默听直接进张绝对枚数"),
]
ADVANCE_KEYS = [k for k, _n in ADVANCE_FEATURES]
```

`Expect.compute()` 的 `feats` 返回 `ADVANCE_KEYS + KEYS` 共 18 项；`alt` 仍只有现有 6 个期望听牌枚数。
初始化改成 `feats = dict((k, 0.0) for k in ADVANCE_KEYS + KEYS)`；`alt = dict((k, 0.0) for k in KEYS)`。
`values()` / `values_both()` 的 docstring 从「12 个」改为「18 个（6 直接进张 + 12 期望特征）」。

#### 4.2.2 节点键

在 `_zeros()` 中新增 6 个直接进张键（不带 `agg`，因为直接进张不区分 sum/best）：

```python
("da", FURO_ASSUME, TSUMO, "avail")
("da", FURO_ASSUME, TSUMO, "abs")
("da", FURO_ASSUME, RON,   "avail")
("da", FURO_ASSUME, RON,   "abs")
("da", MENZEN_ASSUME, "avail")
("da", MENZEN_ASSUME, "abs")
```

#### 4.2.3 `node()` 的 d=0 分支

在现有 `tp` 赋值之后，直接把对应 `tp` 赋给 `da`：

```python
# 副露自摸 / 副露荣和
for mode in (TSUMO, RON):
    for measure in ("avail", "abs"):
        out[("da", FURO_ASSUME, mode, measure)] = \
            out[("tp", FURO_ASSUME, "sum", mode, measure)]

# 门清
for measure in ("avail", "abs"):
    out[("da", MENZEN_ASSUME, measure)] = \
        out[("tp", MENZEN_ASSUME, "sum", measure)]
```

理由：d=0 时 `tp` 就是该假设/模式下的和牌张枚数；直接进张在听牌状态退化为这个值。

#### 4.2.4 `node()` 的 d=1 分支

在现有进张循环中，`kids` 已经生成（d=0 子节点）。对每个合格的 `t`：

```python
for mode in (TSUMO, RON):
    for measure in ("avail", "abs"):
        key_tp = ("tp", FURO_ASSUME, "sum", mode, measure)
        if any(g[key_tp] > 0 for g in kids):
            n = al[t] if measure == "avail" else 4 - counts[t] - self.meldc[t]
            out[("da", FURO_ASSUME, mode, measure)] += n

for measure in ("avail", "abs"):
    key_tp = ("tp", MENZEN_ASSUME, "sum", measure)
    if any(g[key_tp] > 0 for g in kids):
        n = al[t] if measure == "avail" else 4 - counts[t] - self.meldc[t]
        out[("da", MENZEN_ASSUME, measure)] += n
```

要点：

- `kids` 是「摸 t 后、打到最小向听」的那组 d=0 子节点；
- `g[key_tp] > 0` 表示该子节点在该假设下有至少一张有役和牌张；
- 副露假设是否有役由 d=0 子节点的现有 `tp` 判定，**不需要 `force_open`，不需要新的向听调用**；
- 对每个合格 `t`，按剩余枚数累加，不按 `p` 加权；
- `al[t]` 是父节点视角的剩余未见张数；`4 - counts[t] - self.meldc[t]` 是绝对枚数。

**关键坑**：`node()` 末尾有一个按 `p` 加权的循环：

```python
for kk in list(out.keys()):
    if kk[0] == "sc": ...
    elif kk[0] == "ms": ...
    else:
        agg = kk[2]
        ...
```

`da` 键的元组形状不是 `(kind, assume, agg, mode, measure)`，而且**直接进张是枚数计数，不能乘 `p`**。必须在循环开头加：

```python
if kk[0] == "da":
    continue
```

或者把 `else` 分支限制为 `kk[0] in ("tp", "tq")`。否则 `kk[2]` 会被当成 `agg`，直接进张会被概率加权，结果错误。

#### 4.2.5 `node()` 的 d=-1 / d>max 分支

保持现有 `_zeros()` 返回，即所有直接进张 0。

#### 4.2.6 `_assign_all()` / `compute()` 的 13/14 张赋值

在 `_assign_all(feats, alt, nodes)` 内新增一个 `_assign_advance(feats, nodes)`：

```python
def _assign_advance(self, feats, nodes):
    for key in ADVANCE_KEYS:
        feats[key] = max(g[key] for g in nodes) if nodes else 0
```

- 13 张路径：`_assign_all(feats, alt, [self.node(self.counts, used)])`，`nodes` 只有一个节点；
- 14 张路径：`nodes = [self.node(h, used) for h in keep]`，`nodes` 是全部最小向听切牌；
- 因此 13/14 两条路径统一在 `_assign_all` 里处理，不需要在 `compute()` 里单独加分支；
- 6 个直接进张特征分别取 max；
- 不改现有期望特征的 sum/best 逻辑；
- `alt` 只保留现有 6 个期望听牌枚数的另一种聚合口径，不新增直接进张的 alt。

#### 4.2.7 `Expect.max_shanten` 注释（已在基线加入，实现时保留）

`DEFAULT_MAX_SHANTEN = 1` 下方已加入第 85 轮共识注释；实现时不要删除：

```python
# 轻量分析也不改这个值：无论 standard / light，max_shanten 始终为 1。
# 改成 0 会让 d=1 的 node 不再展开，直接进张无法复用 d=0 子节点的 tp，
# 必须另开一层进张枚举，违反「直接进张嵌入现有枚举」的设计。
```

#### 4.2.8 `shanten_cap` 参数

- `Expect.__init__(..., shanten_cap=3)`，固定为实例属性；
- `Expect.dist()` 调用 `shanten.shanten_of(..., cap=self.shanten_cap)`；
- `values_both()` / `values()` 增加 `shanten_cap=3` 参数；
- `feats.second_class(light=True)` 传 `shanten_cap=2`，标准传 3；
- `max_shanten` 仍固定为 1，不提供轻量覆盖。

注意：`Expect.dist` 的缓存键不需要包含 `shanten_cap`，因为 cap 是实例级固定值。

### 4.3 `mjscore/feats.py`

1. 新增 `ADVANCE_FEATURES`：

```python
ADVANCE_FEATURES = [
    {"key": k, "name": n, "col": "s_" + k, "kind": "int", "min": 0, "max": 136}
    for k, n in expect.ADVANCE_FEATURES
]
```

`EXPECT_FEATURES` 继续使用 `expect.FEATURES`（12 条），不要改成 `expect.ADVANCE_FEATURES + expect.FEATURES`，否则会重复注册。

2. 注册表顺序：

```python
SECOND_FEATURES = SHANTEN_FEATURES + ADVANCE_FEATURES + EXPECT_FEATURES + DANGER_FEATURES
```


3. `second_class(st, seat, log=None, light=False)`：

```python
sh = shanten.shanten_at(st, seat, cap=2 if light else 3)
...
out.update(expect.values(st, seat, shanten_cap=2 if light else 3))
```

4. `records_for_round(..., light=False)` / `records_for_game(..., light=False)`：

- 把 light 传到 `make_record` / `second_class`；
- `make_record` 增加 `light` 参数，默认 False；
- `draw_record` / `call_record` / `wait_record` 增加并透传。

5. `second_class_pass(games, ..., light=False)`：

- 透传给 `feats.records_for_round`。

6. 文档字符串数量更新：

- 17 个第二类 → 23 个；
- 42 个特征 → 48 个；
- 可填 34 → 40。

### 4.4 `mjscore/store.py`

1. `SCHEMA_VERSION = 12`，注释写清 v1.6.0 变更。
2. 新增 `get_db_type(conn)`。
3. `insert_records()`：

   - 删除 `full` 参数；
   - 始终写 `frame_full`；
   - 更新文档字符串。

4. `FULL_NOTE` 改写为「数据库始终写入原始数据」。
5. `check_version()` 错误提示更新。
6. `list_dbs()`（在 `cli.py`）返回 `db_type`。
7. `query()` / `query_detail()` / `frame_feats()`：

   - 行的特征读取逻辑不变（48 列自动包含）；
   - 服务端响应中加 `db_type`（可在 server 层加，见 4.6）。

### 4.5 `mjscore/cli.py`

1. `analyze(..., light=True, ...)`：

   - 删除 `full` 参数；
   - 新建库默认 `light=True`；
   - CLI 增加 `--standard`（显式关闭轻量）；不提供 `--light`，因为默认就是轻量。

2. `_analyze(..., light=True, ...)`：

   - 新建库：使用传入的 `light`；
   - 扩充：读取目标库 `db_type`，强制使用目标库类型；若 `--standard` 与目标库类型冲突，加 warning 并忽略；
   - 始终 `full=True` 写库。

3. `python_records` / `build_records` / `fill_second_class` / `second_class_pass`：

   - 透传 `light`。

4. 写 meta：

   ```python
   store.set_meta(conn, "db_type", "light" if light else "standard")
   store.set_meta(conn, "full", "1")
   ```

5. `list_dbs()` 返回 `db_type`。

6. `feat_value_text(key, value, db_type="standard")`：

   ```python
   if key in feats.SHANTEN_KEYS:
       if db_type == "light" and value == 2:
           return ">=2"
       if db_type == "standard" and value == 3:
           return ">=3"
   return str(value)
   ```

7. `--features` 帮助文本 48 个特征。
8. `--full` 从 argparse 删除；所有引用清理。
9. `last_batch` 不再记录 `full` 或恒记 `full=True`。
10. `--values` / 检索结果输出：打开库后先 `db_type = store.get_db_type(conn)`，再调用 `feat_value_text(key, value, db_type)`；否则轻量库的 2 会打印成 2 而不是 >=2。

### 4.6 `mjscore/server.py`

1. `/api/analyze`：

   - 请求体支持 `light`（bool），默认 `True`；
   - 删除 `full`；
   - 文档字符串更新。

2. `/api/dbs`：

   - 每个库返回 `db_type`（`cli.list_dbs()` 已带）。

3. `/api/query` / `/api/detail` / `/api/frame-feats`：

   - 响应**顶层**增加 `"db_type": store.get_db_type(conn)`（不要只塞进 row，前端统一从响应顶层取）；
   - 便于前端格式化 `2 -> >=2`。

4. `/api/features`：

   - 自动返回 48 个特征；
   - `second_features` 23 个；
   - 文档字符串更新。

5. 进度：

   - `PROGRESS` 不再有 full 相关字段（当前只有 extend，无需大改）；
   - 前端不再发送 full。

### 4.7 前端

#### 4.7.1 `web/js/mjsfeat.js`

1. `SECOND_FEATURES` 增加 6 条，顺序在 3 个向听之后、6 个期望听牌之前。
2. 更新注释：42 → 48，17 → 23。
3. `FEATURES` 自动 concat，无需改结构。

#### 4.7.2 `web/index.html`

1. 牌谱分析：

   - 删除「同时写入原始数据（--full）」复选框与说明；
   - 新增「开启轻量分析」复选框，默认 `checked`；
   - 说明文案：
     > 轻量数据库：三种向听数的内部上限从 `>=3` 改为 `>=2`（内部值 `2` 表示 `>=2`）；其余特征与标准库相同。新建库默认勾选；扩充时由目标库自动决定。

2. 牌谱检索：

   - 数据库下拉显示 `（轻量）` / `（标准）`；
   - 说明文字 34 → 40 个可填特征；
   - 42 → 48 个特征。

3. 当前帧特征面板：无需改 HTML 结构，只改 CSS（见下）。

#### 4.7.3 `web/js/app.js`

1. 分析状态：

   - 删除 `anFull` 引用；
   - 新增 `anLight`；
   - `doAnalyze()` 发送 `{paths, db_name, extend, light}`；
   - 新建模式：`anLight.checked = true; anLight.disabled = false`；
   - 扩充模式：选中库后 `anLight.checked = db.db_type === 'light'; anLight.disabled = true`；
   - 切换回新建模式：`disabled = false; checked = true`。

2. 数据库列表/下拉：

   - 显示 `轻量` / `标准`；
   - `App.dbType` / `Sc.dbType` 保存当前库类型。

3. 检索：

   - `runQuery()` 的响应里读 `d.db_type`，设置 `Sc.dbType`；
   - `syncFeatPanel()` 的 `/api/detail` / `/api/frame-feats` 响应里读 `d.db_type`，设置 `FeatPanel.dbType`；
   - `renderFeatPanel()` 用 `FeatPanel.dbType || Sc.dbType || 'standard'`；
   - `fmtFeatValue(key, v, dbType)`：
     - `dbType === 'light'` 且 `key` 是向听数且 `v === 2` → `>=2`；
     - `dbType === 'standard'` 且 `v === 3` → `>=3`；
     - 其它照旧。
   - `featHint(f)`：
     - 轻量库向听数：`整数 / 区间 -1-2 / 列表 -1,0,1,2 / 比较；内部值 2 = >=2，3 及以上不存在（按整数匹配）`；
     - 标准库保持现有提示。
   - `renderFeatPanel()` 调用 `fmtFeatValue(f.key, value, row.db_type || Sc.dbType)`。

4. 当前帧特征面板：

   - 40 行（17 第一类 + 23 第二类）；
   - 不出现滚动条；先做一版，再按截图微调。

5. 删除 `loadMeta()` 中 `anFullNote` 的赋值；如 API 仍返回 `full_note`，忽略。

#### 4.7.4 `web/style.css`

目标：40 行在截图窗口（CSS 约 1764×959）和 1920×1080 下一屏显示完，无滚动条。

先做一版：

```css
.feat-row {
  font-size: 13px;
  line-height: 1.15;
  padding: 1px 11px 1px 8px;
}
.feat-panel-head {
  flex-basis: 112px;
  height: 112px;
}
.feat-panel-head .muted {
  font-size: 12px;
  line-height: 16px;
  max-height: 72px;
}
.feat-panel-mode {
  font-size: 22px;
  padding: 6px 5px;
}
```

如果仍溢出，继续减小字号/行距/标题区高度；如果空间剩余过多，再适度放大。验收标准是**无滚动条**，不是固定字号。

### 4.8 版本与文档

1. `mjscore/__init__.py`：`__version__ = "1.6.0"`。
2. `package.json`：`"version": "1.6.0"`。
3. `readme.md`：

   - 42 → 48 个特征；
   - 17 → 23 个第二类；
   - 34 → 40 个可填；
   - schema 11 → 12；
   - 删除 `--full` 说明，改为「始终写入原始数据」；
   - 新增「轻量分析 / 轻量数据库」章节；
   - 新增 v1.6.0 发布说明。

4. `docs/readme-dev.md`：同步数量、schema、轻量库、`--full` 删除。
5. `log.md`：新增「第 85 轮 / v1.6.0」章节，记录：
   - 6 条特征的口径；
   - 直接进张嵌入 `node()` 的实现；
   - **`Expect.max_shanten` 在轻量/标准都保持 1 的原因**；
   - 图1 / 图2 的追踪结论；
   - 测试与基准结果。

## 5. 测试计划

### 5.1 直接进张单元测试（`test/expect_test.py` 新增 section）

0. **先改既有断言**：
   - `node_keys()` 从 36 个键改为 42 个（36 + 6 个 `da`）；
   - 「12 个特征」相关 docstring/断言改为 18 个；
   - 所有遍历 `expect.KEYS` 的测试改为 `expect.ADVANCE_KEYS + expect.KEYS`（或分别遍历）；
   - 所有 `startswith("furo")` / `sum(f.values())` 断言要区分旧 6 项和新 6 项，避免把新 `furo_*_advance_*` 算进旧断言。
1. **d=0 退化**：对若干听牌帧，6 个直接进张特征 == 对应 `tp`。
2. **d=1 独立对拍**：

   - 对每个牌种 t：
     - 若 `counts[t] >= 4` 或 `avail[t] <= 0`，跳过；
     - 摸入 t，逐个试打，若存在 `dist(h) == 0`；
     - 且该 d=0 子节点在对应假设下有 `tp > 0`；
     - 则计入 `avail[t]` 或 `4 - counts[t] - meldc[t]`。
   - 与 `node()` 的 6 个 `da` 键逐项比较。

3. **d>=2 为 0**：随机/语料中的 2 向听、3 向听帧。
4. **d=-1 为 0**：已和牌 14 张帧。
5. **14 张帧**：

   - 独立枚举 `keep`，对每个 `node(h)` 取 max；
   - 与 `compute()` 的 6 项比较。

6. **枚数不是种类数**：

   - 构造一个进张牌种还剩 3 张的手牌，断言值为 3 而不是 1。

7. **furo/menzen 口径**：

   - 用图2 的帧：
     - 副露 4 项 = 0；
     - 门清 2 项 = 6 / 7；
     - 打点 5200 / 7900 / 0 / 4000。

8. **绝对 >= 期望**：6 项均满足 `advance_abs >= advance_avail`。
9. **红 5**：赤 5 与普通 5 同种计数。

### 5.2 向听 cap 测试（`test/shanten_test.py`）

- `cap=2`：
  - 精确 0/1 不变；
  - 精确 2 → 2；
  - 3+ → 2；
- `cap=3` 保持现有行为。

### 5.3 轻量库测试（`test/mjscore_test.py`）

- 新建轻量库：`meta.db_type == "light"`；
- 新建标准库：`meta.db_type == "standard"`；
- 扩充轻量库时传入 `light=False` → 自动按轻量执行或拒绝（按实现选择，推荐自动按目标库类型并 warning）；
- schema 11 旧库拒绝；
- v1.5.x 旧库拒绝；
- 轻量库 3 个向听列最大值为 2；
- 检索 `2` 命中；`3` / `>=3` 返回 0；
- 标准库 `2` 只命中恰好 2；`3` 命中 `>=3`；
- `frame_full` 始终有数据（`--full` 删除后）。

### 5.4 前端测试（`test/apptest.js` / `test/uitest.js`）

- 分析页有「开启轻量分析」且默认勾选；
- 没有 `--full` 复选框；
- 扩充选择轻量库时复选框自动勾选并禁用；切回新建时恢复默认勾选；
- 检索数据库下拉显示轻量/标准；
- `fmtFeatValue` 轻量 2 → `>=2`，标准 3 → `>=3`；
- 特征面板 40 行；
- 无滚动条（手动/浏览器验证；如测试环境能读布局，加断言 `scrollHeight <= clientHeight`）；
- 分析 API payload 含 `light`、不含 `full`。

### 5.5 性能基准

在 50~200 个代表性帧上测：

- `shanten_at` cap 3 vs cap 2；
- 标准 vs 轻量整批分析耗时；
- 6 个直接进张特征的额外耗时（应接近 0，因为复用现有 `node()`）。

将结果写入 `log.md`。如果轻量模式比标准模式慢，必须排查是否误开了新枚举或改错了 `max_shanten`。

## 6. 实施顺序

1. `shanten.py` cap 参数 + 测试。
2. `expect.py` 6 个直接进张 + 测试（先不接 DB/UI）。
3. `feats.py` 注册表 + `light` 透传 + 测试。
4. `store.py` schema 12 + `db_type` + 始终 full + 测试。
5. `cli.py` / `server.py` 参数与响应 + 测试。
6. 前端注册表 / 分析选项 / 检索显示 / 面板 CSS + 测试。
7. 版本、readme、log、构建、人工验收。

## 7. 验收标准

- [ ] 48 个特征：7 第零类 + 17 第一类 + 23 第二类 + 1 第三类。
- [ ] 第二类 23 个 = 3 向听 + 6 直接进张 + 6 期望听牌 + 6 期望打点 + 2 危险。
- [ ] 6 个直接进张全部通过独立参考对拍。
- [ ] d=0 时 6 个直接进张 == 对应 `tp`。
- [ ] d>=2 时 6 个直接进张 == 0。
- [ ] 14 张帧取 `keep` 的 max，不是 sum。
- [ ] 枚数按剩余张数计。
- [ ] 轻量/标准库的 6 个直接进张 + 12 个期望特征完全相同。
- [ ] 轻量库只有 3 个向听列不同：`2` = `>=2`。
- [ ] 轻量库检索 `3` / `>=3` 返回空；`2` 命中 `>=2`。
- [ ] 新建库默认轻量；扩充自动匹配类型；类型不匹配拒绝。
- [ ] 数据库始终写 `frame_full`。
- [ ] schema 12；v1.5.x / schema 11 旧库拒绝。
- [ ] 当前帧特征面板 40 行一屏显示，无滚动条。
- [ ] `Expect.max_shanten` 在轻量/标准都保持 1，并有代码注释 + log 记录。
- [ ] 全部相关测试通过；性能基准记录在 log。

## 8. 风险与注意事项

1. **不要改 `max_shanten`。** 轻量分析只改 `shanten.CAP`。`max_shanten=0` 会让 d=1 的 `node()` 不再展开，直接进张无法复用 `kids`，只能另开枚举，违反设计。
2. **不要新开进张枚举。** d=1 直接用现有 `kids` 的 `tp`；d=0 直接用现有 `tp`；14 张直接用现有 `keep` 节点。
3. **不要用 `tq` 单独判空听。** 用 `tp > 0` 判「该子节点在该假设下有至少一张有役和牌张」；`tq` 只表示「有役听牌」的归一化分母，d=0 时可能为 1 但 `tp=0`（理论上不应出现，但用 `tp` 更直接）。
4. **不要给副露加 `force_open` 向听。** d=0 子节点的 `_eval` 已经用 `state=FURO, menzen=False` 判役；d=1 只需读 `tp`。
5. **14 张不要 sum。** 直接进张是「选一手最大的切牌」，用 max。
6. **不要做跨库展示。** 当前只展示选中的库。
7. **不要做 `>=3 -> >=2` 映射。** 轻量库按内部整数匹配，`3` 就是无结果。
8. **不要忘记 `mjsfeat.js` 的重复注册表**，以及 42/17/34 等硬编码。
9. **不要忘记 `--full` 的所有引用**：CLI、UI、API、store、readme、tests、`FULL_NOTE`、`last_batch`。
10. **不要忘记面板 CSS 的实测**；40 行在目标窗口必须无滚动条。
