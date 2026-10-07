# 开发日志（log.md）

> 记录每一轮开发的重要结论与产物，供后续开发参考。

## 0. 项目最终目标
实现立直麻将（天凤）牌谱分析软件：
1. 下载用户指定的天凤牌谱 URL 到本地；
2. 分析每局、每巡目下每一家的手牌与牌河特征；
3. 将特征存入数据库，支持按指定「手牌 / 牌河特征」快速检索出：牌谱 url、局、巡目、玩家。

## 1. 开发环境（硬约束）
- 项目根目录（所有文件操作必须用**绝对路径**，禁止 `.`、禁止相对路径）：
  `D:\coding\dsh_workspace\simple\tenhou-paipu-analysis`
- Python 解释器（Anaconda 环境，禁止使用/修改系统原生 python）：
  `D:\coding\anaconda3\envs\py314_null\python.exe`（Python 3.14.7）
- 编码：`readme.md` / `log.md` / `tenhou-url.txt` 均为 UTF-8（`tenhou-url.txt` 可能带 BOM）。PowerShell 控制台如需正确显示中文，先执行
  `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8`；
  从 Python 输出非 ASCII 时设 `$env:PYTHONIOENCODING="utf-8"`。

## 2. 第 1 轮：天凤牌谱下载脚本
### 2.1 交付物
| 路径 | 说明 |
| --- | --- |
| `download_tenhou.py` | 牌谱下载脚本（项目根目录，仅用标准库） |
| `data/` | 下载的牌谱文件目录（含 5 个测试牌谱） |
| `references/mjlog2mjai_parse.py` | 第三方参考实现（仅作 mjlog 格式参考，非运行时代码） |

### 2.2 功能与用法
```
python download_tenhou.py <url1> <url2> ...        # 传入若干 URL / 特征码
python download_tenhou.py --url-file tenhou-url.txt
python download_tenhou.py                          # 无参数时默认读取 tenhou-url.txt
# 可选：-o/--output-dir <dir>（默认 data/）、--no-overwrite
```
- 输入可为多种形态，脚本自动识别并提取特征码（log id）：
  1. 完整日报 URL：`http://tenhou.net/0/?log=<log_id>&tw=<seat>`
  2. 原始牌谱 URL：`http://tenhou.net/0/log/?<log_id>`
  3. 裸特征码：`<log_id>`
- 多 URL：按输入顺序逐个**独立**下载，自动去重；单个失败不影响其它；任一失败则退出码为 1。
- 输出文件命名为 `<log_id>.xml`，保存到 `data/`（`--no-overwrite` 时已存在文件跳过）。
- 成功/跳过示例输出：`  -> saved <name> (<n> bytes)` / `  = skipped (already exists) <name>`。

### 2.3 关键技术结论
- **特征码（log id）格式正则**：`^\d{10}gm-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{8}$`
  例：`2026082919gm-00a9-0000-4e40cd3e`。
- **原始牌谱下载端点**：`http://tenhou.net/0/log/?<log_id>`，返回 mjlog XML（根 `<mjloggm ver="2.3">`）。
- 该端点默认返回**明文 XML**；若请求头带 `Accept-Encoding: gzip` 则返回 **gzip**（magic `1f 8b`）。脚本两种都兼容（检测 magic 后 `gzip.decompress`）。
- **HTTPS 不可用**：`https://tenhou.net/...` 在本机因证书问题失败
  （`URLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate`），故统一走 **HTTP**。
- 脚本已实现 3 次重试、超时（默认 30s）、User-Agent header。

### 2.4 测试结果（`tenhou-url.txt` 中 5 条真实 URL）
| # | log_id | 文件大小(字节) |
| --- | --- | --- |
| 1 | `2026082919gm-00a9-0000-4e40cd3e` | 16408 |
| 2 | `2026082920gm-00a9-0000-5db954e6` | 17700 |
| 3 | `2026082921gm-00a9-0000-d2e544e6` | 15739 |
| 4 | `2026083020gm-00a9-0000-e9ce1efe` | 13272 |
| 5 | `2026083021gm-00a9-0000-d0810acf` | 21290 |

- 首轮：`Done: 5 succeeded, 0 failed.`（exit 0），5 个文件均为合法 mjlog（首 `<mjloggm ver="2.3">`、尾 `</mjloggm>`）。
- 幂等：再跑 `--no-overwrite`，5 条全部 `skipped (already exists)`。
- 输入形态回归：完整 URL / 原始 URL / 裸特征码 均下载成功。
- 异常回归：`http://tenhou.net/0/?log=not-a-log-id` → `x cannot extract a Tenhou log id from: ...`、`Done: 0 succeeded, 1 failed`、exit=1（优雅失败）。
- BOM 回归：`--url-file` 读取带 UTF-8 BOM 的文件正常（已用 `utf-8-sig`）。

## 3. mjlog 牌谱格式笔记（解析层 `js/mjlog.js` 已实现，供分析阶段复用）
### 3.1 结构
- UTF-8 XML，通常**无换行**，根节点 `<mjloggm ver="2.3">`。
- 大量「字母+数字」短标签（摸牌/打牌），其余为具名标签：`INIT / REACH / AGARI / RYUUKYOKU / DORA / SHUFFLE / GO / UN / TAIKYOKU / N`。

### 3.2 牌 id 编码（整数 0-135）
- `kind = id // 4`（0-33）；`suit = kind // 9`（0=万, 1=筒, 2=索, 3=字）；`rank = kind % 9 + 1`。
- 种类表（索引 0-33）：`1m..9m 1p..9p 1s..9s E S W N P(白) F(發) C(中)`。
- **赤宝牌（红 5）**：`id % 4 == 0` 且 `kind % 9 == 4`（即 5m/5p/5s），记作 `5mr / 5pr / 5sr`。

### 3.3 摸牌 / 打牌标签
- 摸牌 `T/U/V/W` + 数字 → 玩家 0/1/2/3：`player = ord(tag[0]) - ord('T')`。
- 打牌 `D/E/F/G` + 数字 → 玩家 0/1/2/3：`player = ord(tag[0]) - ord('D')`。
- 即 T/D=玩家0、U/E=玩家1、V/F=玩家2、W/G=玩家3（每组第一个字母=摸牌、第二个=打牌）。
- 玩家索引为**绝对座次，与庄家无关**（已验证：`oya=0` 局以 `<T..>` 起手，`oya=1` 局以 `<U..>` 起手）。

### 3.4 鸣牌 `<N who="X" m="M" />`
- `rel = M & 0x3`；被鸣者绝对座次 `callee = (X + rel) % 4`。
- 类型位标志：
  - `M & (1<<2)` → 吃 Chi（顺子）
  - `M & (1<<3)` → 碰 Pon（刻子）
  - `M & (1<<4)` → 加杠 KaKan
  - `M & (1<<5)` → 拔北 Nuki（三麻）
  - 否则 → 杠（`rel == 0` 为暗杠 AnKan，否则大明杠 MinKan）
- 顺子解码：
```
t = (M & 0xfc00) >> 10; r = t % 3; t = t // 3
t = 9 * (t // 7) + (t % 7); t *= 4
h = [t + ((M & 0x0018) >> 3), t + 4 + ((M & 0x0060) >> 5), t + 8 + ((M & 0x0180) >> 7)]
if r == 1: h = [h[1], h[0], h[2]]
elif r == 2: h = [h[2], h[0], h[1]]
```
- 刻子解码：
```
unused = (M & 0x0060) >> 5; t = (M & 0xfe00) >> 9
r = t % 3; t = (t // 3) * 4; h = [t, t, t]
# unused 属于 {0,1,2,3} → 依次给 h 加 (1,2,3)/(0,2,3)/(0,1,3)/(0,1,2)
# 再按 r==1/2 做与顺子相同的重排
```
- 杠解码：`hai0 = (M & 0xff00) >> 8`；暗杠时 `hai0 = (hai0 & ~3) + 3`；其余同上；明杠返回 `[hai0] + h`，暗杠返回 `h[:2]`。
- 已验证示例：
  - `<N who="1" m="42025"/>` → 玩家1 碰东（来自玩家2），`[E,E,E]`
  - `<N who="1" m="11431"/>` → 玩家1 吃 4m5m6m（来自玩家0）
  - `<N who="1" m="55463"/>` → 吃 5s(赤)6s7s
  - `<N who="0" m="32768"/>` → 玩家0 暗杠 發

### 3.5 其它标签
- `<INIT seed="a,b,c,d,e,f" ten=".." oya="K" hai0..3=".."/>`：
  `seed[0]`=局序号、`seed[1]`=本场(combo)、`seed[2]`=供託、`seed[3:5]`=骰子、`seed[5]`=ドラ表示牌；
  `ten`×100 = 各家分数；`oya`=庄家座次；`haiN`=各家起手 13 张（十进制 id，逗号分隔）。
- `<TAIKYOKU oya=".."/>` 对局开始；`<SHUFFLE seed=".."/>`；
- `<DORA hai=".."/>` 杠后新ドラ；
- `<REACH who step [ten]>` 立直宣告（step 1/2）；
- `<AGARI ba hai machi ten yaku doraHai doraHaiUra who fromWho sc>` 和了；
- `<RYUUKYOKU ba sc [type] [hai0..3]>` 流局；
- `<GO>` 对局配置（含红宝牌 / 三麻 flag）；`<UN>` 玩家名/dan/rate/sex。

## 4. 第 2 轮：前端界面（牌谱播放 + 检索入口）

> readme 要求：先做**简洁前端界面**，含「牌谱播放」与「牌谱检索」两项；检索**只保留入口不实现**。
> 播放：浏览选择本地牌谱文件 → 进入播放界面；**不做动画**，但要用按钮控制 出牌/吃/碰/杠/和 按顺序发生或回退。
> 本阶段不使用 python（第 1 轮下载脚本除外）；素材与实现语言参考 `D:\coding\PycharmProjects\killer_mortal_gui-master`。

### 4.1 交付物（文件清单）

| 文件 | 职责 |
| --- | --- |
| `index.html` | 单页三视图骨架：首页 / 播放 / 检索占位 |
| `style.css` | 暗绿主题；3×3 牌桌网格、牌 CSS 变量、立直/摸切/被鸣/和了牌样式、响应式 |
| `js\tiles.js` | 牌 id(0–135) → 短名 / SVG 路径 / 中文标签；`sortHand`、`countsByKind`；**赤 5 判定的唯一出处** |
| `js\mjlog.js` | mjlog XML → 结构化对局；**不用 DOMParser**（正则分词），node 与浏览器都能跑；含全部鸣牌解码 |
| `js\replay.js` | 回放状态机：一局事件流 → **逐帧状态**（手牌/牌河/副露/点数/供托/宝牌/结果） |
| `js\ui.js` | 纯渲染层 `renderBoard / renderCenter / renderPlayer / renderEventList`；不含状态 |
| `js\app.js` | 交互与状态：视图切换、文件载入、步进/跳转、键盘、自动播放、自适应缩放 |
| `media\tiles\*.svg` | 40 个牌面素材（0m–9m / 0p–9p / 0s–9s / 1z–7z / back / Front / Blank） |
| `test\selftest.js` | 解析 + 回放的**不变量**离线自检（node） |
| `test\uitest.js` | 渲染层自检：假 DOM 重跑 `renderBoard`，校验图片存在与渲染张数守恒 |
| `test\apptest.js` | 交互集成 + 展示规则回归自检（7b 牌桌结构 / 7d 牌河分行 / 7f 样式规则 / 7g 副露 / 7h 流局帧；现 754 行） |

- 脚本按 `tiles → mjlog → replay → ui → app` 以**经典 `<script>`** 引入（非 ES module），因此 `file://` 双击 `index.html` 也能直接用（module 会被 CORS 拦）。

### 4.2 界面与交互（要点）

- **首页**：`浏览本地文件…`（`<input type=file>` + FileReader，直接读本地 xml）、拖拽区、`载入示例牌谱`（走 `fetch`，**需要 HTTP server**，启动命令：`& 'D:\coding\anaconda3\envs\py314_null\python.exe' -m http.server 8000 --directory D:\coding\dsh_workspace\simple\tenhou-paipu-analysis`，浏览器开 `http://localhost:8000/`）、`进入牌谱检索` 入口。
- **播放页**：3×3 牌桌（下=自家，右/上/左=下家/对家/上家）+ 中央信息区（局/本番/供托/牌山余枚/ドラ表示牌/四家点数/结果框）+ 右侧事件列表（可点击跳帧）+ 底部控制条。
- **控制按钮（9 个）**：`上一局` `开局` `上一关键` `上一步` `下一步` `下一关键` `本局结束` `自动播放` `下一局`。关键帧 = 出牌 / 鸣牌 / 立直 / 新ドラ / 和了 / 流局；无动画前提下用**逐帧步进 + 关键帧跳转**实现「按顺序发生或回退」。
- **键盘**：`←/→` 上一步/下一步，`↑/↓` 上一/下一关键帧，`Home/End` 本局首/末帧，`PageUp/PageDown` 上/下一局；焦点在 INPUT/SELECT/TEXTAREA 时不响应，方向键 `preventDefault`。
- **选项**：`隐藏他家手牌`（第 3 轮起改为控制条按钮 `#btnOthers`）、`显示事件列表`。
- **检索视图**：全部 disabled 的占位表单 + 「依赖后续分析与入库」说明，符合「只保留入口」。
- 牌面表现：摸到的牌单独显示在 `.drawn`；摸切（tsumogiri）半透明；被鸣走的牌红框（最新规则见 5.3/5.8）；副露带「吃/碰/加杠/大明杠/暗杠/拔北」标签。（旧版会从牌河移走被鸣牌并标 `.from-river`，第 5 轮起已废弃。）

### 4.3 关键技术结论（mjlog 解析 / 回放）

1. **`yaku` 是 (役id, 翻数) 成对**：`yaku="1,1,0,1,7,1,54,2,53,0"` → `nestPairs` → `[[1,1],[0,1],[7,1],[54,2],[53,0]]`；渲染役名必须按对渲染 `役名(翻数)`，否则翻数会被当成役 id。
2. **`ten` = `[符, 点数, 是否自摸]`**：`[20,8000,1]`（自摸）/ `[30,1000,0]`（荣和）。
3. **鸣牌取牌必须按「牌 id 精确匹配」**：先弹出被鸣者牌河末张并记住它的 **id**，再对副露的牌逐张 `indexOf(id)` 精确移除（跳过 `calledId` 那张），找不到才退回按 kind 删。按 kind 猜会造成「副露与手牌残留同 id 牌重复」（实测 11 处）。修好后 5 个牌谱 **117 次鸣牌零警告**，说明 `decodeChi/Pon/Kan/Kakan` 算出的 id 与真实牌河牌 id 完全一致。
4. **不变量**：① `手牌数 + Σ副露牌数 ∈ {13+K, 14+K}`（K = 4 张的副露数，暗杠/加杠/大明杠各 +1；+1 = 刚摸牌未打牌）；② 每局 `Σ四家点数 + 供托×1000` 恒定（和了时供托清零，流局时保留）；③ 牌 id 全局唯一、每 kind ≤ 4。
5. **标签判定顺序陷阱**：具名标签 `GO/UN/TAIKYOKU/SHUFFLE/INIT/N/REACH/DORA/AGARI/RYUUKYOKU` 必须**先于**单字母摸打标签 `T/U/V/W`、`D/E/F/G` 判定，否则 `TAIKYOKU` 会被当成 T（摸牌）。
6. 供后续分析阶段复用：`MJLOG.parse(text)` → `{meta, rounds:[{init, events}]}`；`REPLAY.buildGame(game)` / `buildFrames(game, i)` → 逐帧状态。两者都能在 node 下 `require`，特征提取**不需要另写解析器**。

### 4.4 测试与限制

- 全量自检：`selftest` **5 牌谱 / 58 局 / 5824 帧**（摸 2701 / 打 2776 / 鸣 117 / 立直 104 / 新ドラ 10 / 和了 51 / 流局 7）+ 全部不变量通过；`uitest` 每谱 38 种素材 0 缺失；`apptest` 全流程断言通过。
- `test\out\timeline_<牌谱名>.txt`（5 个）＝ 逐事件对账底稿（每局 INIT + 逐帧状态快照 + 终局手牌）。
- 限制：检索未实现（依赖后续入库）；役 id → 役名只覆盖天凤常见 0–54 号（冷门役显示「役#id」）；无动画（自动播放 = 500ms 定时逐帧）；自动化用假 DOM，**CSS 观感必须靠真实浏览器确认**。

## 5. 第 3 轮起：牌桌展示规则的逐轮改造（按用户实测反馈）

> 每小节 = 一轮用户反馈（消息号标注）→ 需求 → 改动 → 结论。**当前有效规则** = 5.1~5.7 的叠加结果（5.8 的改动已回滚）。

### 5.1 牌桌版面改造（m00281）

需求：① 增加显示/隐藏他家手牌按钮；② 左右两侧与对面的**手牌、牌河整体旋转**，牌河靠中心、6 张一排、预留 4 排；③ 中央只保留 局数/供托/剩余牌数/宝牌指示牌；④ 风位与点数按截图方向展示（同样旋转）。
层次（从外到内）：**手牌在最外圈 → 牌河居中靠内 → 「风位+点数」抬头最靠中心**。

- 方案：**整块面板旋转**（不是逐张牌旋转）—— 四家面板都按自家视角排版（DOM 自上而下固定 `抬头 → 牌河 → 副露 → 手牌`），外层 `.p-rot` 整体 `rotate`，则牌面朝向、点数文字朝向、牌河生长方向同时自动正确，且不会因宽高互换而拉伸。
- 座位映射 `SEAT_ROT = { 0:'r0', 1:'r270', 2:'r180', 3:'r90' }`：自家 `.cell-bottom/r0`、下家 `.cell-right/r270`、对面 `.cell-top/r180`、上家 `.cell-left/r90`；`RIVER_COLS = 6`、`RIVER_ROWS = 4`。
- `js\ui.js`：`riverEl(river)` 每 6 张一个 `.river-row`；`renderPlayer()` 内固定顺序 `.p-head → .p-river → .p-melds → .p-hand`；`renderCenter()` 的 `.center` 含 `.c-round / .c-honba / .c-kyotaku（+ .stick 供托小方条）/ .c-left（xN）/ .c-dora / .c-result`，**删掉** `.c-scores`。
- `index.html`：删 `#chkHideOthers` 复选框，控制条加 `<button data-act="others" id="btnOthers">隐藏他家手牌</button>`；`js\app.js` 新增 `syncOthers()`（按钮 `.on` 高亮 + 文案在「隐藏/显示他家手牌」间切换）。
- 遗留：截图中央「中 + 5 个深色方块」的含义未确证，当前按「宝牌指示牌（正面）+ 供托小方条」渲染。

### 5.2 牌河生长方向 + 自适应缩放（m00340，浏览器实测反馈）

需求：① 牌河第 1 排应贴中央信息框、第 2 排起向外（手牌方向）延伸；② 高分屏比例失衡、留白过大，要求手牌/牌河/中央紧凑，且不同分辨率观感一致。

- ① 根因：`.p-river` 当时是 `column-reverse`，而 `.p-rot` 的 DOM 顺序是 `p-head → p-river → p-hand`（手牌最外圈）⇒「第 1 排」被推到靠手牌一侧。改 `.p-river { flex-direction: column; }`：DOM 第 1 排落在容器顶部＝贴中央信息框，后续排朝手牌方向生长。
- ② `.board` 去掉 `1fr` 弹性轨道，改成**完全以牌宽为单位**：`grid-template-columns: calc(var(--tile-w) * 9.5) calc(var(--tile-w) * 8.6) calc(var(--tile-w) * 9.5)`、`grid-template-rows: auto auto auto`、`gap: calc(var(--tile-w) * .45)`、`flex: 0 0 auto`、`overflow: visible`；areas = `"top top top"` / `"left center right"` / `"bottom bottom bottom"`。新增 `.cell-left, .cell-right { height: calc(var(--tile-h) * 4.6); }`（面板旋转 90° 后的实际占位；`≤1100px` 复位 `height: auto`）。写死的 px 全改 calc（`.tile.big`、`.c-dora .tile`、`.p-head` 字号/padding）。
- **单一缩放单位**：`--tile-w`（`--tile-h = u * 4/3`，牌面比例 3:4）。
- `index.html`：`#board` 外包 `<div id="boardBox" class="board-box">`（`.board-box { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; min-width: 0; min-height: 0; overflow: auto; }`）作为量测基准与居中容器。
- `js\app.js` 的 `fitBoard()`（`BASE_U = 30` / `MIN_U = 9` / `MAX_U = 34`）：按基准值量自然尺寸 → `k = min((w-4)/bw, (h-4)/bh)` → `u = clamp(u*k)`，**迭代 3 次**（`|k-1| < .01` 提前退出）；`setTileUnit(u)` 写 `--tile-w/--tile-h`（带 `if (st && st.setProperty)` 守卫，假 DOM 下安全返回）。调用点：切到 replay 视图、载入牌谱后、事件列表勾选变化、`window.resize`。

### 5.3 鸣牌 / 横放 / 和了 展示规则（m00397，共 8 条）

| # | 规则（现状） |
| --- | --- |
| ① | 自摸时中央显示「X家 自摸和了」（X = 风位） |
| ② | 荣和显示「X家 放铳 Y家」 |
| ③ | 和了帧即使勾选「隐藏他家手牌」也临时摊开，下一局恢复用户选项 |
| ④ | 副露放在手牌右侧（自家视角），先鸣的靠右、后鸣的依次向左延伸 |
| ⑤ | 被鸣走的牌**不从别家牌河移除**，改用**红框**标记（与表示摸切的透明度区分）※ 后来试探过加透明度，已回滚，见 5.8 |
| ⑥ | 吃/碰/大明杠用横放牌的位置表示来源；加杠第 4 张卡在原横牌上；暗杠 1、4 张反扣 |
| ⑦ | 立直宣言牌只横放、不加方框或文字 |
| ⑧ | 横放统一为从竖放位置**逆时针转 90°**、下侧边缘对齐 |

- `js\replay.js` 的 `applyCall`：不再 `river.pop()`，改为给被鸣者牌河末张打 `called` 标记 + `calledId`（该牌与副露里那张是**同一张实体牌**，故不变量口径改为「牌河（被鸣走的除外）」）。
- `js\ui.js`：`MELD_ROT = { 3: 0, 2: 1, 1: 2 }`（rel：3=上家/2=対面/1=下家）+ `rotIndexOf(m, list, seat)`（吃 → `list.indexOf(m.calledId)`；碰/杠按 `rel = (m.from - seat + 4) % 4` 查表；暗杠/拔北 → -1）；`meldEl()` 盒子类名 `meld meld-<callType>`，暗杠首末张 `back: true`，加杠 `list = m.tiles.slice(1)` 且 rot 位置放 `.tile-stack`；`renderPlayer()` 的副露按 `for (mi = pl.melds.length - 1; mi >= 0; mi--)` **倒序**插入（先鸣的在最右）；`resultEl(ev, st)` 按 `(seat - oya + 4) % 4` 取风位。
- `style.css`：`.p-bottom`（手牌 + 副露同一行、底对齐）、`.tile.rot`（`translateY((--tile-h − --tile-w)/2) rotate(-90deg)`，左右各留 `(--tile-h − --tile-w)/2` 的 margin）、`.tile-stack`；`.tile.called` 红框；**删除** `.tile.riichi`（「立」字标记）与 `.tile.from-river`。
- 当时的分歧：用户说「吃：放的位置代表牌的来源」，但实测 50 次吃**只可能吃上家**（rel 恒为 3），按来源则永远是第 1 张、没有信息量 ⇒ 当时按通行规则实现（第 6 轮按 m00483 纠正，见 5.4）。
- 测试：`test\apptest.js` 7b 改为断言 `p-head > p-river > p-bottom` 且 `.p-bottom` 首个子节点是 `p-hand`；7f 加样式回归；新增 **7g 段**（用 `UI.renderBoard` 直渲指定帧：四种副露的摆放/张数/横放张数、被鸣牌仍留在牌河、立直宣言牌横放、和了中央标题、和了时强制摊牌）。

### 5.4 吃 / 大明杠 / 副露排列 修正（m00483）

用户实测后纠正三点（逐字要点：①「这里的摆放顺序应当是 7p（横）6p（竖）8p（竖），因为 7p 来自我们，也就是鸣牌家的上家…所以吃牌的副露，一定是第一张横放」；②「你必须使用不同的方式来处理大明杠…来自上家横放第一张、来自对家横放第二张、来自下家横放第四张…大明杠的情况未做测试」；③「从下家碰了 7p，应该…将三张 7p 的位置插在手牌与三张东的中间，而不是和东放在同一列」）：

1. **吃**：被吃的那张**恒摆第 1 张（横放）**，另两张按点数升序跟在后面 —— 例：下家用 6p8p 吃我们的 7p → `7p(横) 6p(竖) 8p(竖)`。理由：吃只可能吃上家，第 1 张就等于来源，「被吃的是顺子里的第几张」是多余信息。代码：`rotIndexOf()` 对 `chi` 直接 `return 0`；`meldEl()` 里 `list = [calledId].concat(其余两张升序)`。
2. **大明杠**：改用用户指定规则 —— **上家 = 第 1 张、対面 = 第 2 张、下家 = 第 4 张**（即永不横放第 3 张），与碰（共 3 张：上家 1 / 対面 2 / 下家 3）**不是同一张表**。代码：`KAN_ROT = { 3: 0, 2: 1, 1: 3 }`，`var tbl = (m.callType === 'daiminkan') ? KAN_ROT : MELD_ROT;`（`js\replay.js` 里大明杠的 callType 就是 `'daiminkan'`，不是 `'kan'`）。⚠ **大明杠无真实样本**（5 牌谱里 吃 50 / 碰 45 / 加杠 4 / 暗杠 5、大明杠 0），只在 apptest 里对映射表做了单测。
3. **副露被挤到同一列**：根因是 `.p-bottom` 与 `.p-melds` 都允许 `flex-shrink` / `flex-wrap`，副露一多就被压缩换行（面板旋转 90°/270° 后看着像「新鸣的那组和先鸣的放在同一列」）。改：`.p-bottom { flex-wrap: nowrap }` + `.p-bottom > * { flex: 0 0 auto }` + `.p-melds { flex-wrap: nowrap }` ⇒ 副露沿「手牌 → 更外侧」一条线依次排开，新鸣的紧挨手牌。

- 测试 7g 同步更新（吃：第 1 张 = 被吃的那张且横放、后两张升序；新增「大明杠/碰 来源→横放位置」与「暗杠/拔北 不横放」单测）+ 「同一家两组以上副露」的 DOM 顺序断言（DOM 顺序 = 状态副露顺序的倒序）。

### 5.5 和了帧细化（m00569）

1. **荣和：铳牌不进和了者手牌** —— `js\replay.js` 的 `case 'agari'` 不再 `dp.river.pop()`，改成取放铳者牌河最后一张打 `e2.win = true`；`js\ui.js` 的 `riverEl` 给它加 `.win`（绿色 `--accent` 框）。同时删掉「用 mjlog 的 `hai` 覆盖和了者手牌」那两行（和了帧沿用上一帧摆法，mjlog 权威手牌仍在 `st.result.hand`）。
2. **自摸：摸牌不插进手牌** —— `drawn` 的 `st.phase === 'playing'` 守卫去掉，和了帧继续把摸牌单摆在手牌末端（13 张 + 摸牌 1 张）。
3. **显示/隐藏是特例**：`st.reveal`（座位号数组，当时叫 `st.winners`，随 `cloneState` 复制）累加每个 agari 事件的和了者；和了帧 `hidden = (reveal.indexOf(seat) < 0)`，即摊开和了者、隐藏其余三家（含自家），与「隐藏他家手牌」按钮无关，新一局恢复用户选项。一炮双响 / 三响靠「mjlog 每个 `<AGARI>` 一个事件、逐帧累加」支持（无样本，未实测）。
4. **副露任何时候都不隐藏**：`hidden` 只作用于手牌区与摸牌；apptest 用「副露区牌背数 = 暗杠数 × 2」看住这一点。
5. **中央用词**：`parseAgari` 的 `doraHai` / `doraHaiUra` 是**指示牌**，标签由「ドラ / 裏ドラ」改为「宝牌指示牌 / 里宝指示牌」；役表 52/53/54 由「ドラ / 裏ドラ / 赤ドラ」改为「宝牌 / 里宝牌 / 赤宝牌」。
6. apptest 新增 `agariSpec(frame, tag)`（荣和 / 自摸各一个样本，7 项断言）；注意 7d 末帧 bottom 牌河由 14 张变 15 张（`[6,6,3]`），因为铳牌不再被移出牌河。

### 5.6 流局帧展示 + 中央信息顺序 + 红绿框加粗（m00636）

1. **显示/隐藏机制与和了帧统一**：`st.reveal`（座位号数组）= 本帧摊开手牌的名单，名单外一律隐藏（**含自家**，与「隐藏他家手牌」按钮无关），下一局自动恢复；`hidden` 只作用于手牌区，副露任何时候不隐藏。
2. **名单按流局种类算**（`js\replay.js` 的 `case 'ryuukyoku'`）：荒牌流局 = mjlog 里带 `haiN` 属性的座位（= 听牌家，实测 7 次流局全部如此）；流局満貫（`type="nm"`）= 点数为正的満貫者（视为和牌，只摊开他们，不论是否听牌）；九種九牌（yao9）= 宣告者 `who`（缺失时退化为「最后摸牌的那家」）；四家立直（reach4）= 四家全摊开；四風連打（kaze4）/ 四槓散了（rck4）= 空名单；三家和了（tripleRon，见 5.7）= 除放铳家外三家。
3. **踩坑**：`gain > 0` **不能**当作「流局満貫者」—— 荒牌流局的听牌家同样会 +1000 / +1500（实测 `2026082920gm-00a9-0000-5db954e6.xml` 南3局 `sc="300,10,409,-30,51,10,220,10"`）；现 `ev.nagashi` 只在 `reason === 'nm'` 时填。
4. **中央文字**：荒牌流局 → 第 1 行「荒牌流局」+ 第 2 行「東家 南家 西家 流局听牌」（按 東→南→西→北 排序）；流局満貫 → 「荒牌流局」+「西家 流局満貫」；途中流局 → 「流局」+ 流局名（九種九牌 / 四風連打 / 四家立直 / 四槓散了 / 三家和了）。流局名统一用 `js\mjlog.js` 新增的 `REASON_NAME`（旧的 kaze4→「四家立直」等错误映射已修）。
5. **中央信息栏顺序**：本場 → 供托 → 剩余牌数（`renderCenter` 里把供托块移到剩余牌数之前）。
6. **红框 / 绿框加粗**：`.tile.called` / `.tile.win` 改成外圈 `calc(var(--tile-w) * .17)` + 牌面内嵌 `inset 0 0 0 calc(var(--tile-w) * .11)` 两道，宽度随 `--tile-w` 缩放（自适应后小牌上也明显，不再是写死的 2px）。
7. 测试：`test\apptest.js` 新增 **7h 段**（22 条断言）—— 中央顺序（DOM `c-round > c-honba > c-kyotaku > c-left > c-dora`）、荒牌流局帧（名单 = mjlog 听牌家、牌背数 = 未听牌者手牌 + 暗杠×2、听牌家手牌无牌背、中央两行文字），以及用构造事件直接跑引擎的 7 种流局方式（`''` / `nm` / `yao9` / `reach4` / `kaze4` / `rck4` / `tripleRon`）的名单与中央文字；7f 加两条「框加粗且随牌宽缩放」。
8. 数据限制：5 牌谱的 7 次流局**全是荒牌流局**，流局満貫 / 九種九牌 / 四家立直 / 四風連打 / 四槓散了 / 三家和了**无真实样本**（只有构造事件单测）；大明杠同样 0 样本。

### 5.7 三家和了展示（m00739）

- 规则：三家和了帧摊开**三家荣和者**、隐藏**放铳家**（与和了帧同一套显示/隐藏机制）；中央仍写「流局」+「三家和了」。
- 代码：`js\replay.js` 的 `case 'ryuukyoku'` 把 `tripleRon` 从「空名单」拆出来单独分支 —— `st.reveal = (rkDeclarer >= 0) ? [0, 1, 2, 3].filter(function (s) { return s !== rkDeclarer; }) : [];`，其中 `rkDeclarer` = mjlog 的 `who`，缺失时退化为「最后摸牌 / 打牌的那家」。
- 测试：7h 里两个样本（`who` 缺失 → reveal `[0,1,3]`；`who=1` → `[0,2,3]`），中央都显示「流局三家和了」。
- 限制：无真实样本，mjlog 的 `who` 是否就是放铳家**未做数据验证**。

### 5.8 被鸣牌加透明度（m00761）→ 已按 m00815 回滚

- 需求（m00761）：「下家的 6m 被对家吃，没有提高透明度，检查该 bug 产生的原因，另外检查立直宣言牌被鸣牌时，透明度是否正确设置」。
- 根因：`js\ui.js` 的 `riverEl` 类名本来就对（`tsumogiri` / `rot` / `called` / `win`），问题在 CSS —— 只有 `.tile.tsumogiri { opacity: .5 }`（摸切变淡），`.tile.called` 只有红框、**没有透明度**；而截图里那张 6m 是**手切**（不是摸切），所以整张牌不透明，只剩红框。
- 全量数据（5 牌谱 58 局末帧）：被鸣牌 **107 张** —— 摸切被鸣 **38 张**（`tsumogiri called`，有透明度）/ 手切被鸣 **69 张**（只有 `called`）/ 立直宣言牌被鸣 **1 张**（`2026083021gm-00a9-0000-d0810acf.xml` 南1局 P0 第 13 张 6z = `rot called`，横放本身是对的）。
- 曾改动：`.tile.called { opacity: 1; background: rgba(243,246,244,.5); box-shadow: … }` + 新增 `.tile.called > img { opacity: .5; }`（牌面淡、红框保持饱和；`opacity: 1` 抵消 `.tile.tsumogiri`，让两种被鸣观感统一）；apptest 加 7f 4 条 + **7i 数据回归段**（扫 5 牌谱末帧，按 river 下标核对类名，实测 107 / 38 / 1）。
- **已回滚（m00815，用户逐字：「改完后的展示效果不如之前，回滚最后一次改动」）**：`style.css` 与 `test\apptest.js` 全部还原（7f 恢复原文案、7i 整段删除，apptest 回到 754 行），复跑 `apptest` 全部通过、`selftest` `[OK] 全部不变量通过`。
- **现状与遗留**：手切被鸣（69/107）在牌河里只有红框、没有透明度；立直宣言牌被鸣同理。用户尚未给替代方案（可考虑的更轻做法：整张牌连红框一起 `opacity: .5`，或只把红框调暗一档）。

## 6. 第 12 轮：mjscore 特征打点 + SQLite 入库 + 本地服务 + 前端「牌谱分析 / 牌谱检索」

本轮目标（readme.md，m00001）：对给定本地牌谱里的**每一个非自摸的摸牌帧**，站在**摸牌者本人**视角
标注 16 个「第一类特征」，写入数据库，并能按用户指定的部分特征（AND）检索出所有满足条件的帧；
前端「牌谱分析 / 牌谱检索」两个入口接上，检索结果点进可视化时**必须**能拿到可复制的
「牌谱特征码+局况+本场+巡目+风位」。

### 6.1 交付物（文件清单）

- Python 包 `mjscore\`：
  - `mjlog.py`：mjlog XML → dict（与 `js\mjlog.js` 逐字段对齐；`paipu_url` / `log_id_of` / `joukyoku_label`）。
  - `replay.py`：逐帧状态机（`initial_state/apply_event/iter_events/count_tiles/check_invariants`）。
  - `feats.py`：16 个第一类特征的打点（`FEATURES/extract/draw_record/records_for_round/row_label`）。
  - `store.py`：SQLite 建表/写库/条件编译/检索（`SCHEMA_VERSION=1`、`compile_query`、`query`、`query_detail`、`list_feature_values`、`export_json`）。
  - `nodeharness.py` + `node_harness.js`：调 node 侧打点（`--records/--frames/--summary/--invariants/--out`）。
  - `cli.py`：argparse 入口（`analyze/run_query/resolve_inputs/capture/list_dbs/main`）。
  - `server.py`：stdlib HTTP 服务（静态托管 + JSON API）。
- 根目录入口脚本：`analyze.py`（命令行打点入库）、`server.py`（启动本地服务）。
- 前端新增 `js\mjsfeat.js`（浏览器侧第一类特征，与 `mjscore/feats.py` 同口径，静态帧特征串由它拼）。
- 前端改造：`index.html`（新增「牌谱分析」tab 与视图；检索视图重写；帧内新增 `#frameKey`；脚本顺序加 `mjsfeat.js`）、
  `js\app.js`（本地服务 API 客户端 + 分析/检索/条目导航/复制特征串）、`style.css`（新样式）、
  `js\mjlog.js`（`joukyokuLabel` 泛化到东/南/西/北）、`js\replay.js`（玩家 `draws` 巡目计数）。
- 测试：`test\mjscore_test.py`（新增，88 项）。

### 6.2 解析口径（与 `js` 侧完全对齐）

- 帧下标：`frames[0]` = 开局（未处理任何事件），`frames[k]` = 处理完第 k-1 个事件
  ⇒ **事件下标 i 的帧下标 = i+1**；入库 `ev_index`（事件）与 `frame_index`（帧），前端跳帧直接用 `frame_index`。
- 立直顺序（实测）：`<REACH step="1">` 在**立直宣言打牌之前**，`<REACH step="2" ten="…">` 在打牌之后
  ⇒ 打点帧上的「自家立直状态」只含**已成立**的立直，不含本巡刚宣告的那张。
- **非自摸摸牌帧** = 摸牌事件帧，且**下一事件不是**「`winner == fromWho == 摸牌者` 的 `agari`」。
- 样本数据：5 个牌谱 / 58 局 / 5766 事件帧 / 摸牌帧 2701（其中自摸和了 22）⇒ **打点 2679 行**。
- ⚠ **第 13 轮已修订本节口径**：打点主体加入副露后出牌帧（+107）⇒ **2786 行**；巡目改为按出牌计（`draws` → `turns`）；
  `SCHEMA_VERSION` 1 → 2（frame 表加 `kind`）。6.2~6.7 里出现的「2679 行 / `SCHEMA_VERSION=1` / `draws` 巡目」均以此为准，详见第 7 节。

### 6.3 16 个第一类特征（口径写进 DB `meta.doukou`，也写在 `mjscore/feats.py` 头部）

| # | 特征 | 取值 |
|---|------|------|
| 1 | 局况 | 東一局…北四局 |
| 2 | 是否南三局及以后 | 是 / 否（`round >= 6`） |
| 3 | 巡目 | 正整数（**该家本局第 N 次出牌，含本次**；暗杠/加杠也算一次出牌） |
| 4 | 供托 | 整百非负整数（**立直棒×1000 + 本场×300**） |
| 5 | 自家 | 亲家 / 子家 |
| 6 | 顺位 | 1/2/3/4（按当前分数降序，同分按自风 東→南→西→北 排先） |
| 7-9 | 自家立直状态 / 自家副露状态 / 自家副露数量 | 是·否 / 是·否 / 0-4 |
| 10-13 | 立直家（他家）数量 / 副露家（他家）数量 / 两副露以上（他家）数量 / 三副露以上（他家）数量 | 0-3 |
| 14-16 | 亲家（他家）立直状态 / 亲家（他家）副露状态 / 亲家（他家）副露数量 | 摸牌者本人是亲家时记 否 / 否 / 0 |

- 副露 = 吃 / 碰 / 加杠 / 大明杠 / 暗杠 的**组数**（拔北不计；牌河里被鸣牌只算一次）。

### 6.4 数据库与检索

- 表：`meta` / `feature_def` / `source` / `round` / **`frame`（一行 = 一个非自摸的摸牌帧）** / `frame_full`（`--full` 时存该帧原始数据，便于以后重算新特征）。
- `frame` 列 = 定位列（`log_id/url/round_index/frame_index/ev_index/seat/round/honba/kyotaku_raw/score/oya/joukyoku/wind/junme/dealer/rank/kyotaku_total/drawn/hand_size`）+ 16 个 `f_*` 特征列 + `label` + `log_path` + `tool` + `added_at`；唯一索引 `(log_id, round_index, ev_index, seat)`。
- 条目名 `label` = **牌谱特征码 + 局况 + 本场 + 巡目 + 风位**，例：
  `2026083021gm-00a9-0000-d0810acf 東三局 0本場 3巡目 西家`
  （Python `feats.row_label` 与 JS `MJSFEAT.rowLabel` 同格式；前端静态帧原样显示，`#frameKey` 一键复制）。
- 条件语法：整数 `3` / 区间 `1-3` / 列表 `1,2,3` / 比较 `>=3`（`>`、`<`、`<=`、`!=` 同理）；条件行 `特征名=条件`（`:`、`==` 等价 `=`），多条 **AND**。
- 命令行例：
  - `python analyze.py data --tool node --db data\db\paipu.sqlite`（node 打点；`--tool python` 走纯 Python，`--full` 额外存原始帧）
  - `python analyze.py --query --db data\db\paipu.sqlite`（stdin 逐行「特征名=条件」）
  - `python analyze.py --list-dbs` / `--features` / `--values 巡目` / `--capture data\fixtures`
- 检索结果字段含 `idx`（行号）、`log_id`、`frame_index`、`label`、`log_path`（前端据此跳帧 + 拉原文）。

### 6.5 本地服务（`python server.py` → http://127.0.0.1:8770/）

- 静态文件与 API **同源**：`SimpleHTTPRequestHandler(directory=项目根)` ⇒ 直接用浏览器打开 `http://127.0.0.1:8770/` 即可；
  若双击 `index.html`（file://）也能用 —— 前端会改请求 `http://127.0.0.1:8770`，服务端已开 CORS `*`。
- GET：`/api/health`、`/api/features`（16 特征 + 口径）、`/api/dbs`、`/api/scan?dir=`（递归找 `*.xml`）、`/api/read?path=`（返回原文，≤16MB）。
- POST：`/api/analyze`（`paths` 可为文件或目录 + `db_name`/`db` + `tool` + `full`）、`/api/query`（`conds` 或 `lines`）、
  `/api/browse`（**`limit<=0` = 不限行数**，供「全部浏览」）、`/api/detail`、`/api/round-frames`、`/api/delete-db`。
- 错误：坏条件 / 坏路径 / 不存在的库 → 400 `{"ok":false,"error":…}`；未知 `/api/*` → 404。

### 6.6 前端交互

- **牌谱分析**：选数据源目录 → 扫描（递归）→ 勾选牌谱（可全选/全不选）→ 选打点工具（auto/node/python）+ 是否 `--full`
  → 填库名 → 分析入库 → 下方列出已有的库（名称 / 行数 / 工具 / 大小），可「设为当前库」或删除。
- **牌谱检索**：先选定本地数据库 → 「牌谱特征」框**初始为空**，从下拉逐条添加特征（**已添加的不再出现在下拉里**，不能重复）
  → 每条填检索条件（不填会被拦下）→ 全部填好才可点检索 → 结果条目名 = 特征串 → 点条目跳到对应帧
  （**不改成摸牌家主视角**，用既有可视化）。
- **全部浏览**：直接进阅图模式（`limit=0` 一次取全库），用「上一条目 / 下一条目」在不同条目间切换；
  工具栏 `#itemInfo` 显示「条目 i / N（检索结果 | 全部浏览）」，到头/到尾时对应按钮禁用。
- 两种查看方式下，棋盘上方都有一条 `#frameKey` 状态条显示**可复制的**「牌谱特征码+局况+本场+巡目+风位」；
  从检索条目进入时直接取该条目的 `label`（保证与检索结果逐字一致），手动播放时则从当前帧向前回溯到最近的摸牌帧算出同格式的串。

### 6.7 测试结果（全绿）

- `test\mjscore_test.py`（新增）**88 项全部通过**：解析 58 局 / 5766 帧 / 0 条牌张不变量错误；打点 2679 行且 2679 行逐行口径抽查 0 违规；
  表结构与字段；条件语法与错误提示；**node 与 python 打点 38 列 × 2679 行逐项 0 差异**（readme 要求的交叉校验）；`frame_full` 13395 行一致；
  server 的 GET/POST 路由与错误码（含「检索不存在的库不会顺手建库」）。
- `test\selftest.js` = `[OK] 全部不变量通过`；`test\apptest.js` = `全部通过`（新增第 8 节 42 条：分析视图扫码/勾选提交、检索视图 16 特征/重复拦截/空条件拦截/结果条目/跳帧、
  「全部浏览」`limit=0`、跨牌谱走 `/api/read`、上/下条目禁用、坏条件与服务未启动的可读提示）；
  `test\uitest.js` = `全部通过`。
- 真实进程冒烟：`python server.py --port 8781` → `/`、`/style.css`、`/js/mjsfeat.js`、`/api/health|features|dbs` 全 200。

## 7. 第 13 轮：数据库主体扩展（副露后出牌帧）+ 巡目改按出牌计

用户要求（m00367）：

1. 打点主体除「非自摸摸牌帧」外，**再加入「副露后出牌前的那一帧」**：吃/碰 = 摆出副露牌后等待出牌的那一帧；
   加杠/大明杠/暗杠 = 杠完摸牌后等待出牌的那一帧（这一帧本身就是杠后的岭上摸牌帧，`kind='draw'`，不另建帧）。
2. 巡目改**以出牌为准**：打牌 +1；**暗杠/加杠 +1**（视为出了一次牌）；**吃/碰/大明杠 +0**，摸牌本身 +0。

等价模型（实现即按此）：每家 `turns = 打牌次数 + 暗杠/加杠次数`；任何「该家即将出牌」的帧（draw 帧 / 吃碰副露帧）`junme = turns + 1`。

### 7.1 口径与数据（实测）

- 新增帧 = 吃/碰 `call` 事件之后的等待出牌帧，记 `kind = "chi" | "pon"`、`drawn = NULL`；摸牌帧记 `kind = "draw"`。
- 样本：吃/碰副露帧 **107**（chi 50 + pon 57）+ 非自摸摸牌帧 2679 ⇒ **打点 2786 行**；各牌谱 364/530/531/576/785。
- 鸣牌 117 次分布：chi 50 / pon 57 / ankan 6 / kakan 4 / **daiminkan 0 / nuki 0**
  （大明杠、拔北无真实样本，靠口径 + 构造用例验证）。
- 「按摸牌计」与「按出牌计」巡目不同的摸牌帧 = **437** 行
  （例：`2026082919gm-00a9-0000-4e40cd3e` 東一局 ev38 旧 4 → 新 6）。

### 7.2 代码改动（Python 与 JS 双侧同步）

- `mjscore\replay.py` / `js\replay.js`：玩家字段 `draws` → `turns`；`draw` 事件不再 +1，`discard` 事件 +1；
  `apply_call` 末尾 `if ct in ("ankan", "kakan"): turns += 1`。
- `mjscore\feats.py` / `js\mjsfeat.js`：拆出 `make_record(game, round_index, ev_index, st, seat, kind, drawn)`，
  `draw_record` / `call_record` 包装；记录新增 `kind`；`junme = me["turns"] + 1`；
  `records_for_round` 收 `call` 且 `callType ∈ {chi, pon}` 的事件；`FACT_COLS` 加 `("kind", "TEXT")`。
- `mjscore\store.py`：`SCHEMA_VERSION` **1 → 2**；frame 表加 `kind TEXT`；`FRAME_FACT_COLS` / `RESULT_COLS` 末加 `kind`；
  新增 `check_version(conn, db_path)` 并在 `connect()` 内调用 —— 用 v1 旧库检索会得到可读错误（exit=1）：
  `数据库结构版本 1 ≠ 当前 2（第 13 轮新增 kind 列、巡目改为按出牌计），请删除后重新分析：python analyze.py <牌谱路径> --delete-db <库名>（<绝对路径>）`
- `mjscore\cli.py`：分析结果多报 `rows_draw` / `rows_call`，打印「本次打点 N 行（摸牌帧 X + 副露帧 Y）」。
- `js\app.js`：`frameKeyText()` 支持副露帧（当前帧不是摸牌帧时，回看上一事件是否 chi/pon call 取该家）；
  条目导航 `#itemInfo` 追加「｜ 摸牌帧 / 吃后帧 / 碰后帧」。

### 7.3 验证结果（全绿）

- node↔python 交叉校验：41 列 / 双方 2786 行 / **字段 0 差异**；kind 分布双方皆 `draw 2679 / chi 50 / pon 57`。
- `test\mjscore_test.py` **109 项全部通过**（新增 2b 节：独立重算 `junme` 2808 条 0 不符、逐事件 turns 增量 0 违规、
  构造用例「大明杠 +0 / 暗杠 +1 / 加杠 +1」、旧库结构版本守卫）。
- `test\apptest.js` **218 项全部通过**（第 8 节新增 8.8：`kind='pon'` 条目检索 → 点击 → 帧特征串与条目名逐字一致、`#itemInfo` 显示「碰后帧」）。
- `test\selftest.js` = `[OK] 全部不变量通过`（帧/不变量统计不变：5 牌谱 / 58 局 / 5824 帧 / discards 2776 / calls 117）；
  `test\uitest.js` = 全部通过。
- 规范库重建：`python analyze.py <root>\data --tool node --full` → `data\db\paipu.sqlite`（2498560 B，2786 行 = 摸牌帧 2679 + 副露帧 107，230ms）；
  检索冒烟 `巡目=3 且 供托>=1000 且 自家立直状态=是` → 1 行（`idx 2167`，行内已含 `kind`）。

## 8. 第 14 轮：检索条件的输入方式（互斥取值改下拉）+ 特征 15 显示名修正

用户要求（m00603，附截图 m00602）：

1. 特征 15 的显示名 **「亲家（他家）副露」→「亲家（他家）副露状态」**（避免与 16「亲家（他家）副露数量」混淆）。
2. 「牌谱检索」里**取值互斥的 7 个特征**（局况 / 是否南三局及以后 / 自家 / 自家立直状态 / 自家副露状态 /
   亲家（他家）立直状态 / 亲家（他家）副露状态）的条件输入由自由文本改为**下拉选取**；
   其余 9 个数值特征仍用文本框（整数 / 区间 `1-3` / 列表 `1,2,3` / 比较 `>=3`）。

### 8.1 实现

- 取值本来就在两张注册表里（`mjscore/feats.py` 的 FEATURES `kind/values`、`js/mjsfeat.js` 的 FEATURES 同构），
  本轮只是**把前端渲染接上**：`js/app.js` 新增 `featIsEnum(f)`；`renderConds()` 里
  enum → `<select class="cond-ctl cond-select">`（第一项是占位 `<option value="">请选择</option>`，再逐个 `f.values`），
  int → `<input class="cond-ctl cond-input" placeholder=featHint(f)>`；`collectConds()` 改查 `.cond-ctl`（input / select 通用）。
- 文案：没选 / 没填分别提示「条件还没选择。」/「条件还没填写。」；`index.html` 检索说明改成
  「每条特征都要指定条件（**互斥取值的特征用下拉选取**，数值特征填整数 / 区间 / 列表 / 比较）」；`style.css` 加 `.cond-select`。
- `js/mjsfeat.js` 与 `mjscore/feats.py`（含头部文档表）、`log.md` 6.3 表同步改名。
- 规范库 `data\db\paipu.sqlite` 用 `python analyze.py <root>\data --tool node --full` 重建（`feature_def.name` 才会跟着改），
  重建后 2786 行 / schema v2 / 230ms。

### 8.2 验证结果（全绿）

- `test\mjscore_test.py` **119 项全部通过**（8.2/8.3 共新增 8 项：`/api/features` 的 7 个 enum 都带非空 `values`；
  `feats.BY_KEY["oya_meld"]["name"]` 已改名）。
- `test\apptest.js` **228 项全部通过**（新增 8.9 节：选 `oya_meld` → 渲染出 `SELECT` 且 3 项 = 占位 + 是/否、
  首项值为空、行名含「副露状态」、没选被拦下且提示「还没选择」、选「是」后 `/api/query` 的
  `conds = [{"key":"oya_meld","expr":"是"}]`、整数特征仍是 `INPUT` 文本框）。
- `test\selftest.js` = `[OK] 全部不变量通过`；`test\uitest.js` = 全部通过；
  `py_compile` 全部 `.py` / `node --check` 全部 `.js` exit=0。

### 8.3 顺手修掉的两个缺陷（重分析留下孤儿 `frame_full` / `--delete-db` 退出码）

复核规范库时发现 `data\db\paipu.sqlite` 里 `frame_full` 比预期大一倍（27860 行、5572 个 `frame_idx`，
而 `frame` 只有 2786 行且 `idx` 从 2787 起）——根因是**重分析同一批牌谱**：

- `frame` 有唯一索引 `frame_uniq ON frame (log_id, round_index, ev_index, seat)`，`INSERT OR REPLACE` 会
  **先删旧行、再插入新的 `idx`**；而 `frame_full` 是按 `frame_idx` 存的（`PRIMARY KEY (frame_idx, key)`）
  ⇒ 旧原始数据变成永远取不到的**孤儿行**（实测每重分析一次多 2786 个 idx / 13930 行、约 +1MB）。
- 修法：`mjscore\store.py` 新增 `prune_frame_full(conn)`（`DELETE FROM frame_full WHERE frame_idx NOT IN
  (SELECT idx FROM frame)`），`mjscore\cli.py` 的 `analyze()` 在写完全部打点行后、`commit` 前调用；
  返回删除行数（本轮验证 0 行，因为入库前已清干净）。
- 顺带修 `--delete-db` 退出码：原来是 `return 1 if not os.path.isfile(p) else 0`（删成功后文件已不在 ⇒ 反而 exit=1），
  改为成功分支直接 `return 0`、文件不存在分支 `return 1`。

验证：`test\mjscore_test.py` 新增 4b（重分析后 `frame` 仍 2786 行、`frame_full` 不膨胀 13930、孤儿 0）
与 4c（`--delete-db` 成功 0 / 不存在 1）共 8 项断言 ⇒ **119 项全部通过**。
`data\db\paipu.sqlite` 与 `data\db\test.sqlite` 都已用 `--delete-db` 后 `python analyze.py data --tool node --full --db-name <名>`
重建为干净库：**各 2498560 B，`frame` idx 1..2786，`frame_full` 13930 行，孤儿 0**。


## 9. 第 15 轮：和牌判别器 + 点数计算器（`mjscore/agari.py`，第二类特征的前置）

用户要求（m00783）：

1. 和牌按牌型分三类、各自要求固定的 block 形状：**国士無双** = 13 种幺九牌各一张 + 其中一种成对（13 个 block）；
   **七対子** = 七个互不相同的对子（7 个 block）；**面子手** = 四组完整面子 + 一组雀头（5 个 block），
   其中完整面子 = 副露摆出的顺子/明刻/明槓/暗槓、手中的暗刻、或手中点数相连的顺子（仅 m/p/s）。实现思路即「枚举 block」。
2. 每类 × 自摸/荣和 × 立直/默听/副露 = **18 种判别器**（国士/七対子必然门清，副露形恒 False）。
3. 每种情形配一个**点数计算器**：亲/子 + 供托；自摸 → 自家得点 + 每家失点，荣和 → 自家得点 + 放铳家失点；规则取**天凤段位战**。
4. 用 `tenhou-url.txt` 的牌谱逐个和牌场景验证；**本轮不集成界面**（它只是第二类特征的前置）。

### 9.1 交付物与接口

- 新模块 `mjscore\agari.py`（798 行，纯函数：只吃「手牌 + 副露 + 和了张 + 场况」，不依赖 `mjscore\replay.py` 的状态机）：
  - 牌型：`is_kokushi` / `kokushi_13wait` / `is_chiitoi` / `decompose_with_pairs` / `_extract_all` /
    `shapes_of(hand, melds=(), win_tile=None)`；另有 `set_melds` / `n_sets` / `meld_set` / `menzen_of`（暗槓不影响门清）/ `state_of` / `concealed_size`。
  - 18 判别器：`_mk_disc(shape, mode, req_state)` + `_en` 生成名字 `<shape>_<mode>_<state>`，汇总在 `DISCRIMINATORS`（18 项，同时注入模块全局）；
    总入口 `check_all(hand, melds=(), win_tile=None, tsumo=True, riichi=0)`、`can_tsumo(...)`、`can_ron(...)`。
  - 打点：`score(hand, melds=(), win_tile=None, tsumo=True, oya=False, honba=0, kyotaku=0, seat_wind=EAST, round_wind=EAST, riichi=0, ctx=None, state=None)`
    → dict（`shape/mode/state/han/fu/yakuman/yaku/base/gain/payments/wait/tiles/melds/menzen/oya/honba/kyotaku`）；
    另有 `payment_of(base, oya, tsumo, honba=0, kyotaku=0)`、`seat_deltas(result, seat, n=4, oya_seat=None, loser=None)`。
- 新测试 `test\agari_test.py`（**176 项全部通过**）：第 1 节 18 判别器 / 第 2 节符 / 第 3 节点数 / 第 4 节宝牌·赤·上限 / 第 5 节全量校验 / 第 6 节最大原则（多解拆解取打点最大者）。
- 语料：第 15 轮新下载的 **66** 个牌谱放仓库根 `data_extra\`（`data\` 仍是原 5 个，保住第 12~14 轮的 119 项测试与界面下拉基线）；
  `download_tenhou.py` 有 `-o/--output-dir` ⇒ 以后下载用 `python download_tenhou.py -o data_extra`。

### 9.2 口径（由 71 个牌谱 / 640 个和牌实测反推，不是凭记忆）

- **役 id 表 0..54** 与 `js\ui.js` 的 `YAKU` 表逐项一致（实测确认 `10-13 自風 東南西北`、`14-17 場風 東南西北` —— 同一刻子既是场风又是自风时两个 id 各记 1 番、
  `18-20 役牌 白發中`、`21 両立直`、`22 七対子`、`52 宝牌 / 53 里宝牌 / 54 赤宝牌`）；役満 = 36..51，
  双倍役満 = 41 四暗刻単騎 / 46 純正九蓮宝燈 / 48 国士無双十三面 / 49 大四喜，天和 37 / 地和 38 / 人和 36 也按役満算。
- **基本点**：`base = min(fu × 2^(2+han), 2000)`；5 番 2000 / 6-7 番 3000 / 8-10 番 4000 / 11-12 番 6000 / ≥13 番 8000；役満 `base = 8000 × 倍数`。
  配分：子家自摸「亲家 `ceil100(base×2)`、其余 `ceil100(base)`」，亲家自摸各家 `ceil100(base×2)`，荣和 `ceil100(base×4)`（子）/`×6`（亲）；
  本场自摸每家 +100、荣和放铳者 +300；和了者另收 `供托 × 1000`。
- **天凤没有切り上げ満貫**：实测 4 番 30 符子家荣和 = **7700**（不是 8000）；6 番 40 符 = 12000。
- **符**：`if tsumo and not pinfu: fu += 2`（平和自摸 20 符）；`if menzen and not tsumo: fu += 10`（門前清栄和 +10，平和荣和 = 30 符）；
  待ち符 `wait_fu` = 嵌張/辺張/単騎 各 2、**両面与双碰 0**（代码注释「天凤实测：双碰不加」，13 个反例都因此成立）；
  連風雀头 = `seat_wind` +2 与 `round_wind` +2 各算一次（合 4 符；docstring 已改，用户 m01068 确认 4 符）；食い平和型 30 符。
  实测符号分布 `{20:75, 25:14（七対子）, 30:367, 40:154, 50:21, 60:6, 70:3}`。
- **和了张必须落在本来不完整的那一组**：雀头形要求手里恰好 2 张（単騎）、刻子形恰好 3 张（双碰），否则它只能落在顺子里
  （`score()` 的 placement 有效性检查；修掉过一例把 1s×3 的手牌解成単騎、符从 30 变 40 的错）。
- **ダブロン**：本场与供托归**先和者**，后和者按 0 本场 0 供托算（`data\2026091320gm-00a9-0000-15180bb5.xml` 第 1 局实测）。
- 无役 → `score()` 抛 `ValueError("役なし：和牌牌型成立，但没有任何役（手牌 %s + %s）")`；牌谱里 `[53, 0]`（里宝牌 0 张）只是占位，比较时要过滤 0 番条目。
- 样本里 **0 个役満**（`yakuman` 标签全空）⇒ 役満/双倍役満的打点只能靠构造用例（第 3 节）与规则校验。

### 9.3 验证结果（全绿）

- `test\agari_test.py` → **176 项全部通过**；第 5 节扫 `data\` 5 + `data_extra\` 66 = **71 个牌谱**，**640 个和牌** / **545 个立直**，
  符/役/番/得点/4 家配分/宝牌指示牌**逐例 0 不符**，`score_err` / `disc_bad` / `tenpai_bad` 全 0。
- 立直不变量：545 个立直手任取一张去掉，都能找到至少一张和了张使 `shapes_of` 非空（立直必定听牌）。
- `is_red` 修正回归：`is_red(16/52/88) = True`、`is_red(124) = False`（原来把白 kind 31 当赤宝牌 ⇒ 赤宝牌多算；三处同步改为
  `kind_of(tid) < 27 and (tid & 3) == 0 and (kind_of(tid) % 9) == 4`：`mjscore\mjlog.py`、`js\tiles.js:22`、`js\mjlog.js:20`）。
- 其他测试：`test\selftest.js` = `[OK] 全部不变量通过`（5 牌谱 / 58 局 / 5824 帧 / draws 2701 / discards 2776 / calls 117 / reaches 104 / doras 10 / agari 51 / ryuu 7）；
  `test\uitest.js`、`test\apptest.js` = 全部通过；`py_compile` 全部 `.py`、`node --check` 全部 `.js` exit 0。
- `test\mjscore_test.py` 与 `analyze.py --tool node` **本环境跑不了**（见第 22 条 WinError 5），不是代码回归。

### 9.4 存疑与后续

- **連風雀头 = 4 符**（自风 +2、场风 +2）：样本无法判别（「自风 = 场风 = 雀头」仅 3 例，2 符/4 符取整后同符）；现按用户 m01068 的确认采用 4 符，并用 `calc_fu` 直测锁定（第 6 节）。
- 本轮只做判别器与点数计算器；**第二类特征第 9~14 项（荣和/自摸期望打点）与第 15/16 项（危险筋组）留待下一轮** —— `mjscore\agari.py` 已按纯函数设计，可直接被枚举调用。

### 9.5 最大原则（多解拆解取打点最大者，m01068）

- 用户要求：一个和牌手牌可能有多种 block 拆解，**得点必须取所有拆解中的最大值**，并要求单独测试。
  `score()` 本来就是 `best = max(cands, key=total_of)`（`total_of`：役満 `8000 × 倍数`、普通役 `base_points(番, 符) × 4`，对打点单调）
  ⇒ 实现已满足要求；本轮补「单独测试」并修掉一个真 bug。
- 真 bug（已修，`mjscore\agari.py` 的 `mentsu_yaku`）：原来用 `dups` 数「重复出现的顺子起点」，把**同一顺子 3 组**（如 123m×3）判成 **二盃口(32)**。
  改成 `pairs = sum(c // 2 for c in 起点计数)`：3 组同顺子 = 一盃口(9) 1 番；4 组、或两组不同成对顺子 = 二盃口(32) 3 番。
- 单独测试（`test\agari_test.py` 第 6 节，本轮 144 → **176 项**）：
  - 全量 640 个和牌断言「选中者打点 = 全部候选的最大值」，**0 处违例**；其中 **53 个**和牌确实存在多解候选。
    为便于核对，`score()` 返回 dict 新增 `cands` 键（每个候选的 `shape/wait/yaku/han/fu/yakuman_mult/total`）。
  - `calc_fu` 直测連風：中張明刻 2 + 中張暗刻 4 + 連風雀头 4 + 自摸 2 = 32 → **40 符**（場风为東时同一手 30 符）⇒ 这条能真正判别 4 符 / 2 符。
  - 用户 m01068 的 6 个例子逐例断言（東場・南家・子家・0 本場・0 供托・宝牌指示牌 1z；「子,亲」= 子家付点, 亲家付点）：
    | # | 立直/默听 自摸/荣和 + 手牌 + 和了张 | 本引擎 | m01068 期望 | 差异原因 |
    |---|---|---|---|---|
    | 1 | 立直自摸 `1123567m234p456s`+1m | 立直+平和+自摸 3 番 20 符 **700,1300** | 700,1300 | 一致 ✓ |
  | 2 | 立直自摸 `1123567m234p777z`+1m | 立直+役牌中+自摸 3 番 40 符 **1300,2600**（単騎读法） | 1300,2600 | 已一致 ✓（旧实现按「単騎要求手里恰好 2 张」剪枝，只给 30 符 1000,2000；现已放开，同种 3 张也能读成単騎） |
    | 3 | 默听荣和 `11223355677m22p`+6m | 二盃口 3 番 40 符 **5200** | 2600（2 番 40 符） | 二盃口番数（天凤与我们 = 3 番） |
    | 4 | 默听自摸 `22233344m123p99s`+4m | 三暗刻+自摸 3 番 40 符 **1300,2600** | 1000,2000（30 符） | 自摸 2 符 + 三个中張暗刻 12 符（20+2+12 = 34 → 40） |
    | 5 | 默听自摸 `11122233m123p99s`+3m | 一盃口+純全帯幺九(3)+自摸 **5 番満貫 2000,4000** | 2000,3900（4 番 30 符） | 123m×3 我们算一盃口 1 番 ⇒ 多 1 番 |
    | 6 | 默听自摸 `11122233m123p44z`+3m | 一盃口+混全帯幺九(2)+自摸 4 番 30 符 **2000,3900** | 1300,2600（3 番 40 符） | 同上 |
  - 例 4/5/6 都是多解的好素材（例 4：三暗刻 40 符 5120 > 両面+一盃口 2 番 20 符 480；例 5：5 番満貫 8000 > 三暗刻 3 番 40 符 5120；例 6：4 番 30 符 7680 > 三暗刻 3 番 40 符 5120）。
- 语料不能裁定这些分歧：71 个牌谱 / 640 个和牌里，「同一顺子 ≥3 组」的手牌 **0 例**，日志含一盃口 24 例、含二盃口 **0 例**
  ⇒ 「二盃口 3 番」与「3 组同顺子算不算一盃口」只能靠天凤规则或用户裁定；现按天凤标准（3 番 / 算 1 番）实现，已向用户逐条报告。

- **用户 m01164 的裁定（6 例全部对齐）**：例 1、3、4、5、6 的判定正确 —— 例 3 的「二盃口 2 番」、例 5/6 漏算的一盃口、例 4 写 30 符都是用户给例子时的疏漏；
  **例 2 是用户漏算了単騎读法**（他说我错、他对）。⇒ 现按「二盃口 = 3 番」「同一顺子 3 组算一盃口 1 番」实现，并确认 **符数也参与最大原则的比较**。
- **placement 枚举已去掉 `n_win` 剪枝**（`mjscore\agari.py` 的 `score()`）：原来「雀头形要求手里恰好 2 张（単騎）、刻子形要求恰好 3 张（双碰）」的剪枝是错的 ⇒
  现在 `if pair == win_kind: placements.append(("pair", None))`（単騎）、`elif s[1] == win_kind: placements.append(("set", i))`（双碰）、顺子含和了张照旧，
  三种读法全部枚举，由 `best = max(cands, key=total_of)`（`total_of` 含符）挑选。用户原话口径：「只需要枚举出每一种可能的 block 拆分方式（包括国士無双、七対子），
  对每一种判定为和牌的拆分计算番、符、打点，比较打点大小即可。」
- **放宽后的经验校验（关键）**：第 5 节全量 640 个和牌的符/役/番/得点/4 家配分/宝牌指示牌仍然 **0 处不符** ⇒ 天凤确实按「含符的最大原则」计分，而不是按某种读法硬定。
  新增 6.4 号用例复刻 `data\2026090320gm-00a9-0000-ed855534.xml` 局 1 who=2：同种 3 张时単騎读法也成立（40 符），但平和両面读法 2 番 30 符 base 480 >
  単騎 1 番 40 符 base 320 ⇒ 仍取 30 符，与牌谱一致。例 2 同理：単騎 40 符 base 1280 > 両面 30 符 base 960 ⇒ 取 40 符。
- 测试总数 172 → **176 项**（第 6 节新增 6.4，例 1 候选数 1 → 2，例 2 改 3 番 40 符 1300,2600）；全量多解候选 47 → **53 例**。

## 10. 第 16 轮：界面微调（和了番种里「里宝牌」0 番不显示，m01212）

### 10.1 要求与改动

- 用户要求（m01212）：和牌信息里没中里宝（`里宝牌(0)`）时，不要在和了番种里显示「里宝牌」条目；`里宝指示牌` 的展示保持原样。
- `js/ui.js` 的 `resultEl(ev, st)`（和了信息渲染，291 行起）在把 `ev.yaku` 的 `[id, 翻]` 转成名字时跳过番数为 0 的宝牌类条目：
  `if (y && y.length && !y[1] && y[0] >= 52 && y[0] <= 54) { continue; }`
  （52 宝牌 / 53 里宝牌 / 54 赤宝牌：这三者的「番数」就是宝牌张数，0 张即没中。）
- 语料实测（71 个牌谱扫 `yaku="…"`）：`53,0` 出现 **165 次**，而 `52,0` / `54,0` 一次都没有 ⇒ 实际只影响里宝牌；规则仍按 52~54 统一写，防将来出现 0 张的宝牌 / 赤宝牌条目。
- 未改：`mjscore/agari.py` 本来就不会在无里宝时产生 53 条目（`test\agari_test.py` 第 4 节已有断言）；`mjscore/feats.py` 的 53/54 役牌映射不受影响。

### 10.2 验证结果（全绿）

- `test\apptest.js` 的 `agariSpec()` 增加「里宝牌 0 番不显示 / >0 番仍显示」断言，并新增 **7g.2** 节：在整份牌谱里找 `[53,0]` 与 `[53,>0]` 的和了帧各一个，`show(st)` 整帧渲染后断言 `.c-result` 文本。
- 实测（`data\2026083020gm-00a9-0000-e9ce1efe.xml`）：0 番帧显示「立直(1) / 役牌 發(1)70 符 / 6800 点」（无「里宝牌」）；2 番帧显示「立直(1) / 平和(1) / 宝牌(1) / 里宝牌(2)30 符 / 8000 点」。
- `node test\apptest.js` = **231 OK / 1 skipped / 全部通过**（跳过的 1 条是原有的条件性样本）；`node test\uitest.js` = 全部通过；`node test\selftest.js` = `[OK] 全部不变量通过`（5 牌谱 / 58 局 / 5824 帧 / draws 2701 / discards 2776 / calls 117 / reaches 104）；`node --check js\ui.js|test\apptest.js` exit 0。

## 11. 第 17 轮：三种向听数（国士無双 / 七対子 / 面子手，`mjscore/shanten.py`）

用户 m01278：开始第二类特征的计算，**先设计三种向听数计算** —— 国士无双向听数 / 七对子向听数 / 面子手向听数，取值 `{-1, 0, 1, 2, >=3}`。

### 11.1 口径（按用户 m01278 的原话落地）

- 定义：为达到听牌状态，最少需要**摸进或副露**的牌张数量。-1 = 已经和牌；0 = 未和牌但听牌；正整数 = 向听数；只关心到 2，更大的统一记 3。
- 枚举法（与用户给的定义等价）：初始手牌若能构成和牌形 ⇒ -1；否则枚举「打一张 → 摸一张」，存在和牌可能 ⇒ 0；不存在就扩成「二打二摸」⇒ 1；再扩成「三打三摸」⇒ 2，仍不成立 ⇒ >=3。
- **进张必须结合场上信息**：某种牌还能摸到几张 = `4 −（自己手牌 + 四家副露 + 四家牌河（被鸣走的牌不重复计） + 所有翻开的宝牌指示牌）`。`avail = 0` 的牌不能当进张；`avail = 1` 时只能算一张（用户的例子：手里一张 4m、牌河与宝牌指示牌合计能看到三张 4m ⇒ 不能再期待摸进 4m；二打二摸时更不能期待摸进**两张** 4m）。
- 用户裁定：枚举法的开销可以接受，但要求把全体测试样例的总耗时报给他，再由他判断是否换算法（见 11.4）。

### 11.2 实现（`mjscore/shanten.py`，210 行，纯 LF）

- 三种牌型各一个 `*_need()`，返回「还差几张进张」的**精确值**（`SENTINEL = 4` 表示无解），对外统一 `cap(need) = min(need - 1, CAP)`（`CAP = 3`）：`-1` = 和牌、`3` = `>=3`。
- 面子手：真正的枚举 —— `GROUPS` = 34 个刻子 + 21 个顺子（共 55 组）；`rec(start, left, cost)` 取 `left = 4 - 副露数` 组面子 + 一组雀头；`take()` 优先消耗手牌、不够就算「摸进来」（必须 `drawn[k] + 1 <= avail[k]`），`untake()` 回滚；同一组可重复取（等价于组合去重）；剪枝只有 `cost >= best`。
- 国士無双 / 七対子用闭式：前者 = 缺的幺九种类数（手里有幺九对子、或某张单张/空位能凑出对子时 +1），后者 = 「凑成 7 个对子」成本最小的 7 种之和（有副露直接无解）。
- 与回放层对接：`visible_counts(state, seat)` / `avail_counts(state, seat)` / `shanten_at(state, seat)`（用 `mjscore.replay` 的状态结构与 `mjscore.agari.counts_of`）。
- 本轮**不做**特征入库 / 界面 —— 用户只要「先设计三种向听数计算」。

### 11.3 验证结果（`test\shanten_test.py`，92 项全绿）

1. 手算用例：三种牌型的 -1 / 0 / 1 / 2 / >=3（含 `14-3n`、`13-3n` 手牌与带副露的手牌；注意「四面子 + 两张单张」已经是**听牌 0**，不是 1 向听）。
2. 场上可见牌约束：`123m456m789m123p5s`（単騎听 5s）在 `avail[5s] = 4 / 1 / 0` 时分别给 0 / 0 / 1。
3. **独立参考实现对拍**：40 组随机手牌（张数合法、副露 0~3 组）× 随机可见牌（31 组面子手 >=3）—— 参考实现枚举 d = 0..3 张摸牌 multiset，再无条件地把 `counts + D` 拆成「(4-n) 组面子 + 雀头」（允许丢弃多余的牌）⇒ 三种向听数**逐例与模块一致**。
4. 全量语料（`data\` 5 + `data_extra\` 66 = 71 个牌谱、**37533 帧**、每帧 3 个向听数 = 112599 次计算）：
   - 面子手向听数分布：`-1` 278 / `0` 5862 / `1` 9775 / `2` 10943 / `>=3` 10675（这是加了「起和役」之后的口径，见 11.6）。
   - 三条硬不变量全部成立：自摸和了的前一帧 279 帧全是 -1；荣和家的手牌 + 放铳牌 358 例全部能和；**立直家（含宣言后未打牌）的 13 张手牌 2231 帧全部听牌**（对应第 15 轮「立直必定听牌」的实测）。

5. **起和役（副露手必须有役）**：见 11.6 —— 10 组固定副露用例（A~J）逐条断言，并用 `mjscore/agari.py` 的 `score()` 当独立裁判交叉验证。
6. **全量语料双向复核**：形和但无役的副露帧 **3 帧**全部没记 `-1`；记成 `-1` 的副露帧 **102 帧**经 `agari.shapes_of()`（形，第 18 轮起改用）+ `agari.score()`（役）复核全部成立。

### 11.4 耗时（用户 m01278 要求报告的数字）

- 加「起和役」后全量 37533 帧 × 3 个向听数 = **144.26 s**（第 18 轮复测 **143.70 s**），平均 **3.843 ms/帧**（复测 3.829），单帧最慢 29.43 ms（复测 25.29）；`test\shanten_test.py` 整体 **152.3 s**（92 项）。第 17 轮最初版（不判役）是 102.5 s / 2.73 ms/帧。
- 若以后要对每一帧算**四家**的向听数：前 150 帧实测 1.82 s / 12.141 ms/帧 ⇒ 全量外推约 **455.7 s**。（用户 m01436 已答复：时间可以接受、暂不换算法，因为枚举的中间产物对后续计算有用。）
- 用户 m01436 裁定：**耗时可以接受，暂不换算法**（枚举的中间产物对后续计算有用）；以后若要提速可考虑整数规划 / 增量更新 / 缓存 / 只算到 1 向听等。

### 11.5 本轮踩到的坑

- 第一版是「kind 顺序 DFS + 搭子 / 单张 / 空槽」的近似模型，在 `avail` 约束下**不完备**：空槽里的 3 张牌不能假定都摸得到，单张的完成方式也不止「再摸两张同种」（还能摸两张邻牌凑顺子）。改成「直接枚举完整面子 + 雀头」的精确算法后才消失。
- 递归成本里 `3 * 空槽数` 这类项**不是下界**（它随枚举递减），拿它参与剪枝会把根节点直接剪掉（症状：所有手牌都返回 3、耗时 0.000 s）。
- 写「对拍参考」时也踩了一次：判断「能不能取出 (4-n) 组面子 + 雀头」的朴素 DFS 必须允许**丢掉多余的牌**，否则会误报无解（一度以为模块偏乐观，最后用「直接枚举 W 计划」的第二种参考复核，确认模块才是对的）。
- 顺子判定写 `k % 9 <= 6` 不够：字牌「中」的 kind 33 满足 `33 % 9 == 6` ⇒ `c[k + 2]` 越界，必须加 `k < 27`。
- 造测试手牌时张数必须是 `14-3n` 或 `13-3n`（第一版冒烟测试造了「10 张 + 2 副露」的非法手牌，期望值因此写错，被模块纠正）。

### 11.6 起和役（副露手必须有役，m01436）

（第 18 轮已把这里的 `has_open_yaku` / `MENZEN_ONLY_YAKU` 换成 `mjscore/agari.py` 的 `sets_min_yaku_ok`：见第 12 节。下面记的是第 17 轮当时的口径。）

用户 m01436 规定：和牌检测必须遵循立直麻将的起和规则 —— block 拆分成立但**没有任何役**的「假和牌」不能记为 -1，到它的距离也不能算进向听数。统一规定（之后所有特征同样适用）：**输入里只要含非暗杠副露（吃 / 碰 / 加杠 / 大明杠），就按副露手记，此时必须判起和役；否则按门清记（门清可以立直，总有起和役）**。用户同时答复：枚举法耗时可以接受、暂不换算法，因为枚举的中间产物对后续计算有用。

- 实现（`mjscore/shanten.py`）：新增 `has_open_yaku(sets, pair, melds=(), seat_wind=27, round_wind=27)` —— 门清（含只有暗杠）直接返回 `True`；否则把枚举出的暗面子（`group_set`）与 `meld_set(melds)` 一起交给 `mjscore/agari.py` 的 `mentsu_yaku(sets, pair, WAIT_RYANMEN, True, False, 自风, 场风)`，只要命中不在 `MENZEN_ONLY_YAKU = (7, 9, 32, 40, 41)`（平和 / 一盃口 / 二盃口 / 四暗刻 / 九蓮宝燈）里的役就算有起和役。副露手能成立的役（役牌 / 断幺九 / 三色同順 / 対々和 / 三暗刻 / 一気通貫 / 混一色 / 混老頭 / 三槓子 …）都与和了张、待ち形无关 ⇒ 不需要 placement，直接复用现成的役判定。
- `mentsu_need()` 只在 `need_yaku`（非门清）时要求 `has_open_yaku`，并用 `yaku_memo[(暗面子组合, 雀头)]` 缓存判定；`shanten_of()` 里 `n_melds > 0` 却没给 `melds` 会抛 `ValueError("有副露时必须传 melds（起和役要按副露牌判，m01436）")`；`shanten_at()` 顺手修掉「`len(pl["melds"])` 会把拔北算成一组副露」的隐患，并传自风 `27 + (seat - oya) % 4`、场风 `27 + round // 4`（`initial_state()["round"]` 是 0 基）。
- 影响（全量 71 牌谱 / 37533 帧，与「无役约束」的旧行为逐帧对比，共 **335 帧**变化）：`-1→0` 3 / `-1→2` 1 / `-1→3` 1 / `0→1` 88 / `0→2` 33 / `0→3` 9 / `1→2` 140 / `1→3` 17 / `2→3` 43 ⇒ 记为 -1（真和牌）的帧从 283 降到 **278**。旧行为（monkeypatch `has_open_yaku` 恒真）下 -1 也是 283 帧，与改造前的分布一致；新旧两种口径下所有 -1 帧的手牌张数都等于 `14-3n`（没有伪 -1）。
- 双向核对（`test\shanten_test.py` 第 4 节，全量语料）：① 「形和（`agari.can_tsumo`）但 `score()` 抛役なし」的副露帧 **2 帧**，全部没有记成 -1；② 记成 -1 的副露 draw 帧 **102 帧**，全部经 `can_tsumo`（形）与 `score()`（役）复核为「形和 + 真有役」。
- 第 1b 节 10 组固定用例（自风 28 / 场风 27；`A` = 吃 123s + `123m456m234p99m`）：A → **0**（形和但无役，最近的役是把 234p 换成 123p 成三色同順，还差 1 张）；B 同手牌换碰白 → **-1**（役牌）；C 换暗杠東 → **-1**（门清）；D → **-1**（三色同順）；E（唯一候选是门清役一盃口）→ **2**；F → **-1**（三暗刻）；G 碰東 東場 → **-1**（場風）、南場自风東 → **-1**（自風）、西場自风北 → **2**（无役）；H → **-1**（断幺九）；I 门清同手牌 → **2**（门清不判役，与旧行为一致）；J 未传 melds → 抛 ValueError。每例都用 `agari.score()` 当独立裁判对齐。
- 测试裁判的注意点：`agari.score()` 的 `hand` 是**不含和了张**的 `13-3n` 张（`win_tile` 另给）；`agari.can_tsumo(hand, melds)`（`win_tile=None`）里 `hand` 是完整的 `14-3n` 张、只看牌型不看役；`score()` 末尾把 `ctx_yaku` / `dora_yaku` 一并算进 `han` ⇒ 只有宝牌没役的手**不会**抛「役なし」，造测试牌必须避开赤 5 的 id（16/52/88）。

## 12. 第 18 轮：起和役并入判别器 + 得点计算前置门槛 + 向听叶子改用判别器（m01701）

用户 m01701 的四条裁定：① 18 种判别器**必须**考虑起和役（区分自摸/荣和与立直/默听/副露，就是为了判起和条件）；② **得点计算只能从「判别器通过（即有役和牌）」的手牌进入**，进入得点计算的手牌不可能无役；③ 向听计算的叶子改用判别器判定；④ 判别器暂不考虑一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底等偶发或特殊役，用真实牌谱测试时注意规避它们的影响。

### 12.1 口径（起和役门槛）

- 统一门槛 `min_yaku_ok(menzen, tsumo, state, ids)`：`state == RIICHI`（立直本身就是役）→ 通过；`tsumo and menzen`（門前清自摸和）→ 通过；否则要求存在**真役** —— `GATE_IGNORED = OCCASIONAL_YAKU(2, 3, 4, 5, 6) + DORA_IDS(52, 53, 54)` 之外的役 id。宝牌 / 里宝 / 赤宝牌与一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底都不算役（用户 m01701 ④）。
- 国士無双 / 七対子本身必然是役（门清）⇒ 判别器直接放行；面子手必须在待ち读法里**存在一个有真役的拆解**。
- `score()` 的候选先过同一个门槛，再按「最大原则」取打点最大者 ⇒ 得点计算的入口就是「有役和牌」。

### 12.2 代码改动

- `mjscore/agari.py`（801 → 923 行，纯 LF）：
  - 新增 `OCCASIONAL_YAKU = (2, 3, 4, 5, 6)`、`DORA_IDS = (52, 53, 54)`、`GATE_IGNORED = OCCASIONAL_YAKU + DORA_IDS`、`min_yaku_ok(menzen, tsumo, state, ids)`（第 304 行）；新增 `win_candidates(hand, melds=(), win_tile=None, tsumo=True, seat_wind=EAST, round_wind=EAST)`（第 707 行，从 `score()` 里抽出的候选枚举：国士 / 七対子 / 面子手 × placement 三读法）、`has_min_yaku(hand, melds=(), win_tile=None, tsumo=True, seat_wind=EAST, round_wind=EAST, state=None, riichi=0)`（第 775 行，判别器用）、`yaku_ids_of_sets(sets, pair, melds=(), tsumo=True, seat_wind=EAST, round_wind=EAST)`（第 581 行）、`sets_min_yaku_ok(sets, pair, melds=(), tsumo=True, seat_wind=EAST, round_wind=EAST, state=None, riichi=0)`（第 594 行，已知拆解的「有没有役」内核，向听叶子用）。
  - `_mk_disc(shape, mode, req_state)`（第 320 行）分三支：国士 / 七対子门清放行；面子手先 `shape in shapes_of(hand, melds, win_tile)`，再 `has_min_yaku(hand, melds, win_tile, tsumo=(mode == TSUMO), seat_wind=ctx.get("seat_wind", EAST), round_wind=ctx.get("round_wind", EAST), state=st, riichi=riichi)`。`check_all` / `can_tsumo` / `can_ron` 都新增 `seat_wind=EAST, round_wind=EAST` 参数并转发（此前判别器把自风 / 场风收进 `**ctx` 却不用）。
  - `score()` 的候选块改成 `all_cands = win_candidates(concealed, melds, win_tile, tsumo, seat_wind, round_wind)` → 空则 `raise ValueError("并未和牌：手牌 %s + %s" ...)` → `cands = [c for c in all_cands if min_yaku_ok(menzen, tsumo, st, [i for i, _h in c["yaku"]])]` → 空则 `raise ValueError("役なし：和牌牌型成立，但没有任何役（手牌 %s + %s）")`。
  - **修掉宝牌漏洞**：改造前 `score()` 把 `ctx_yaku` / `dora_yaku` 也算进「有没有役」，副露手「只有宝牌、没有役」会被判成能和（实测：吃 123s + `123m456m234p99m`、和了张 9m 自摸，`ctx={"dora": [9m]}` → `han = 1`、`yaku = [(52, 1, '宝牌')]`、`base = 240`）；现在同一手抛「役なし」。
- `mjscore/shanten.py`：删掉 `MENZEN_ONLY_YAKU = (7, 9, 32, 40, 41)` 与自制的役判定，`has_open_yaku(sets, pair, melds=(), seat_wind=27, round_wind=27)` 改为委托判别器内核 `agari.sets_min_yaku_ok([group_set(g) for g in sets], pair, melds, tsumo=True, seat_wind=seat_wind, round_wind=round_wind)`（签名不变 ⇒ `mentsu_need` 的叶子调用点与测试引用都不用改）；向听「打一张 → 摸一张」模型里最后摸进的牌就是和了张 ⇒ 一律 `tsumo=True`。
- 测试：`test\agari_test.py` 第 1 节加判别器带役断言（副露无役 `can_tsumo/can_ron == []`；换碰白后 `check_all(...) == [(面子手, 自摸, 副露)]`；门清无役 `can_ron == []` / `can_tsumo == [面子手]` / 立直 `[(面子手, 荣和, 立直)]`；副露手只有宝牌要抛「役なし」），第 5 节全量循环给 `check_all` 补传自风 / 场风（原来漏传 ⇒ 33 例「唯一役是自风/场风役牌」被误判）；`test\shanten_test.py` 第 4 节的「假和牌」判据从 `agari.can_tsumo` 换成 `agari.shapes_of`（`can_tsumo` 现在也带役门槛，用它找假和牌永远找不到 ⇒ 见踩坑 30）。

### 12.3 验证结果（全绿）

- 语料探针（改造前先扫）：71 牌谱 / 640 个和牌里，**没有任何一个和牌的役列表只由偶发役（2/3/4/5/6）或宝牌（52/53/54）构成** ⇒ 起和役门槛不会让任何真实和牌帧被误判，全量回归不需要跳帧。
- `test\agari_test.py`：**182 项全部通过 / 失败 0**（原 173 项 + 3 处期望值更新）；全量 71 牌谱 / 640 和牌的符 / 役 / 番 / 得点 / 四家配分 / 宝牌指示牌仍 **0 不符**，立直 545 例、最大原则 0 违例、多解 53 例全部照旧。
- `test\shanten_test.py`：**92 项全部通过 / 失败 0**（section 1 + 1b + 2 + 3 = 86 项 / 7.8 s，全量 151.4 s）；面子手向听数分布 **`-1` 278 / `0` 5862 / `1` 9775 / `2` 10943 / `>=3` 10675**，与第 17 轮带起和役的口径完全一致；三条硬不变量（自摸和了前一帧 279 全 -1、荣和 358 例全能赢、立直家 2231 帧全听牌）成立；「形和但无役」的副露帧 **3 帧**全部没记 -1，记成 -1 的副露帧 **102 帧**经 `shapes_of` + `score()` 复核全部成立。
- `test\mjscore_test.py`：**119 项全部通过 / 失败 0**（2.1 s）—— 本轮找到绕开「本环境禁止建子进程管道」的办法（`subprocess.run(argv, stdout=<文件对象>, stderr=<文件对象>)`，见踩坑 31），`--tool node` 的交叉校验因此可以在本机跑。
- JS 三件套：`node test\selftest.js` = `[OK] 全部不变量通过`（5 牌谱 / 58 局 / 5824 帧）；`node test\uitest.js` = 全部通过；`node test\apptest.js` = **231 OK / 全部通过**。
- 耗时（加门槛后）：全量 37533 帧 × 3 个向听数 = **143.70 s**，平均 **3.829 ms/帧**，单帧最慢 25.29 ms；四家全算外推约 **438.6 s**（第 17 轮不带门槛时是 102.5 s / 2.73 ms/帧）。

### 12.4 后续

- 起和役口径已在判别器 / `score()` / 向听三处统一（同一个 `min_yaku_ok`）；第二类特征其余项（听牌强度、期望听牌枚数、期望打点、危险筋组…）可直接复用。
- 偶发役（一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底）仍未纳入（用户 m01701 明确暂不考虑）；以后要算时，`GATE_IGNORED` / `OCCASIONAL_YAKU` 就是要放开的位置。

## 13. 第 19 轮：12 个期望特征（`mjscore/expect.py`，第二类特征）

### 13.1 要求与口径（用户 m01877；概率 / 假设 / 表宝牌口径已按 m02073、m02075 修订，见 13.6；打点口径已按 m02389 更正，见 13.8）
- 12 个特征（11 个「非负实数」+ 1 个「正实数」，本实现一律给 float）：
  - 枚数 6 项：副露自摸期望听牌枚数 / 副露自摸期望听牌绝对枚数 / 副露荣和期望听牌枚数 / 副露荣和期望听牌绝对枚数 / 立直·默听期望听牌枚数 / 立直·默听期望听牌绝对枚数。
  - 打点 6 项：副露荣和 / 副露自摸 / 立直荣和 / 立直自摸 / 默听荣和 / 默听自摸 期望打点。
- 期望听牌枚数 = Σ_听牌状态 [p(听牌状态) × 该状态「满足起和役的和牌张数」]；枚数要考虑**当前牌桌公共信息**（自己手牌 + 四家副露 + 四家牌河（被鸣走的不算） + 宝牌指示牌）之后再数。
- 绝对枚数 = 向听搜索仍用公共信息，但**达到听牌状态后只数自己手牌**（4 − 自己握着（手牌 + 副露））⇒ 用户熟悉的「两面听 8 枚」能直接对上，便于定位牌型。
- 期望打点 = **「已经和牌」前提下的条件期望**（用户 m02389 更正）：`Σ [p(和牌状态) / Σ p(和牌状态)] × 和牌自家得点` —— 先把各和牌叶子的概率归一化再加权求和，**「达到和牌状态」的概率不计入**（那是「听牌强度」要算的量；实现 = 每个节点维护 `SC = Σ p × 得点` 与 `MS = Σ p`，打点 = `SC / MS`，见 13.8）；打牌选择仍按 `argmax{ p(打完的后继状态 → 和牌状态) × 和牌打点 }`（未归一化的 Σp·得点）；得点用第 15 / 18 轮的 `agari.score(...)["gain"]`（含本场 / 供托 / **表宝牌** —— 宝牌指示牌是场上公开信息，按 `state["dora"]` 计入 `ctx`；不含里宝 / 一发 / 嶺上 / 海底等偶发役；赤 5 按非赤算）。
- 概率在枚举进张时同步算：`p(k) = (avail[k] − used[k]) / (Σavail − Σused)`（`used` = 这条路线已经假想摸进的张数 ⇒ **每假想摸进一张就把该牌的剩余张数与分母各减 1**，不会再期待摸到第 5 张同种牌；用户 m02073 修正，见 13.6）；多次摸牌 = 概率连乘，只统计**没有一次进张浪费的完美路线**（每次进张后都存在一张打牌让最小向听数正好 −1）；打牌取 argmax（打点 = 取最大；枚数见 13.2 的两种聚合口径）。
- 假设（用户 m02075，见 13.6）：带「副露」字样的 6 项（4 个枚数 + 2 个打点）**不管本帧是否门清都按「有副露」计算**（起和役与番数都在副露状态判 ⇒ 不会出现平和 / 一盃口 / 門前清自摸和 / 门清加符）；门清帧另有 2 个枚数项（与自摸 / 荣和无关，因为门清自摸必有役）+ 4 个打点项（按本帧状态取名 `riichi_*` / `damaten_*`），副露帧的门清项记 0。
- 边界：向听数 ≥3（默认 > 上限 1）一律 0；已经和牌的帧枚数 0、打点 = 该手牌的最大和牌得点；13−3n 张手牌直接算；14−3n 张（摸牌帧 / 吃碰帧）先打一张再算。

### 13.2 实现（`mjscore/expect.py`，当时 519 行 / 26128 B / 纯 LF（m02647 后 573 行 / 29522 B）；打点假设已按 m02512 改成「立直 / 默听」两套，见 13.9；枚数已按 m02647 改成条件期望、节点键 24 → 36，见 13.10；`mjscore/agari.py` 943 行 / 37996 B）
- 模块：`FEATURES`（12 项 key → 显示名）、`KEYS` / `NAMES`；`MAX_SHANTEN = 2`（绝对上限）+ `DEFAULT_MAX_SHANTEN = 1`（默认上限）；`tid_of(kind)`（同种第 n 张，避开赤 5 的 16 / 52 / 88）、`tiles_of(counts)`。
- `_mentsu_waits(counts, slots)`：`shanten.mentsu_need` 的「只差 1 张」变体（DFS 成本 ≤ 1，收集 `drawn` = 顺子 / 刻子缺的那张或雀头的另一半）；`waits_of(counts, melds)`：国士（有对子听缺的幺九、十三面听全部幺九）+ 七対子（听手里单张的种）+ 面子手（`_mentsu_waits`）取并集，门清无副露才查国士 / 七対子。
- `class Expect(state, seat, agg="sum", max_shanten=DEFAULT_MAX_SHANTEN)`：`dist(counts, used=None) = min(国士, 七対, 面子手)`（面子手已含起和役；缓存键含 `used`）；`waits(counts)`（形状听牌张，与可见牌 / 起和役无关）；`_avail_left(used)` / `_unseen_left(used)`（扣掉假想摸进的牌）；`_eval(counts, kind, tsumo, assume)` = 一次 `agari.evaluate(...)` 同时得到「有没有役」与 `gain`（返回 None ⇒ 这颗和牌张不计；furo 假设用 `state=FURO, menzen=False`，menzen 假设用 `state=self.cat, menzen=True`，并传 `ctx={"dora": self.dora}`）；`_tiles(counts, kinds, measure, used)`（avail = Σ(avail[k] − used[k])，abs = Σ(4 − counts[k] − 副露张数)）；`node(counts, used=None)`（13−3n 张 → 24 个内部键 = 12 个枚数 + 6 个打点分子 + 6 个打点分母，带缓存）。
- `node(counts, used)`：叶子（d = 0）对每个模式取 `got = [k for k in waits if _eval(k, FURO) is not None]` 写副露 4 个枚数键、打点分子 `("sc", FURO, mode)` 与打点分母 `("ms", FURO, mode)`（每张有役和牌张 `ms += p`）；门清帧再写 2 个枚数键（用**全部** wait）、打点分子 `("sc", MENZEN, mode)` 与打点分母 `("ms", MENZEN, mode)`。非叶子：枚举合格进张（手里 < 4、`avail[t] − used[t] > 0`、摸进后 `dist == d − 1`），再枚举打牌只留「打完 `dist == d − 1`」的；`agg = "sum"` 的枚数键累加 `p × Σ kids`、其余枚数键累加 `p × max(kids)`；打点键先按 `chosen[("sc", 假设, 模式)] = max(kids, key=…)` 选分支，再 `sc += p × chosen[sc]`、`ms += p × chosen[ms]`（分子分母走同一条 argmax 分支）。`compute()` → `(12 项, alt)`：张数不是 13−3n / 14−3n ⇒ 全 0；14−3n 且 `dist == -1` ⇒ 枚数 0、打点 = 该手牌和牌得点；14−3n ⇒ 只留最小向听的打牌，**枚数键对 keeps 求和、打点键对 keeps 取最大**；13−3n ⇒ 直接取 `node(counts)`。模块 API：`values_both(state, seat, agg="sum", max_shanten=DEFAULT_MAX_SHANTEN)` / `values(...)`（默认上限 `DEFAULT_MAX_SHANTEN = 1`，绝对上限 `MAX_SHANTEN = 2`）。
- 两种聚合口径（24 个内部键在同一份 dict 里）：`agg` 同时作用于枚数键与打点键 —— `sum` = 所有完美路线 / 所有合格打牌都计入（**默认**）；`best` = 每层打牌只取最大（与打点口径一致）。`alt`（`values_both` 的第二个返回值）是另一种口径，且**只有 6 个枚数项**（`("sc", assume, mode)` / `("ms", assume, mode)` 8 个打点键与 `agg` 无关，在 `alt` 里恒 0）。
- 本轮做的三处性能优化：① 打点只在小向听打牌里取最大（不评估让向听数变大的打牌，否则会再深一层枚举，那也不是有意义的打法）；② `node()` 里 `if self.dist(newc) != d - 1: continue`（进张后必须正好 −1 才可能不浪费，省下大量 `dist` 调用，等价于逐个试打）；③ `compute()` 的 14−3n 分支先算 `d0 = dist(counts)`，`d0 > max` 直接返回全 0、`d0 == -1` 直接走和牌分支（省下 14~34 次 `dist` 调用；依据见第 19 节第 35 条）。

### 13.3 验证结果（全绿）
- `test\expect_test.py`（m02647 后 672 行）**70 项全部通过 / 失败 0**（总耗时 23.6 s；m02647 前 66 项 / 636 行；原 47 项 + 宝牌 / 扣减 / 两向听独立参考等新断言）：① `waits_of` 对暴力 `agari.shapes_of` 对拍（合成嵌张 / 両面 / 七対子 / 国士十三面 / 国士有对子 + 语料 239 个听牌手牌）**0 差异**；② 手算用例（嵌张 4 枚 + 默听自摸、両面 8 枚 + 平和荣和 / 自摸、牌河见 1 张 ⇒ 期望 7 / 绝对 8、副露碰發 8 枚、吃 123s 无役 ⇒ 0、立直与默听共用枚数项、14 张根节点、已经和牌的帧、张数不对、超上限、**副露假设与门清假设并存**、**表宝牌计入打点**）；③ 120 个听牌手牌 × 2 种假设逐键与独立参考（`used` 逐张扣减 + 用 `agari.score` 自己判役取点）一致；④ 20 个 14 张「打一张即听」帧的独立一层聚合（sum / best × 副露 / 门清）一致；⑤ **3c：2 个向听 1 的手牌用扣减版独立枚举对拍**；⑥ 不变量（非负 / 绝对 ≥ 期望 / 和牌帧枚数 0 / 超上限 0）0 违规；⑦ **期望打点归一化（m02389）**：`node_keys()` 20 键（m02512 后 24 键、m02647 后 36 键，见 13.9 / 13.10）、叶子 / 中间节点 / keep 三级都满足 `打点 = SC / MS`（多和牌张 = 各张得点的概率加权平均，如 L1 门清自摸 5666.67、13 张中间节点 `23468m2278p2346s` 门清自摸 5150.0）、`_pick_score` 在分母 0 时返回 0.0、多解候选（120 手牌 × 2 假设逐键）与独立参考一致；⑧ **立直 / 默听两套假想（m02512，见 13.9）**：副露帧门清 6 项记 0，门清帧 4 个打点项都算（`h1` 荣和 1300 / 自摸 2000、`h2` 荣和 2000 / 自摸 2700、已立直帧 `damaten_tsumo_score` 1100 等）。
- 全量 71 牌谱 / 37533 帧的**最小向听数**分档：`-1` 281 / `0` 6137 / `1` 10539 / `2` 11503 / `>=3` 9073（注意这是三种牌型取最小，与第 17 / 18 轮记的「面子手」分档不可直接比）。
- 未接入 `mjscore/feats.py` / DB / 界面（本轮只做计算，等用户确认耗时与口径）。
- m02766 之后（见 13.11）：`test\expect_test.py` 721 行 / **73 项全部通过 / 失败 0**（23.5 s），上一行那 70 项里只有枚数分母相关的断言改了期望值。

### 13.4 耗时（用户 m01278 / m01877 要求报告，据此判断是否换算法）
- 单帧平均（每档 25 帧样本，71 牌谱）：上限 0（只算向听 0 的帧）`-1` 2.9 ms / `0` 19.5 ms / `1` 2.1 ms / `2` 4.8 ms / `>=3` 5.7 ms ⇒ **全量外推 250 s（约 4 分钟）**；上限 1（默认）`0` 20.0 ms / `1` **536 ms**（平均 15 个节点）/ 其余同上 ⇒ **全量 5882 s = 1.63 小时**；上限 2 时向听 2 的帧 **9.78 s**（3 帧样本，平均 106 个节点）⇒ 全量约 **32.9 小时**（1.63 h + 11503 × 9.78 s）。
- 成本几乎全在**向听数 1** 的帧（10539 × 0.536 s = 5650 s ≈ 96%）；瓶颈是 `shanten.shanten_of`（纯 DFS ≈ 3.5~4 ms/次，这类帧要 150~280 次）。
- 三个可选方向（待用户定）：① 保持默认上限 1（向听 ≥2 的帧 12 项全 0，全量 1.63 h）；② 换**快速向听算法**（按花色 DP / 表法，理论可快两个数量级，上限 2 也可能压到可接受）；③ 只对检索 / 展示需要的帧按需算（不预先入库全量）。

### 13.5 本轮踩到的坑
- 见第 19 节第 33~37 条；本轮修订新增第 38~48 条（第 43~45 条见 13.8 / 13.9，第 46~48 条见 13.10 / 13.11）；第 20 轮新增第 49~51 条（见 14.5）。

### 13.6 口径修订（用户 m02073 / m02075：假想摸牌扣减、一轮枚举、副露假设、表宝牌）

- ① **概率扣掉假想摸到的牌**：`used`（34 项计数）随路线累加，`p(k) = (avail[k] − used[k]) / (unseen − Σused)`；`dist(counts, used)` / `node(counts, used)` 的缓存键都含 `used`（`_eval` 的缓存不含 used，因为得点与已摸牌无关）。原写法「每一步都用当前帧的可见牌」会重复期待已摸到的牌，甚至出现「第 5 张同种牌」。
- ② **一次候选枚举同时得到「有没有役」与打点**：`mjscore/agari.py` 新增 `evaluate(hand, melds=(), win_tile=None, tsumo=True, oya=False, honba=0, kyotaku=0, seat_wind=EAST, round_wind=EAST, riichi=0, ctx=None, state=None, menzen=None)`（体为 `try: return score(...) except ValueError: return None`）；`Expect._eval()` 每张和牌张只调它一次（原先 `_win` 与 `_score` 各跑一遍候选枚举）。
- ③ **副露假设**：`agari` 全链路新增 `menzen=None` 开关（None = 按 melds 推断，`False` = 强制按副露手算 ⇒ 国士 / 七対子 / 九蓮 / 平和 / 一盃口 / 門前清自摸和 / 門清加符全不成立），逐层传进 `win_candidates` / `has_min_yaku` / `sets_min_yaku_ok` / `yaku_ids_of_sets` / `score`；`Expect._eval` 用 `state=FURO, riichi=0, menzen=False` 算副露项、用 `state=self.cat, riichi=self.riichi, menzen=True` 算门清项。
- ④ **表宝牌**（顺手发现的缺陷）：`_eval` 原先没传 `ctx` ⇒ `dora_yaku` 拿到空 tuple、期望打点系统性偏低。现在 `self.dora = tuple(state.get("dora") or ())` 并传 `ctx={"dora": self.dora}`（宝牌指示牌是场上公开信息）；赤 5 仍按非赤算（`tid_of(kind) = kind*4 + 1`，要支持赤牌得把真实牌 id 带进来，本轮不做）。
- 文件规模：`mjscore/agari.py` 943 行 / 37996 B、`mjscore/expect.py` 459 行 / 21984 B（均纯 LF）。
- 验证：`test\agari_test.py` 182 项（全量 640 和牌的符 / 役 / 番 / 得点 / 配分 0 不符）、`test\expect_test.py` 61 项、`test\shanten_test.py` 92 项、`test\mjscore_test.py` 119 项、JS 三件套（`apptest` 231 OK）全绿。

### 13.7 两向听示例文档（根目录 `expect_example.md`，用户 m02075 第 ④ 条）

- 文档 **24770 B / 345 行 / 纯 LF**（初版 15705 B / 284 行，经 13.8 与 13.9 两次修订），用一个真实帧把 12 项逐个算一遍：第 1 节特征表 / 第 2 节例子帧 / 第 3 节计算规则（向听含起和役、概率扣减、树的走法、两种口径、枚数与打点的聚合差别、两种假设）/ 第 4 节树展开（根 12 种打牌、20 条路径、5 个听牌叶子、役·符·得点明细 + 两个算点示例）/ 第 5 节十二项逐个算 / 第 6 节复现代码 / 第 7 节口径与限制。
- 例子帧：`data_extra\2026091422gm-00a9-0000-c6933e45.xml`，`round_index = 2`、`ev_index = 46`、`seat = 0`；14 张 `2468m22378p23346s`（全断幺九，副露假设下也有役 ⇒ 两类特征同时非 0）、门清未立直、自风北 / 场风東、1 本场 1 供托、宝牌指示牌 `2s` ⇒ 宝牌 `3s`、`unseen = 96`、`dist(14) = 2`（复现要显式传 `max_shanten=2`）。
- 帧级 12 项（`agg = "sum"`）：4 个副露枚数项均 **0.252632**；`menzen_tenpai_expect` **0.378947**、`menzen_tenpai_abs` **0.421053**；`furo_ron_score` = `furo_tsumo_score` = **1.478163**（打点已在 13.8 按 m02389 更正为 3300.0 / 4185.714286 / 4977.777778）；`riichi_ron_score` **6333.333333** / `riichi_tsumo_score` **8055.555556**（m02512 后：本帧虽未立直，也按「保持门清到听牌、听牌时宣布立直」算，见 13.9）；`damaten_ron_score` **2.187383**、`damaten_tsumo_score` **3.344532**；best 口径 6 个枚数项 = 0.042105 ×4 / 0.063158 / 0.070175。
- 树的要点：根 12 种打牌里只有打 3p / 3s / 6s 打到最小向听 2；三个 keep 的节点值完全相同；打 3p 一支 20 条路径 → 5 种听牌叶子（P(叶子) 0.021053 / 0.010526，**Σ P = 0.084211** = 两次进张都正好各减 1 向听的概率）；叶子处 `ul = 94`；门清荣和里 6m8m 等 7m 是嵌张 ⇒ 40 符。
- 文档写明两条聚合语义：**枚数特征所有合格路径相加、打点特征在打牌层取 argmax**（帧级打点 = 三个 keep 里最好的那个，不是相加）—— 这正是用户 m01877「打牌则选让对应期望打点最大的一张」的落实。
- 文中每个数字都用独立复算脚本核对过（`values_both(st, 0, max_shanten=2)` 实测 1.907 s，与文档逐项一致）；复现片段就是文档第 6 节那段代码。

### 13.8 期望打点口径更正（用户 m02389：先归一化再加权）

- 用户指出：期望打点隐含「**已经和牌**」这个前提，所以**不应包含「达到和牌状态」的概率**（那是之后「听牌强度」要算的量）。正确公式：
  `打点 = Σ [ p(叶子) / Σ p(和牌叶子) ] × 和牌得点`；而 n 摸 n 打中**打牌的选择**仍按 `argmax{ p(打完的后继状态 → 和牌状态) × 和牌打点 }`（= 未归一化的 `Σ p × 得点`）。
- 实现：`_zeros()` 新增 4 个分母键 `("ms", assume, mode)`；叶子每张有役和牌张累加 `ms += p`；非叶子先按
  `chosen[("sc", assume, mode)] = max(kids, key=lambda g: g[("sc", assume, mode)])` 选分支（打牌层 argmax 就是它），再 `out[("sc",…)] += p × chosen[("sc",…)]`、`out[("ms",…)] += p × chosen[("ms",…)]`；
  新增 `_pick_score(nodes, assume, mode)`：`ms <= 0 ⇒ 0.0`，否则 `sc / ms`；`_assign_all` 的 6 个打点项改用它 ⇒ **帧级打点 = 和牌前提下的条件期望（单位：点）**，帧级仍按 `SC` 在 3 个 keep 里取最大。
- 例（`expect_example.md` 那个帧，`max_shanten=2`）：`furo_ron_score` = `furo_tsumo_score` = **1.478163 / 0.000448 = 3300.0**；`damaten_ron_score` = **2.187383 / 0.000523 = 4185.7142857**；
  `damaten_tsumo_score` = **3.344532 / 0.000672 = 4977.7777778**；6 个枚数项与 best 口径完全不变（0.252632 / 0.378947 / 0.421053 / 0.042105…）。
  三级节点都满足 `打点 = SC / MS`：叶子 L1 门清自摸 `361.702128 / 0.063830 = 5666.67`、13 张中间节点 `23468m2278p2346s` 门清自摸 `27.681971 / 0.005375 = 5150.0` ⇒ 多和牌张的叶子就是「各张得点的概率加权平均」。
- 跟随改动：`test\expect_test.py` 期望值全部改成归一化结果（嵌张默听自摸 1100、両面默听荣和 1000 / 自摸 1500、副露碰發 1000 / 1100、宝牌用例 1500 / 2100；`node_keys()` 20 键；
  `ref_leaf` / `ref_frame` 改成累加 `[Σp·gain, Σp]` 再相除；新增 `_pick_score` 与分母 0 的断言）⇒ **63 项全绿**。
- 根目录 `expect_example.md` 同步重写相关小节（当时 **19810 B / 314 行 / 纯 LF**，m02512 后为 24770 B / 345 行，见 13.9；m02647 后为 27983 B / 370 行，见 13.10）：§1 加打点定义、§2 表的打点行改成 3300.000000 / 4185.714286 / 4977.777778、§3.5 改「先归一化、打牌层按未归一化 `SC` 取 argmax」、
  §4.3 补叶子的 `SC / MS`、§5.3 重写为三级 `SC / MS` 展开、§6 改「20 个内部键」（m02512 后为 24 个，见 13.9）、§7 口径同步。

### 13.9 立直 / 默听两套打点假设（用户 m02512）

- 用户指出：原实现里「未立直的门清帧 `riichi_*` 恒 0」是错的。正确规则：**本帧已经副露（吃 / 碰 / 槓）⇒ 跳过立直这两项（听牌时不可能满足立直要求，记 0）；否则一律按「保持门清到听牌、在听牌时宣布立直」算 `riichi_*`，另外再按「不宣布立直」算 `damaten_*`**；得点计算忽略偶发 / 特殊役（与判别器的起和役门槛同一套口径）。
- 实现（`mjscore/expect.py`，当时 519 行 / 26128 B；m02647 后 573 行 / 29522 B，见 13.10）：
  - 常量：`RIICHI_ASSUME = "riichi"`、`DAMATEN_ASSUME = "damaten"`、`MENZEN_ASSUME = "menzen"`（`menzen` 只留给门清那 2 个枚数键）；`ASSUMES = (FURO_ASSUME, RIICHI_ASSUME, DAMATEN_ASSUME)`、`MENZEN_ASSUMES = (RIICHI_ASSUME, DAMATEN_ASSUME)`。
  - `_eval(counts, kind, tsumo, assume)` 的映射：`FURO_ASSUME ⇒ (state=FURO, riichi=0, menzen=False)`；`RIICHI_ASSUME ⇒ (state=RIICHI, riichi=self.riichi or 1, menzen=True)`（本帧真的已经立直就沿用它自己的番数，両立直 = 2）；`DAMATEN_ASSUME ⇒ (state=DAMATEN, riichi=0, menzen=True)`。起和役门槛侧 `min_yaku_ok` 对 `state == RIICHI` 直接放行（立直本身是役），`DAMATEN` 的荣和必须有真役。
  - 节点键由 20 → **24 个**：枚数 12（副露 4 项 × 2 模式 × sum/best + 门清 2 项 × sum/best，键名仍是 `MENZEN_ASSUME`，与前两轮一致）+ 打点分子 6（`("sc", assume, mode)`：副露 2 + 立直 2 + 默听 2）+ 打点分母 6（`("ms", assume, mode)`）。
  - 叶子门清段外层改成 `for assume in MENZEN_ASSUMES:`；非叶子仍对每个 `("sc", assume, mode)` 各自在打牌层取 argmax，`("ms", assume, mode)` 跟着这条分支走；`_assign_all` 的门清 4 个打点项分别写 `SCORE_KEYS[(RIICHI, mode)]` / `SCORE_KEYS[(DAMATEN, mode)]`；`compute()` 的「已经和牌」分支同样写这两条。
- 一个明确的取舍：**本帧已经宣布立直时，`damaten_*` 也照样计算**（口径 = 「假想这一帧不宣布立直」，两套假想对称、不特判）。若要改成「已立直帧的默听项记 0」，只需在 `_assign_all` 与和牌分支各加一行判断。
- 例子帧（同 13.7 / 13.8，`data_extra\2026091422gm-00a9-0000-c6933e45.xml`，`max_shanten=2`）：`riichi_ron_score` **6333.333333**、`riichi_tsumo_score` **8055.555556**（此前恒 0）；`furo_*`（3300.0）、`menzen_tenpai_*`（0.378947 / 0.421053）、`damaten_*`（4185.714286 / 4977.777778）与 best 口径的 6 个枚数项完全不变。keep 级五个打点键：`1.4781634938 / 0.0004479283 = 3300`、`5.4124673386 / 0.0006718925 = 8055.5555556`、`4.2553191489 / 0.0006718925 = 6333.3333333`、`3.3445315416 / 0.0006718925 = 4977.7777778`、`2.1873833520 / 0.0005225831 = 4185.7142857`。
- 测试：`test\expect_test.py` 63 项 → **66 项全部通过 / 失败 0**（23.4 s，`py_compile` exit 0）。新增 / 改动的断言：`h1`（未立直、听 6s）`riichi_ron_score == 1300` / `riichi_tsumo_score == 2000`；`h2`（听 4s / 7s）`2000` / `2700`；已立直帧 `state_for(h1, riichi=True)` 的 `riichi_ron_score == 1300` 且 `damaten_tsumo_score == 1100`（证明已立直帧也填默听项）；`node_keys()` 断言改 24 键；section3 / 3b / 3c 的假设列表改成 `[FURO] + [RIICHI, DAMATEN]` 并逐键对拍，`ref_leaf` 新增 `assume` 与 `all_waits` 参数。
- 文档：`expect_example.md` 同步重算并扩写（**24770 B / 345 行 / 纯 LF**）——§1 打点定义（两套假想各算一遍）、§2 表的两个立直项（`6333.333333` / `8055.555556`，并注明「本帧自己没宣布立直，`riichi_*` 照样有值；只有本帧已经副露才跳过」）、§3.6 由「两种假设」改成 `### 3.6 三种假设（有副露 / 立直 / 默听）`、§4.3 打点 bullet（三种假设各数一遍）、§4.4 表扩成 6 列 + 役的构成表 + 三个算点示例（新增「立直自摸 5 番 20 符 ⇒ 封顶満貫 base 2000 ⇒ 4100 + 2100×2 + 1000 = 9300」）、§5.3 整段重写为三级 `SC / MS`（叶子 `ul = 94` / 中间节点 `ul = 95` / keep `ul = 96`，每级都列 5 个打点键）、§6 改「24 个内部键」、§7 新增立直 / 默听两套假想的说明；文中每个数字都与模块逐项核对一致。

### 13.10 听牌枚数 / 绝对枚数也改成归一化条件期望（用户 m02647）

- 用户指出：**枚数要像期望打点一样，把「到达听牌状态」的叶子概率归一化后再加权**：
  `枚数 = Σ_听牌状态 [ p(叶子) / Σ p(听牌叶子) ] × 该状态「满足起和役的和牌张数」`——枚数隐含的前提是**已经听牌**，
  「达到听牌状态」的概率本身不该乘进枚数（那是「听牌强度」要算的量）；打牌的选择仍然按 `argmax{ p(打完的后继状态 → 听牌状态) × 枚数 }`。
- 口径：分母 = **所有到达的听牌叶子**（含该假设下无役、枚数 0 的听牌状态）⇒ 枚数 = `E[枚数 | 到达听牌]`，与打点 `E[得点 | 和牌]` 同构。
  若用户想要 `E[枚数 | 有役听牌]`，把叶子的 `("tq", …)` 改成「该假设下有和牌张才记 1.0」即可（一行）；本帧副露四项会从 `0.252632 / 0.084211 = 3.0` 变成 `0.252632 / 0.063158 = 4.0`（**用户已在 m02766 确认取后者**，见 13.11）。
- 实现（`mjscore/expect.py`，现 **573 行 / 29522 B / 纯 LF**；`mjscore/agari.py` 未动）：
  - `_zeros()` 的节点内部键 24 → **36 个**：枚数分子 `("tp", 假设, 口径, …)` 12 + 枚数分母 `("tq", 假设, 口径, …)` 12 + 打点分子 `("sc", 假设, 模式)` 6 + 打点分母 `("ms", 假设, 模式)` 6。
  - 叶子（`d == 0`）：写完 `("tp", 假设, agg, …) = 枚数` 之后紧接写 `("tq", 假设, agg, …) = 1.0`（叶子就是听牌状态；起和役只过滤分子的枚数 ⇒ 叶子比值仍是枚数本身）。
  - 进张层：`("tp", …)` / `("tq", …)` 与 `("sc", …)` / `("ms", …)` 分开走 —— `sum` 口径 `out[kk] += p × Σ kids[kk]`；`best` 口径先用 `("tp", 假设, "best", …)` 的 argmax 选分支（`chosen` 里补 `("tp"/"tq", …, "best", …)` 两个键），再 `out[kk] += p × chosen[kk][kk]`。
  - 新增 `Expect._pick_tenpai(nodes, key_num, key_den, agg)`：`sum` ⇒ 分子 / 分母各自求和后相除，`best` ⇒ 按**分子**挑 keep 再取该 keep 的分子 / 分母；分母 ≤ 0 ⇒ 0.0。
  - `_assign_tp(feats, alt, nodes, keys, out_key)` 签名改为接收 4 元组 `(分子 sum, 分母 sum, 分子 best, 分母 best)`；`_assign_all()` 两处调用（副露 4 项、门清 2 项）改造；`_pick_best` 变成无人调用（保留）。
  - docstring 第 4 条重写（枚数 = 条件期望 + `("tp")/("tq")` 含义 + sum/best 的打牌层 argmax 取分子）、第 5 条尾部「只有 6 个打点项做了归一化」改成「6 个枚数项同理」、第 8 条补「sum 口径先各自求和再相除」。
- 例子帧（同 13.7~13.9，`data_extra\2026091422gm-00a9-0000-c6933e45.xml`，14 张 `2468m22378p23346s`、`max_shanten=2`）：
  `furo_tsumo/ron_tenpai_expect` 与两个 `abs` 全 = **3.000000**（原 0.252632）、`menzen_tenpai_expect` = **4.500000**（原 0.378947）、`menzen_tenpai_abs` = **5.000000**（原 0.421053）；
  打点六项不变（`furo_*` 3300.0、`riichi_ron` 6333.333333 / `riichi_tsumo` 8055.555556、`damaten_ron` 4185.714286 / `damaten_tsumo` 4977.777778）；
  best 口径的 6 个枚数项现在也是 3.0 / 4.5 / 5.0（原 0.042105 / 0.063158 / 0.070175）。keep 级：分子 `TP` = 0.084211（副露）/ 0.126316、0.140351（门清），分母 `TQ` = 0.028070，比值 = 3.0 / 4.5 / 5.0；
  分子 / 分母按「Σp × 枚数」/「Σp」分别对 3 个 keep 求和（0.252632 / 0.084211 等）。
- 测试：`test\expect_test.py` 636 → **672 行 / 字符 26201 → 28248**，**66 → 70 项全部通过 / 失败 0**（23.6 s，`py_compile` exit 0）。
  跟随改动：`node_keys()` / 节点键标签 24 → 36；`ref_frame` 新增 `nums[(agg, mode, measure)] = [分子, 分母]`（`den = len(rows)` for sum / `1.0` for best）并在结尾相除；
  section3 断言叶子 `("tq", …) == 1.0`；section3b 的 sum 口径枚数改成 `sum(avs) / nkeep`、`sum(abss) / nkeep`（`nkeep = len(keep)`，best 不变）；section2 新增 4 条 `_pick_tenpai` 断言（`18/0.6 = 30`、`best = 20`、分母 0 ⇒ 0、听牌叶子 `TQ = 1.0`）。
- 文档：`expect_example.md` 重算并同步（现 **27983 B / 370 行 / 纯 LF**）——§1 新增枚数定义、§2 表的 6 个枚数行改成 3.000000 / 4.500000 / 5.000000 + 说明、§3.4 补打牌层 argmax 键（`SC` / `TP`）、§3.5 重写成「枚数与打点都先归一化」、§4.3 补「叶子 `TQ = 1.0`」与「Σ P 是枚数分母」、
  §5.1 / §5.2 改成分子 / 分母展开（`0.252632 / 0.084211 = 3.0`、`0.378947 / 0.084211 = 4.5`、`0.421053 / 0.084211 = 5.0`）、§5.3 末尾补 keep 级 `TP / TQ`、§6 改「36 个内部键」、§7 补枚数归一化与分母口径（待确认）。
- 回归范围：只改了 `mjscore/expect.py` 与 `test/expect_test.py`（`expect` 只被这一支测试直接引用），`agari / shanten / mjscore / feats / replay / store / cli` 未动。
### 13.11 枚数分母改成「有役听牌」（用户 m02766）

- 用户裁定：13.10 里问的分母口径取 **`E[枚数 | 有役听牌]`**——「区分副露 / 默听 / 立直就是为了对不同情况下的**有役听牌 / 和牌**进行区分」。
  于是叶子的枚数分母 `("tq", 假设, …)` 从「听牌叶子一律 1.0」改成 **「该假设 / 模式下存在过起和役门槛的和牌张才记 1.0，否则 0.0」**；
  分子不变（枚数本来就只数有役的和牌张）⇒ 无役的听牌状态既不进分子也不进分母。门清枚数项（`("tq","menzen",…)`）仍一律 1.0（门清自摸必有役）；
  打点项不受影响（`E[得点 | 和牌]` 本来就是同构口径）。
- 实现（`mjscore/expect.py`，573 → **576 行 / 23065 字符**）：叶子副露段改成
  `out[("tq", FURO_ASSUME, agg, mode, measure)] = 1.0 if got else 0.0`（`got` = 该假设 / 模式下过起和役门槛的和牌张）；
  docstring 第 4 条重写成「枚数 = 「**有役听牌**」前提下的条件期望（m02647；分母口径按 m02766 修订，与第 5 条同构）」。
- 例子帧（同 13.7~13.10，`data_extra\2026091422gm-00a9-0000-c6933e45.xml`，14 张 `2468m22378p23346s`、`max_shanten=2`）：
  `furo_tsumo/ron_tenpai_expect` 与两个 `abs` = **4.000000**（13.10 时 3.000000、m02647 前 0.252632），因为分母只算有役听牌叶子 L1 / L2 / L4 = **0.063158**
  （13.10 含无役的 L3 / L5 = 0.084211）；`menzen_tenpai_expect` = 4.500000、`menzen_tenpai_abs` = 5.000000（分母仍是 Σ P，不受影响）；
  打点六项不变；best 口径 6 个枚数项 = 4.0 / 4.0 / 4.0 / 4.0 / 4.5 / 5.0。keep 级：`TQ` = 0.021053（副露，只数有役听牌）/ 0.028070（门清）⇒ 0.084211 / 0.021053 = 4.0。
- 测试：`test\expect_test.py` 672 → **724 行 / 字符 28248 → 30852**，**70 → 73 项全部通过 / 失败 0**（23.5 s，`py_compile` exit 0）。
  跟随改动：新增独立参考 `ref_yaku_ok(e, counts, tsumo, assume=None)`（判「这个听牌叶子在该假设 / 模式下算不算有役听牌」，`agari.score` 抛 `ValueError` 即无役）；
  `ref_frame` 的分母改成「有役听牌叶子」的 Σ p（sum 口径）；section2 拆成四条断言（门清叶子 `TQ = 1.0` / 副露假设下无役叶子 `TQ = 0.0` / 断幺九叶子 `TQ = 1.0` / 吃 123s 叶子 `TQ = 0.0`）；
  section3 的 `tq` 检查改成逐键求参考值；section3b 的副露 sum 分母改成 `nfuro`（有役 keep 数，best 分支不用改 —— 分子 > 0 的 keep 必有役）。
- 文档：`expect_example.md` 17449 → **17886 字符 / 370 行 / 纯 LF**（§1 枚数定义改「有役听牌」、§2 表 4 个副露枚数行 3.000000 → **4.000000**、
  §3.5 分母说明、§4.3「Σ P 是门清分母 / 副露分母 0.063158」与叶子 `TQ` = 1.0 / 0.0、§5.1 `0.252632 / 0.063158 = 4.000000`、§5.3 keep 级 `TQ`、§7 的「待确认」改成「已确认 = `E[枚数 | 有役听牌]`」）。
- 回归范围：仍只改 `mjscore/expect.py`、`test/expect_test.py`、`expect_example.md`（+ 本文件）；`agari / shanten / feats / replay / store / cli` 未动。

## 14. 第 20 轮：立直家（他家）危险筋组数量 / 危险两面组数（`mjscore/danger.py`，用户 m02865）

### 14.1 要求与口径（用户 m02865）

- 取消「听牌强度」特征（与现有特征含义重复）。
- 新增两项特征（第二类特征的收尾；本轮只做计算，不接入 feats / DB / 界面）：

  | key | 显示名 | 取值 |
  | --- | --- | --- |
  | `riichi_others_danger_suji` | 立直家（他家）危险筋组数量 | -1 或 0..18 |
  | `riichi_others_danger_ryanmen` | 立直家（他家）危险两面组数 | -1 或非负整数 |

- **-1**：以当前摸牌者为主视角，其他家无人立直（即第一类特征「立直家（他家）数量」= 0）时两项都取 -1；
  有立直家时取非负整数（判定复用 `feats.is_riichi`，与第一类特征完全同口径）。
- **立直家的安全牌** = ① 该立直家打出过的所有牌（无论是否被其他家鸣走）
  + ② 立直动作发生后，场上任何一家打出过的牌（不包括暗杠）。
- **筋组**：m/p/s 中数字相差 3 的两种牌构成一个筋组，三种花色 x {1,4},{2,5},{3,6},{4,7},{5,8},{6,9} = 18 组；
  每组对应一种両面 = 构成筋组的两种牌中间间隔的两张牌（筋组 25m -> 両面 34m）。
- **危险筋组**：以下之一成立则该组（両面）**安全**，否则危险 ——
  ① 该筋组的两种牌里至少有一种是立直家的安全牌；② 主视角视野中（自身手牌 + 公共信息）该両面的两张牌至少有一种能看到 4 张。
  危险筋组数量 = 危险组计数（0..18）。
- **危险两面组数** = Σ over 危险筋组 of（両面第一张剩余张数 x 第二张剩余张数），剩余 = 4 - 主视角可见张数
  （加法原理 + 乘法原理；用户算例：筋组 14m 危险、看到 2 张 2m 与 1 张 3m => 両面 23m 共 2 x 3 = 6 组）。
- **多家立直**：危险 = 对**任意一家**立直家危险；安全 = 对**全体**立直家均安全
  （组安全 <=> ② 或「对每家立直家 X，X 的安全牌里都含该筋组的至少一种牌」）。
- **出牌序**：② 需要「立直动作发生后场上任何一家打出过的牌」，而 replay 的状态里只有各家自己的牌河顺序
  （river 条目没有全局序号）=> 新增 `DangerLog` 按事件顺序维护全局出牌序与各家立直位置。

### 14.2 实现（`mjscore/danger.py`，8050 B / 162 行 / 纯 LF）

- 常量：`SUJI`（18 组，元素 = `(筋组第一张 kind, 第二张, 両面第一张, 両面第二张)`）、
  `FEATURES`（key -> 显示名，key 沿用第一类特征 `riichi_others_n` 的命名风格）、`NAMES` / `KEYS` / `RANGES`。
- `class DangerLog`：`seq` = [(座位, 牌种)] 全局出牌序（含被鸣走的牌；暗杠不是出牌事件）；
  `reach_at` = {座位: 立直宣告时已发生的出牌数}；`feed(ev)` 与 `replay.apply_event` 同序调用；
  `after_reach(player)` = 该家宣告之后被任何人打出过的牌种集合。
  立直位置取 `REACH step="1"`（宣告）那一刻 —— step1 与 step2 之间恰好夹着 1 张别家的出牌，那张也算「立直动作发生后」。
- `round_log(game, round_index, ev_index=None)`、`riichi_others(state, seat)`（复用 `feats.is_riichi`）、
  `safe_kinds(state, player, log)`、`groups_detail(...)`（逐组明细，测试 / 调试用）、`values(state, seat, log)`、
  `values_at(game, round_index, ev_index, seat)`（回放到该帧再算，测试 / 单帧查询用）。
- 可见张数复用 `shanten.visible_counts(state, seat)`（自己手牌 + 四家副露（含暗杠）+ 四家牌河
  （被鸣走的那张算在副露里、不再算牌河）+ 宝牌指示牌），与向听 / 期望特征同口径。
- 有他家立直而没给 `DangerLog` 时抛 `ValueError`（避免悄悄按「立直后没有出牌」算错）。

### 14.3 验证结果（全绿）

- `test/danger_test.py`（16721 B / 370 行）：**29 项全通过 / 0.9 s**，4 节 ——
  ① 筋组表（18 组、不重复、両面 = 中间两张、每花色 6 组、特征名 / 取值域）；
  ② 手算用例（其他家无人立直 => -1 且与第一类特征一致、只有自己立直 => 仍 -1、安全牌只有 4z 时 18 组全危险
  且筋组 14m 的両面 23m = 2 x 3 = 6（用户算例）、安全牌 {3m, 9m} => 16 组 / 236、立直动作**之前**别家的 9m 不算安全牌
  => 17 组 / 252、看到 4 张 4p => 14 组 / 204、被鸣走的牌仍是安全牌、两家立直各挡一个筋组 => 18 组全危险、
  两家都打出过 3m => 17 组 / 246、没给 DangerLog 要报错）；
  ③ 全量语料 71 牌谱 / **37254 帧**（有他家立直 6693、多家立直 506；立直宣告 545 次）与独立参考实现
  （安全牌改走「各家牌河后缀」）**逐帧 0 差异**，不变量 0 违规，另核对「全局出牌序 vs 四家牌河」逐牌种一致；
  ④ `values_at()` 一次性取数与逐帧流式取数抽样 192 帧 0 差异。
- 帧数 37254 = 向听 / 期望测试的 37533 - 279（自摸和了的那一帧不打点，与 `feats.records_for_round` 一致）。
- 分布（6693 个有他家立直的帧）：危险筋组数量 0..17 ——
  `[0:1, 1:48, 2:61, 3:148, 4:295, 5:524, 6:526, 7:706, 8:700, 9:768, 10:676, 11:651, 12:596, 13:469, 14:306, 15:137, 16:67, 17:14]`
  （语料里没有 18）；危险两面组数 min 0 / max 219 / 平均 71.21。
- 本轮改动后重跑其余测试：`agari_test` 182 项、`expect_test` 73 项、`shanten_test` 92 项（语料 37533 帧 / 145.23 s /
  3.870 ms/帧）、`mjscore_test` 119 项全部通过；`node test\selftest.js` / `uitest.js` / `apptest.js` 全部通过。

### 14.4 未做 / 后续

- 两项特征还没进 `feats.FEATURES`（打点行仍是 16 个第一类特征）、没入库、没上前端。接入时要在
  `feats.records_for_round` 的逐事件循环里加 `log.feed(ev)`，并把 `DangerLog` 传进 `make_record` / `extract`。
- 偶发役（一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底）仍未纳入；「听牌强度」已按用户 m02865 取消。

### 14.5 本轮踩到的坑

- 见第 19 节第 49~51 条（合成算例的可张数别忘立直家自己的牌河、全局出牌序用 `DangerLog`、立直宣告取 `REACH step="1"`）。

## 15. 第 21 轮：第二类特征接入检索 + 帧特征面板 + 分析进度条 + 牌谱下载（用户 m02959）

用户 m02959 的四项要求：① 把 17 个第二类特征接入前端「牌谱检索」（与第一类特征同位置、同处理逻辑）；
② 牌谱检索里任何形式的当前帧图片展示，边上要标明全部一类和二类特征的名称与取值，用于检索的条目换成醒目颜色；
③ 牌谱分析耗时较长，界面要实时给出「已完成数 / 总数」进度条，并能实时显示当前正在分析的牌谱特征码；
④ 新增「牌谱下载」功能，入口与牌谱播放 / 分析 / 检索并列（可输入单个 url，或选一个「每行一个 url」的本地文本文件；
必须先指定本地存储地址，默认 `data/paipu/<带时间戳的目录名>`，`data/paipu` 固定、子目录名可自定义；同名覆盖；显示待下载 / 成功数量）。

### 15.1 交付物

| 文件 | 规模 | 说明 |
| --- | --- | --- |
| `mjscore/feats.py` | 286 行 | 特征注册表 16 → 33 项；`SECOND_FEATURES = SHANTEN_FEATURES + EXPECT_FEATURES + DANGER_FEATURES`、`SECOND_KEYS`、`second_class(st, seat, log=None)`、`make_record(..., log=None)`、`records_for_round(game, round_index, log=None)`（内部建 `danger.DangerLog` 并逐事件 `feed`） |
| `mjscore/store.py` | 367 行 | `SCHEMA_VERSION = 3`（frame 表新增 17 个 `s_*` 列，float → `REAL`）；`parse_cond()` 支持实数（精确 / 区间 / 列表 / 比较）；新增 `frame_feats(conn, log_id, round_index, frame_index, seat=None)` |
| `mjscore/cli.py` | 553 行 | 全局进度（`PROGRESS` + `threading.Lock` + `progress_reset / progress_update / progress_snapshot`）；`python_records` 逐局报进度；`second_class_pass / merge_second_class / fill_second_class`（`--tool node` 时第一类由 node 打点、第二类 17 项由 Python 补齐并给一行警告）；`analyze()` 变薄包装，收尾只写 running=False |
| `mjscore/server.py` | 344 行 | 新增 `GET /api/analyze-progress`、`/api/download-progress`、`POST /api/frame-feats`、`/api/download` |
| `mjscore/download.py` | 284 行 | 新建：根脚本的 `extract_log_id / build_download_url / fetch_log / looks_like_mjlog / save_log` 搬进来 + `paipu_root / default_subdir / resolve_out_dir / read_url_lines / read_url_file / collect_urls / run_download / start_download` 与下载进度 |
| `download_tenhou.py` | 135 行 | 改成薄 CLI，核心复用 `mjscore/download.py`；默认输出目录仍是 `data/` |
| `mjscore/danger.py` | 164 行 | 修掉与 `feats` 的循环导入（`riichi_others` 里延迟 `from . import feats`） |
| `js/mjsfeat.js` | 212 行 | `FEATURES` 追加 17 项（3 个 int 向听 / 12 个 float 期望 / 2 个 int 危险），`extract()` 仍只产出 16 项 |
| `index.html` | 292 行 | 第 5 个页签「牌谱下载」+ 首页卡片 + `#featPanel`（当前帧特征）+ `#anProgressBox` + `#view-download` |
| `js/app.js` | 1360 行 / 54156 B | `VIEWS.download`、`featHint` 实数分支、`frameSeatOf()`、`FeatPanel / renderFeatPanel / syncFeatPanel / markUsedFeatures`、`anProgress*` 轮询、`Dl`（下载视图逻辑） |
| `style.css` | 625 行 | `.feat-panel` / `.feat-row.used` / `.progress-box` 等 |
| `test/mjscore_test.py` | 649 行 | 33 特征 / schema v3 / 4 个新接口 / 下载离线用例（新增 2c、4d 节） |
| `test/apptest.js` | 1144 行 / 70357 B | 新增第 8.10 节（帧特征面板 / 分析进度条 / 下载视图） |

### 15.2 第二类特征接入检索

- `feats.FEATURES` 现为 33 项 = 16 个第一类 + 17 个第二类（3 向听 + 12 期望 + 2 危险），`SECOND_KEYS` 就是后 17 个 key 的顺序；
  `second_class(st, seat, log=None)` 一次算出 17 项，`make_record(..., log=None)` 把 16 + 17 合并成一行。
- `--tool node` 的路径：JS 侧不实现第二类特征，`cli.second_class_pass()` 在对应用 python 逐帧补算 17 项，
  `merge_second_class()` 按 `(log_id, round_index, ev_index, seat)` 合并，缺行直接 `ValueError`；成功时给一行警告
  「`--tool node`：第一类特征来自 node，第二类 17 项由 python 补齐（js 侧没有实现）」。
- 库结构：`frame` 表 58 列（定位列 + 16 个 `f_*` + 17 个 `s_*` + 元数据），`feature_def` 33 行；
  `SCHEMA_VERSION = 3` ⇒ 旧库会被 `check_version()` 拒绝，需要 `python analyze.py <牌谱路径> --delete-db <库名>` 后重建。
- 检索条件：`store.parse_cond()` 对 `kind == "float"` 走实数分支（`1.5` / `0-1.5` / `0,1,2.5` / `>=3`），
  前端 `featHint()` 同步给出同一套提示；枚举特征仍是 `<select>`，其余仍走文本框。

### 15.3 前端（帧特征面板 / 分析进度条 / 下载视图）

- **当前帧特征面板**：回放视图右侧新增 `#featPanel`（与 `#eventList` 并列），按 `FEATURES` 顺序列出 33 行「特征名 = 取值」；
  取值来源 —— 条目模式（从检索结果跳进来）走 `POST /api/detail {idx}`，手动播放走
  `POST /api/frame-feats {log_id, round_index, frame_index, seat, db_name}`；
  座位判定抽成 `frameSeatOf(st)`（摸牌帧 = `st.drawn.player`；吃 / 碰帧 = 上一事件的 `ev.player`），与 `frameKeyText()` 同一套逻辑。
  检索用到的特征 key（`markUsedFeatures()` 读 `Sc.conds`）加 `.used` 类：左侧强调色竖条 + 淡色底 + 名字与取值变色。
  面板按 key 缓存并用 `seq` 丢弃过期响应；非打点帧（没有座位可判）显示提示而不是空列表。
- **分析进度条**：`doAnalyze()` 启动后每 500 ms 轮询 `GET /api/analyze-progress`，
  文本 = 「已完成 X / Y 个牌谱 ｜ 当前 <特征码> ｜ 局 a/b ｜ 打点 N 行 ｜ t s ｜ 阶段：…」，条宽 = `files_done / files_total`；
  成功 / 失败都停轮询并把结果写进 `#anMsg`。`/api/analyze` 本身仍是同步阻塞调用，进度来自服务端全局快照。
- **下载视图**：第五个页签「牌谱下载」。两种输入二选一（单 url 文本框 / 本地文本文件经 FileReader 读入，逐行处理、
  跳过空行与 `#` 注释）；存储地址默认时间戳子目录（`YYYYMMDD-HHMMSS`，`data/paipu` 固定、子目录名可自定义，另有「用默认」按钮）；
  下载后每 400 ms 轮询 `GET /api/download-progress`，条宽 = `done_n / total`，文本给「已下载 d / t ｜ 成功 ｜ 失败 ｜ 当前 ｜ t s」；
  完成后写 `#dlCounts`（待下载 / 成功 / 失败）并用 `/api/scan` 列出该目录，顺便把分析视图的来源目录预填成 `data/paipu/<子目录>`。

### 15.4 牌谱下载的存放位置约束

- `download.resolve_out_dir(sub)` 只接受 `data/paipu` 下的**子目录名**：剥掉 `data/paipu/` 前缀后为空则用时间戳；
  出现绝对路径、`..` 或路径分隔符一律 `ValueError`（文案「存储地址只能是 data/paipu 下的子目录名（不含路径分隔符或 ..），收到「%s」」）。
- 因此 `data\*.xml`、`analyze.py data`、`/api/scan?dir=data` 这些既有路径完全不受影响；下载下来的牌谱都在 `data/paipu/<子目录>/`，
  要分析它们就把分析视图的来源目录指到那里（前端下载完成后已自动预填）。
- `save_log(..., overwrite=True)` 同名覆盖；`run_download()` 逐条独立成败，返回 `{dir, total, saved, failed, skipped, results}`，
  每条 entry = `{input, ok, log_id, path, bytes, written, error}`；下载内容不像 mjlog 会记 `DownloadError("下载内容不像 mjlog 牌谱（%d 字节）")`。

### 15.5 验证结果（全绿）

- `test\mjscore_test.py`（649 行，v3 口径）→ **180 项全通过**：含 2c 节（33 特征 / 17 个 `s_*` / 起和役与危险特征的横切不变量）、
  4d 节（下载模块离线用例）、第 5 节（4 个新接口 + 进程内真起 `make_server`、下载失败路径 `failed 1`）。
  本轮踩到的两处测试自身问题：① 向听取值断言误用列名 `s_shanten_*`（应为特征 key `shanten_*`）；
  ② `/api/analyze` 的 `urlopen(timeout=15)` 对现在的长跑接口必然超时。
- `node test\apptest.js` → **264 OK / 0 FAIL / 全部通过**（新增第 8.10 节：帧特征面板 / 分析进度条 / 下载视图）。
- 其余：`test\agari_test.py` 182 项、`test\expect_test.py` 73 项、`test\shanten_test.py` 92 项；
  `node test\selftest.js` / `test\uitest.js` 全绿；`node --check` 全部 `js\*.js` 通过。
- node / python 双路径交叉校验（单牌谱 11 局）：530 行 × 41 列 field diffs = 0（17 个 `s_*` 也逐行一致）。
- 规范库体检：`data\db\paipu.sqlite` 与 `data\db\test.sqlite` 均 3121152 B、schema 3；
  `frame` 58 列 / 2786 行、`frame_full` 13930、`feature_def` 33、`source` 5；17 个 `s_*` 无 NULL；
  `s_shanten_mentsu` 分布 `{0: 462, 1: 707, 2: 887, 3: 730}`；`s_riichi_others_danger_suji == -1` 共 2216 行。
- 真机下载（联网）：单 url → `data/paipu/s21probe/2026082919gm-00a9-0000-4e40cd3e.xml`（16408 B）；
  文本形式（含注释行 / 空行 / 裸特征码）→ 2 个文件、`done_n=2 / total=2 / saved=2 / failed=0`。

### 15.6 本轮踩到的坑

- 见第 19 节第 52~57 条（路由前缀顺序、假 DOM 没有 `.style`、残留 `setInterval` 让测试进程不退出、帧特征面板缓存、
  `mjscore_test.py` 的 float 值域分支与 `SCHEMA_VERSION`、长跑接口的超时值）。
- 另记一条口径：`--tool node` 时第二类 17 项由 Python 后处理补齐（因此 node 库的 `s_*` 也一定有值），会带一条 warning。

### 15.7 后续

- 听牌强度按 m02865 取消；偶发 / 特殊役（一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底）仍未纳入起和役与打点。
- 第二类特征让全量分析变慢（5 个牌谱约 11 分钟），所以本轮加了进度条；若要多牌谱批量分析，
  还应支持按需只算部分特征。
- 「全部浏览」仍一次取全 2786 行，条目再多应改成按页加载。

## 16. 第 22 轮：bug 修复 + 版本号 v0.1.0 + 扩充现有数据库 + readme（用户 m03580）

### 16.1 要求（用户 m03580 的 7 条）

1. 修 bug：用新库 `20261007_test.sqlite` 检索、点条目后右侧特征面板报「读取数据库文件失败」，且指向已删除的 `paipu.sqlite`；并确认检索范围是否指向新库（用户觉得结果偏少）。
2. 加版本号 **v0.1.0**（界面 + 代码；以后按用户指令改大 / 中 / 小版本）。
3. 「牌谱分析」删除打点工具选择（默认 node 与 python 同时使用）。
4. 解释 `--full`（同时写入原始数据）勾选与不勾选的效果。
5. 分析进度条删除「打点 N 行」与「阶段：解析牌谱 / 打点（node）/ 打点（第二类）/ 写库 / 完成」两条。
6. 新增「扩充现有数据库」：与「输入数据库名」互斥；库内要存生成它的**全体牌谱特征码**（扩充时忽略特征码相同的牌谱）与**软件版本**（版本匹配才能扩充 / 加载）。
7. 重写 `readme.md`（软件功能、配置与使用方法、依赖包；Win10 / Win11 从零可用）。

### 16.2 bug 根因（①）

- `js\app.js` 的 `syncFeatPanel()` 在「点击的条目正好是当前帧」（`sameItem`）时只发 `POST /api/detail {idx}`，**没带 db / db_name** ⇒ `mjscore\server.py` 的 `_db_of()` 回落到 `cli.DEFAULT_DB_NAME`（`"paipu"`）⇒ `data\db\paipu.sqlite` 不存在（用户已删）⇒「数据库文件不存在」。
- 修法：先把 `dbKey` 算出来，`body.db` / `body.db_name` **在 `sameItem` 分支之前**就写入，`/api/detail` 分支照旧；特征面板缓存键也带上 `dbKey`。
- 「结果偏少」不是范围错误：用截图里的 12 条条件直接查新库，逐条命中 29766 / 27616 / 35162 / 6187 / 21755 / 35108 / 9773 / 36971 / 30006 / 3027 / 1365 / 1589，AND 结果 = **5**，与 `store.query()` 的 `total` 一致（库内 37254 行）⇒ 条件本身很严（AND 越多越少）。

### 16.3 版本号 v0.1.0（②）

- `mjscore\__init__.py`：`APP_NAME = "天凤牌谱分析"`、`__version__ = "0.1.0"`。
- `mjscore\store.py`：`meta` 新增 `app_version`（`META_KEYS` 加键）；`check_version()` 重写 —— ① 结构版本仍必须等于 `SCHEMA_VERSION`；② 有 `app_version` 记录时**必须与当前 `__version__` 一致**，否则抛「数据库由软件版本 %s 生成…请改用原版本软件，或删除后重新分析」；③ 没有记录（v0.1.0 之前建的库）按兼容处理、返回 False。新增 `app_version_of(conn)` / `source_ids(conn)` / `totals(conn)`。
- `mjscore\cli.py`：`--version` → `天凤牌谱分析 v0.1.0`；`list_dbs()` 每项加 `app_version` / `compatible`；`--list-dbs` 打印版本（不匹配加「⚠ 版本不匹配」）。
- `mjscore\server.py`：`server_version = "mjscore/%s"`；`/api/health` 与 `/api/features` 都带 `name` / `version`。
- 前端：页眉 `#appVer` 显示 `v0.1.0`；数据库下拉 / 列表显示版本与「⚠ 版本不匹配（不能扩充 / 加载）」。

### 16.4 扩充现有数据库（⑥）

- `cli.analyze(..., extend=False)` / `_analyze(...)`：`fixture` 与 `extend` 互斥（报「fixture 入库不能与扩充模式同时使用」）；库不存在报「要扩充的数据库不存在…请先新建数据库」；先 `store.connect(create=False)` 校验版本，再取 `store.source_ids(conn)` 作为已有 **log_id** 集合；解析前按 `mjlog.log_id_of(f) in existing` 分流，全部重复时抛「这 N 个牌谱都已经在数据库里了，没有需要扩充的新牌谱」；空库给一条「本次按新建处理」的 warning；写库时 `meta.app_version` 覆盖写、`full` 取「本次 or 原有」、`last_batch` 记 `extend` / `skipped`；返回 dict 增 `extend` / `skipped`（log_id 列表）；CLI 增 `--extend`，人读结果多一行「扩充模式：跳过已入库牌谱 N 个」。
- 前端：「新建数据库 / 扩充现有数据库」两个 radio 互斥（扩充时禁用库名输入框），扩充下拉列出 `名字（N 行 · vX.Y.Z）`，不兼容的库 `disabled`。
- 判重口径 = **牌谱特征码**（`log_id` = 文件名去掉 `.xml`）；`source` 表本来就以 log_id 为主键。

### 16.5 其余界面改动（③④⑤）

- 删除 `#anTool`（HTML / JS / apptest 同步删）；后端 `tool` 参数保留（默认 `auto`）。
- 进度条不再显示「打点 N 行」与「阶段：…」，改为可选显示「跳过已入库 N 个」。
- `--full` 说明写进界面（`<details>` 折叠 + `store.FULL_NOTE` 动态填充）与 readme：勾选 = 除 33 个特征值外还把该帧原始数据（手牌 / 副露 / 宝牌指示牌 / 分数 / 牌谱路径）写进 `frame_full`，以后新增特征可只按原始数据重算、不必重新解析 XML（库约大一倍、写库略慢）；不勾选 = 只写 33 个特征值（库小、写快），新增特征只能重新分析全部牌谱。

### 16.6 readme（⑦）

- 重写 `readme.md`（17579 B / 295 行 / 纯 LF）：四个页签功能表、检索条件四种写法、33 个特征清单、Win10 / Win11 从零安装（python.org 下载并勾 Add python.exe to PATH / Node 可选 + 查找顺序 / 放非中文路径 / `python server.py` → http://127.0.0.1:8770/，不要用 `file://`）、使用流程（下载 / 分析入库（新建 vs 扩充 + --full）/ 检索浏览 / 回放快捷键）、数据库结构与版本匹配表、命令行速查、常见问题、依赖（无第三方包）/ 目录 / 测试命令 / 版本号规则。

### 16.7 验证结果（全绿）

- `test\apptest.js` **276 OK / 0 FAIL / 全部通过**（`node --check` 通过）：假服务新增 `/api/features`，`/api/dbs` 带 `app_version` / `compatible`，`/api/analyze` 回显 `extend`；新增 (4b) 节断言（`#anTool` 已删 / 版本显示 / `--full` 说明 / 扩充下拉禁用不兼容库 / 扩充模式目标库与请求体 `extend:true` 且不含 `tool` / 进度文本不含「阶段」「打点」）；条目模式断言额外校验 `/api/detail` 请求体带 `db`（即 ① 的 bug 修复点）。
- `test\mjscore_test.py` 新增第 7 节（v0.1.0 / 扩充 / 版本校验）：`meta.app_version`、`app_version_of`、版本不匹配拒绝打开（人为改 `0.0.9`）、无 `app_version` 的老库按兼容、扩充的重复 / 缺库 / fixture 冲突三种报错、扩充只分析新牌谱并跳过已入库（`logs = 1 / skipped = 2`）、空库扩充按新建处理、`/api/health` 与 `/api/features` 带版本、`/api/dbs` 每项带 `app_version` / `compatible`、`POST /api/analyze` 扩充全重复 400、版本不匹配的库 `/api/detail` 400。
- **全量结果：通过 208 项 / 失败 0 项**（driver `exit=0 wall=3170.9 s` ≈ 53 分钟；跑法见第 19 节第 58 / 59 条）。首轮跑的 204 / 4 全是新增断言插错位置造成的假失败（见第 19 节第 67 条）。
- 本轮测试自身修掉的 4 处：① 造 `__mjtest_ver__` 时补 `set_meta(..., "schema_version", ...)` + `commit()`（见第 19 节第 64 / 65 条）；② 读不匹配库的 `app_version` 改 raw `sqlite3`（`store.connect()` 会抛）；③ 两处 `list_dbs` 断言排除 `__mjtest_ver__`；④ 扩充 / 版本不匹配两条断言移到进度断言之后并改名 `st5 / d5`。
- `test\selftest.js` / `test\uitest.js`：牌谱搬到 `data\paipu\20261007-165558\` 后它们静默扫到 0 个牌谱（假通过），改为递归 `walkXml` + 按 5 个基础牌谱特征码挑选 ⇒ selftest `files 5 / rounds 58 / frames 5824 / draws 2701 / discards 2776 / calls 117`、`[OK] 全部不变量通过`；uitest `全部通过`（见第 19 节第 63 条）。
- 其余套件：`test\danger_test.py` 29 项 / 1.3 s、`test\agari_test.py` 182 项 / 1.3 s、`test\expect_test.py` 73 项 / 22.0 s、`test\shanten_test.py` 92 项 / 135.69 s（37533 帧、3.615 ms/帧、四家外推 417.4 s）。
- 顺带修掉两个与扩充 / 版本校验相关的问题：`cli.list_dbs()` 读不兼容库的 meta 不再走 `store.connect()`（改 raw `sqlite3`），否则 `/api/dbs` 丢 `app_version` 并被误判成兼容；`store.connect()` 版本校验失败时先 `conn.close()` 再抛，否则 Windows 上该 sqlite 文件一直被占（删不掉 / 覆盖不了）。
- `style.css` 追加 `.app-ver` / `.hint > p` / `#anExtendRow select` / `#anExtendInfo`（19871 → 20110 B / 629 行）。
- 用户数据库 `data\db\20261007_test.sqlite`（35311616 B；frame 37254 / source 71 / schema 3 / 无 `app_version`）按兼容处理，未被改动。

### 16.8 未做 / 后续

- 旧库（无 `app_version`）要到下一次用 v0.1.0 分析（或扩充）时才会补写 `app_version`。
- 偶发 / 特殊役（一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底）仍未纳入起和役与期望打点。

## 17. 第 23 轮：扩充库 bug 修复 + 向听数 `>=3` 展示 + 作者信息 + 项目结构整理（用户 m04115）

### 17.1 要求（用户 m04115，五项）
1. 修 bug：选中用 71 个牌谱建的 `20261007_test.sqlite` 后点「扩充现有数据库」报「分析失败：要扩充的数据库不存在：…\data\db\20261007_test.sqlite（请先新建数据库）」。
2. 与向听数有关的特征，内部取值为 3 时对外**一律显示 `>=3`**（代码注释、界面、文档同步）。
3. 在代码与文档的相关位置添加作者信息：**Zumma Crystal** / 邮箱 **z1025zzsg@sohu.com**。
4. 整理项目结构：根目录除 `server.py` 外不暴露其他源码文件。
5. 上传 GitHub，仓库名 `tenhou-paipu-analysis`。
补充（用户 m04182）：向听数的**检索条件**仍接收整数 / 列表 / 区间 / 比较，内部取值范围是 `{-1,0,1,2,3}`，直接用内部取值匹配（输入 `3-5` 应检索出内部值 3 的帧）；`>=3` 的修改**只涉及展示**，不涉及计算逻辑。

### 17.2 bug ①：「扩充现有数据库」报「数据库不存在」
- 根因：`mjscore/cli.py` 的 `db_path_of()` 对库名**无条件追加 `.sqlite`**，而前端扩充下拉的 value 带扩展名（`20261007_test.sqlite`）⇒ 实际路径成 `20261007_test.sqlite.sqlite` ⇒ 报「不存在」。
- 修法：`db_path_of(db=None, db_name=None)` —— 显式路径直接用；否则名字不以 `.sqlite` 结尾才追加；`mjscore/server.py` 的 `_db_of(payload)` 纯库名分支改调 `cli.db_path_of(None, name)`，避免两份解析器分叉。
- 实测：`POST /api/analyze {paths:["data/paipu/20261007-165558"], db_name:"20261007_test.sqlite", extend:true}` → 400「这 71 个牌谱都已经在数据库里了，没有需要扩充的新牌谱」（0.02 s）；`db_name:"20261007_test"` 与 `db:"data/db/20261007_test.sqlite"` 同；`no_such_db.sqlite` → 正确的「要扩充的数据库不存在…」。
- 端到端（`tool:"python"`）：新建 1 谱 → 200（116 s）；扩充 2 谱（其中 1 个已入库）→ 200、`skipped:["2026082919gm-00a9-0000-4e40cd3e"]`（91.5 s，只分析新的）；再扩充全旧 → 400。

### 17.3 向听数 `>=3` 只改展示
- `mjscore/feats.py` 新增 `SHANTEN_KEYS = tuple(f["key"] for f in SHANTEN_FEATURES)`；`mjscore/shanten.py` docstring 注明「内部值 3 = >=3，对外一律写成 >=3」。
- `mjscore/cli.py` 新增 `feat_value_text(key, value)`：向听数特征且 `value == 3` ⇒ `">=3"`，其余 `str(value)`；`--values` 的输出改用它并追加一行检索口径提示。
- 前端：`web/js/app.js` 加 `SHANTEN_KEYS` 映射、`fmtFeatValue(key, v)`（3 → `>=3`）与 `featHint()` 的向听数分支（`整数 / 区间 -1-3 / 列表 1,2,3 / 比较 >=3（内部值 3 = >=3，按整数匹配）`）；`web/js/mjsfeat.js` 注释、`web/index.html` 说明、`readme.md` §1.1 / §2.2 同步。
- 检索口径不变（内部整数）：对用户库实测分布 `-1` 2 帧 / `0` 5862 / `1` 9773 / `2` 10943 / `>=3` 10674；`3`、`3-5`、`>=3` 三种写法**都命中 10674**，`0,3` 16536，`>3` 0，`-1` 2。

### 17.4 作者信息
- `mjscore/__init__.py`：`AUTHOR = "Zumma Crystal"`、`AUTHOR_EMAIL = "z1025zzsg@sohu.com"`、`__author__` / `__email__`。
- `mjscore/server.py`：`/api/health` 与 `/api/features` 的返回都加 `author` / `author_email`。
- 前端：`web/index.html` 增 `#appAuthor`，`web/js/app.js` 的 `loadMeta()` 填充 `v0.1.0 · Zumma Crystal <z1025zzsg@sohu.com>`，`web/style.css` 加 `.app-author` 样式。
- 另外 `tools/analyze.py` / `tools/download_tenhou.py` 的 docstring、`readme.md` 新增 `## 9. 作者`。

### 17.5 项目结构整理（根目录只留 `server.py`）
- 移动：`index.html` → `web/index.html`、`style.css` → `web/style.css`、`js/` → `web/js/`、`analyze.py` → `tools/analyze.py`、`download_tenhou.py` → `tools/download_tenhou.py`。现在根目录 = `server.py` / `readme.md` / `log.md` / `tenhou-url.txt` + `data/ media/ mjscore/ references/ test/ tools/ web/`。
- 随之修正的路径引用：`web/js/tiles.js` 的 `TILE_DIR` 与 `web/js/ui.js` 的 `BACK_SRC`（`file:` 协议用 `../media/tiles/`，否则 `/media/tiles/`）；`mjscore/node_harness.js` 的 `JS_DIR = path.join(__dirname, '..', 'web', 'js')`；`mjscore/server.py` 把 `/` 与 `/index.html` 重写成 `/web/index.html`（静态根仍是项目根）；`tools/analyze.py` 把项目根加进 `sys.path`；`tools/download_tenhou.py` 的 `PROJECT_ROOT = parent.parent`；各模块 docstring 里的 `js/x.js` → `web/js/x.js`、`python analyze.py` → `python tools/analyze.py`；`test/apptest.js` / `test/uitest.js` / `test/selftest.js` 的资源路径。
- 冒烟：`/` 200（= `web/index.html`）、`/web/js/app.js` 200、`/media/tiles/1m.svg` 200、`/api/health` 200；`python tools\analyze.py --version` → `天凤牌谱分析 v0.1.0`。

### 17.6 顺手修掉的反斜杠缺陷
- 批量把 `python analyze.py` 换成 `python tools\analyze.py` 时用了 `re.subn(..., r"python tools\\analyze.py")` —— replacement 里的 `\\` 只落成**一个**反斜杠，于是写出 `python tools\analyze.py`：`mjscore/cli.py` 的 epilog（普通字符串字面量，`\a` = BEL 控制字符，`--help` 会打出乱码）、`tools/analyze.py` docstring、`tools/download_tenhou.py` docstring（`\d` 触发 `SyntaxWarning: "\d" is an invalid escape sequence`）。
- 修法：统一改**正斜杠** `python tools/analyze.py` / `python tools/download_tenhou.py`；复验用 `compile()` + `warnings.simplefilter("always")` 扫全仓 `.py` ⇒ 问题 0（唯一 SyntaxError 是第三方 `references/mjlog2mjai_parse.py` 带 UTF-8 BOM，非本轮引入）。

### 17.7 验证结果（全绿）
- `py_compile`（全仓，跳过 `data/`）失败 0；`node --check` 7 个 JS 文件全 exit 0。
- `test/agari_test.py` 182 项、`test/danger_test.py` 29 项、`test/expect_test.py` 73 项、`test/shanten_test.py` 92 项 —— 全绿。
- `test/apptest.js` **276 OK / 0 失败**；`test/selftest.js` `[OK] 全部不变量通过`；`test/uitest.js` 全部通过。
- `test/mjscore_test.py`：新增 9 条断言（`/api/health` 与 `/api/features` 的作者字段、`cli.feat_value_text` 4 条、`db_path_of` 2 条、扩充不存在的库 1 条）⇒ 全量 **通过 217 项 / 失败 0 项**（wall 3658.0 s ≈ 61.0 分钟）。

### 17.8 GitHub（第 ⑤ 项：本地仓库已就绪，推送暂缓）
- 本地：`git init -b main` + `.gitignore`（排除 `data/`、`__pycache__/`、`test/out/`、`test/_tmp/`）+ `git config core.autocrlf false`（系统级是 `true`，会破坏 LF）+ 本地 `user.name` / `user.email`；`git add -A` 后 78 个文件，提交 **ceda372**（`78 files changed, 32315 insertions(+)`）。
- 本机 `ssh` 客户端坏（`failed to initialize w32posix wrapper`，连接卡死），且**没有 `gh` CLI** ⇒ 只能走 HTTPS + PAT；GitHub API 可达，候选账号 `Z1025` / `ZummaCrystal` 下 `tenhou-paipu-analysis` 均不存在（404）⇒ 待用户提供账号与 PAT（或自行建仓）后再推送。
- 本轮收尾时用户 m04462 指示：其余已完成、只差 GitHub 推送时先停止该项 ⇒ 推送留待用户提供账号 / PAT（或自行建仓）后再做。

### 17.9 本轮踩到的坑
- 见第 19 节第 68~73 条（正则 `\\` 只落一个反斜杠、行号转储抄缩进、PowerShell 重定向原生命令、本机 ssh + `core.autocrlf`、结构改造后逐项核对路径引用、静态页面搬家后必须 302 跳转）。

### 17.10 追加修正：静态页面搬迁后必须 302 跳转（用户 m04553）
- 现象：访问 `http://127.0.0.1:8770/` 后界面点不动，服务端刷 `code 404, message File not found` 与 `GET /js/mjsfeat.js` / `GET /js/app.js` / `GET /style.css` 404。
- 根因：`/` 原来只是**内部改写** `self.path` 成 `/web/index.html`（浏览器地址仍是 `/`），而 `web/index.html` 里是相对引用 `style.css` / `js/*.js` ⇒ 解析成 `/style.css`、`/js/*.js`（改造前的旧路径）⇒ 404。
- 修法：`mjscore/server.py` 的 `do_GET` 把 `/` 与 `/index.html` 改成 **302 跳转**到 `/web/index.html`（`Location` + `Content-Length: 0`），浏览器地址变成 `/web/index.html`，相对引用才落在 `/web/` 下；`/media/tiles/*` 与 `/api/*` 不受影响。
- 复验：`/`、`/index.html` → 302；`/web/index.html` 200；页面里的 7 个相对引用（`style.css` + 6 个 `js/*.js`）全部 200；`/media/tiles/1m.svg` 200、`/api/health` 200（`test/*.py|*.js` 里没有任何针对根路径的断言，改动不影响既有测试）。

## 18. 后续待办（第 1~4、6 项已完成，见第 6 节；第 17 轮完成三种向听数，见第 11 节；第 19 轮完成 12 个期望特征，见第 13 节；第 20 轮完成危险筋组 / 危险两面组，见第 14 节；第 21 轮完成第二类特征接入检索、帧特征面板、分析进度条、牌谱下载，见第 15 节；第 22 轮完成 bug 修复、版本号 v0.1.0、扩充现有数据库、readme，见第 16 节；第 23 轮完成扩充库 bug 修复、向听数 `>=3` 展示、作者信息、项目结构整理，见第 17 节；下面是第 12 轮之后的待办）

- [ ] 解析 mjlog XML，按局切分（`INIT` … `AGARI`/`RYUUKYOKU`）。
- [ ] 逐巡目重建每一家的**手牌**（起手 13 张 + 摸牌 − 打牌 − 鸣牌/杠消耗，注意鸣牌后的摸牌顺序）与**牌河**（各玩家 D/E/F/G 序列）。
- [ ] 提取「每局 / 每巡目 / 每家」的手牌与牌河特征。
- [ ] 特征入库（建议 SQLite），支持按指定「手牌 / 牌河特征」检索出 牌谱 url + 局 + 巡目 + 玩家。
- [ ] `references/mjlog2mjai_parse.py` 可作为 mjlog 解析参考。
- [ ] 前端「牌谱检索」视图仍是占位表单，待入库后接上。
- [ ] 展示规则里**无真实样本**的分支（大明杠、流局満貫、九種九牌、四家立直、四風連打、四槓散了、三家和了、一炮双响/三响）在有样本后需回归确认。

- [ ] **第二类特征**：三种向听数（第 17 轮，见第 11 节）、12 个期望特征（第 19 轮，见第 13 节）、立直家（他家）危险筋组数量 / 危险两面组数（第 20 轮，见第 14 节）均已实现，并在第 21 轮经 `mjscore\feats.py` 接入数据库与前端牌谱检索（共 33 个特征，见第 15 节）；其前置「和牌判别器 + 点数计算器」见第 9 节。「听牌强度」按用户 m02865 取消（与现有特征含义重复）。
- [ ] 起和役已并入 18 种判别器、`score()` 与向听叶子（用户 m01701，见第 12 节）；一发 / 里宝 / 槍槓 / 嶺上 / 海底 / 河底等偶发役尚未纳入。
- [ ] 旧库（无 `meta.app_version`）在下一次用 v0.1.0 分析或扩充时才会补写 `app_version`（第 22 轮，见 16.3 / 16.4）。
- [ ] 牌河类特征的展示遗留：手切被鸣（69/107）只有红框、没有透明度（5.8 回滚后未给替代方案）。
- [ ] 「全部浏览」一次取全 2786 行（第 13 轮后），条目再多（多牌谱全量）时应改成按页/按需加载。
- [ ] 展示规则里**无真实样本**的分支（大明杠、流局満貫、九種九牌、四家立直、四風連打、四槓散了、三家和了、一炮双响/三响）在有样本后回归确认。
- [ ] 推送 / 维护 GitHub 仓库 `tenhou-paipu-analysis`：本地已 `git init` + 提交 `ceda372`（78 文件 / 32315 行），本机 ssh 客户端坏、只能 HTTPS+PAT，远端仓库尚未创建（第 23 轮，见 17.8）。

## 19. 环境与工具踩坑速查

1. **本环境 PowerShell 不能对原生命令做管道 / 重定向 / 变量捕获**（`| Select-Object`、`> file`、`$x = & node …` 会空输出或 exit 1）；必须直接 `& 'D:\Program Files\nodejs\node.exe' <脚本路径>` 让输出进控制台。
   （第 13 轮实测补充：`& <exe> … | Select-String '…'` 在控制台可直接用；失效的是 `> file`、`$x = & …` 这类重定向/捕获，
   `Start-Process -RedirectStandardOutput` 会静默失败，需要 node 全量输出时改用包装脚本 `console.log` 落盘。）
2. 写文件的 PowerShell 脚本：诊断一律用 `Write-Host`（`Write-Output` 会被当成返回值混进文件内容）；含 `$` 的替换文本用单引号 here-string `@'…'@`（双引号里 `$` 要用反引号转义，不是 `\$`）；嵌套数组字面量 `@(,@($o,$n))` 会让整段脚本静默失败（文件完全未改），改成逐个平铺 `if ($t.Contains($o)) { $t = $t.Replace($o, $n) }`。
3. 换行与长度：`js\app.js` 等是 **LF**（锚点字符串只能用 `` `n ``），`log.md` / `style.css` 是 CRLF；PowerShell 的 `$s.Length` 是**字符数**不是字节数（中文占 3 字节）。
4. 测试脚本里的正则常被 PowerShell 双重转义污染（`/\.xml\$/`、`/\\.tile\\.riichi/`），会让断言**静默失效**（曾经导致 7g 从不切换牌谱、加杠分支没被测到）—— 改测试后要确认断言真的被执行。
5. 假 DOM 测试从 HTML 抽 id 的正则要连标签名一起抽：`/<([A-Za-z][A-Za-z0-9]*)[^>]*\sid="([A-Za-z0-9_-]+)"/g`，否则 `#controls button[data-act="others"]` 这类选择器匹配不上。

6. **项目目录之外不能建文件**：`New-Item -Path 'D:\coding\dsh_workspace\simple\mjscore'` → PermissionDenied；连
   `sqlite3.connect(<%TEMP%>\x.sqlite)` 都报 `unable to open database file`（`tempfile.mkdtemp()` 却能成功）
   ⇒ 新文件（含测试用临时库）一律放项目内，测试用 `test\_tmp\`。
7. **PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写 BOM**：带 BOM 的 js 直接 `node x.js` 会报
   `SyntaxError: Invalid or unexpected token`（`require()` 容忍 BOM）⇒ 一律用
   `[System.IO.File]::WriteAllText($p, $t, (New-Object System.Text.UTF8Encoding($false)))`。
8. **改文件优先用 Python 补丁器**（`io.open(..., newline='')` 保留换行 + 断言锚点恰好出现 1 次）而不是 PowerShell 字符串替换：
   曾用 `ReadAllText` + `Contains` 匹配 CRLF 失败，把 `test\_patch_app.py` 前 2418 字符切掉（靠 `_prefix.py + tail` 拼回）。
   补丁器自身的坑：`rep(s, a, B = <三引号块>)` 报 `SyntaxError: positional argument follows keyword argument`；
   插入的 JS 含 `\.` 时必须用 `r<三引号块>`。
9. Python 侧 `subprocess.run(..., capture_output=True)` 捕获 node 输出是正常的（只有 PowerShell 不行），
   `mjscore\node_harness.js` 因此也提供 `--out FILE`。
   （第 15 轮更正：**本环境 Python 侧也建不了管道** —— `subprocess.run(..., capture_output=True)` 会抛 `PermissionError: [WinError 5] 拒绝访问`，见第 22 条。）
10. 管道给 Python 的 stdin 可能带 BOM（PowerShell 设 `[Console]::OutputEncoding=UTF8` 会写）⇒ 读 stdin / 条件文本的地方都要 `.lstrip('\ufeff')`。
11. `store.connect(db, create=False)` 必须显式检查文件存在，否则检索会**顺手建出一个空库**（本轮实测出 `__nope__.sqlite`）。
12. 补丁器留下的半成品行（占位符 `XX(...)`）会让 `server.py` 直接 `IndentationError`；改完必须 `python -m py_compile` 全部 `.py`。
13. 补丁锚点的**缩进必须逐字一致**：`js\replay.js` 的 `switch case` 体是 8 空格缩进（`applyCall` 体才是 4 空格），
    写成 6 空格会得到 `anchor count = 0`（补丁器 fail-fast，源文件不会被改坏，可安全重跑）。
14. 改补丁器脚本本身**不要用 `str.replace()` 做子串替换**：6 空格是 8 空格的子串，会把已修好的行再加深 2 空格；
    直接重写整个脚本更快也更安全。
15. PowerShell 无法重定向原生命令的 stdout（`Start-Process -RedirectStandardOutput` 静默失败、退出码 1）；
    需要 node 测试全量输出时写一个包装 `.js`（劫持 `console.log`/`console.error` 落盘 + 只把匹配行转发到控制台）。
16. CLI 里 `--db` 与 `--delete-db` 取的都是**相对当前工作目录的路径**（`os.path.abspath`），
    只有 `--db-name` 才映射到 `data\db\<name>.sqlite`；另注意 `store.RESULT_COLS` 不含 `drawn`。
17. 极简假 DOM（`test\apptest.js`）只实现 `El.parent`，**没有 `parentNode`**；`matches()` 也**不支持逗号选择器**
    ⇒ 断言用 `byId.X.textContent` 而不是 `el.parentNode`；给控件统一 class 选择器（如 `.cond-ctl`）比 `input.cond-input` 稳。
18. 特征显示名有 4 处副本（`mjscore\feats.py` 的 FEATURES 与头部文档表、`js\mjsfeat.js` 的 FEATURES、`log.md` 6.3 表，
    以及 `analyze` 写进 DB 的 `feature_def.name`）⇒ 改名前先全仓库 grep，改完要重建数据库才同步。
19. `frame` 的唯一键是 `(log_id, round_index, ev_index, seat)`（`frame_uniq`）：`INSERT OR REPLACE` 会先删旧行、
    再插入**新的 `idx`**，而 `frame_full` 按 `frame_idx` 存 ⇒ 重分析同一牌谱会留下孤儿行（1 次多 2786 idx / 13930 行）。
    写库后必须 `store.prune_frame_full(conn)`（第 14 轮已加到 `cli.analyze` 里）。
20. 删除类命令别用「删完再判断文件在不在」写退出码（`return 1 if not os.path.isfile(p) else 0` 会把成功判成失败）
    ⇒ 成功分支直接 `return 0`、失败分支 `return 1`。
21. 第 15 轮再确认：**PowerShell 不能把原生命令的 stdout 重定向/管道出来** —— `& $py test\agari_test.py > test\out\x.log 2>&1` 退出码 0 但日志 **0 字节**；
    `| Select-String '…'` 吞掉输出并 exit 1（第 1/15 条的老结论仍成立：别用 `>` 存测试输出）。
22. **本会话禁止给子进程建管道**：Python 侧 `subprocess.run(..., capture_output=True)` 也失败 ——
    `subprocess.py:1390 _get_handles -> _winapi.CreatePipe(None, 0)` 抛 `PermissionError: [WinError 5] 拒绝访问`；
    实测 `stdout=PIPE` ✗、`stdout=DEVNULL` ✓、不传参数（继承控制台句柄）✓ ⇒ `test\mjscore_test.py`（经 `mjscore\nodeharness.py` 捕获 node 输出）
    与 `analyze.py --tool node` 暂时跑不了，node 侧只能直接 `& node <脚本>`。
23. 想「落盘 + 只看失败行」时用**进程内捕获**而不是重定向：Python 驱动 `runpy.run_path(测试脚本, run_name="__main__")` + `sys.stdout = io.StringIO()`，
    结束后写文件、只转发匹配 `FAIL|===|通过|失败|Error|Traceback` 的行，`SystemExit` 用 try/except 取 code。
24. 合成手牌测试：`hand` 是 13 张（和了张另给 `win_tile`），且必须传**牌 id**（把 kind 当 id 传会报「1m 出现 6 张（超过 4）」这种误导错）；`counts_of()` 返回 34 项 list（不是 dict）。另：把含 `\` 的 Windows 路径写进**非 raw** 的 Python 字符串会被八进制/转义吞掉（`data\2026…` → `data` + chr(130) + `6090…`），写补丁脚本时用 `r'''…'''`。

25. **不要把候选枚举提前剪枝**：同一个 14 张手牌里，和了张的三种读法（落进顺子 / 落进刻子 / 与手里的单张组成雀头）可能同时成立，符与番不同 ⇒
    必须全部枚举再比打点。例：`1123567m` + 1m（手里 1m×3）既可读成 11m 雀头 + 23m 両面（平和 20 符），也可读成 1m 単騎 + 123m 顺子（32→40 符）；
    「単騎要求手里恰好 2 张」这类剪枝是错的（用户 m01164 指正）。
26. **「能不能取出 (4-n) 组面子 + 雀头」的朴素 DFS 必须允许丢掉多余的牌**：对第一个非空种类要么用掉（刻子 / 顺子）、要么**整组丢光**再递归，否则会误报无解（写向听数对拍参考时因此 5 例误报「模块偏乐观」，最后用「直接枚举 W 计划」的第二种参考复核才确认模块是对的）。
27. 顺子边界：`k % 9 <= 6` **不足以**说明能取 `k, k+1, k+2` —— 字牌「中」的 kind 33 也满足 `33 % 9 == 6`，会越界 ⇒ 必须写成 `k < 27 and k % 9 <= 6`（或直接用预生成的 55 组 `GROUPS`）。
28. 向听数的成本函数里**不要用「空槽数 × 3」当剪枝下界**：它随枚举递减而不是下界，会让根节点直接返回（症状：所有手牌都返回 3、耗时 0.000 s）；手牌张数也必须是 `14-3n` 或 `13-3n`（非法张数会让期望值写错）。
29. 复用 `mjscore/agari.py` 的 `score()` 当「有没有役」的裁判时注意：它末尾把 `ctx_yaku` / `dora_yaku` 也算进 `han` ⇒ **只有宝牌、没有役的手不会抛「役なし」**；造测试牌要避开赤 5 的 id（16/52/88），否则会凭空多出「赤宝牌 1 番」把无役手判成能和。

30. **起和役门槛加进 `agari.can_tsumo()` 之后，不能再用它找「形和但无役」的假和牌**（它会直接返回空列表 ⇒ 统计永远 0）；判**牌型形状**要用 `agari.shapes_of(hand, melds)`，判**役**要用 `agari.score(...)`（或新的 `agari.has_min_yaku(...)`）。

31. 本环境虽然禁止给子进程建管道（第 22 条），但**可以给 `subprocess.run` 传文件对象**：`with open(o, 'w', encoding='utf-8') as fo, open(e, 'w', encoding='utf-8') as fe: subprocess.run(argv, stdout=fo, stderr=fe)` ✓（`stdout=PIPE` / `capture_output=True` 抛 `PermissionError: [WinError 5]`，`stdout=DEVNULL` ✓）。`test\mjscore_test.py` 与 `analyze.py --tool node` 的绕法就是在进程内驱动里 monkeypatch `mjscore.nodeharness.run`，把 stdout / stderr 指向临时文件再读回。

32. 补丁器**不要靠手敲大段代码当锚点**（必然 `count=0`）；要按起止标记切片：`i0 = s.index(M1)`、`i1 = s.index(RAISE) + len(RAISE)`、`block = s[i0:s.index(RAISE)]`。断言 `block.endswith(...)` 时**别忘了块尾的空行**（形如 `…"seki": (sets, pair)})\n\n`）。另：把内层三引号直接写在外层三引号字符串里会提前终止字符串（`SyntaxError: invalid character '（'`）⇒ 用 `D = chr(34) * 3` 拼接或外层用单引号三引号。

33. `expect.waits_of()` 返回的是 **set**（听牌张集合），断言里别写 `.count(...)`（会 `AttributeError`）；要比较就用 `sorted(...)` 或 `in`。

34. 合成测试手牌要避开「隐形役」：`123m456m789m…` 自带**一気通貫**（(24, 2)），拿它当「无役手」会得到荣和 2600 而不是 0；无役用例改用 `2m3m4m5m6m7m` 之类。

35. 14 张手牌的向听数 = 「打一张之后」的最小向听数（唯一例外：已经和牌的 14 张是 −1，打一张只剩听牌 0）。这条既能当剪枝依据（进张后 `dist != d − 1` 直接跳过），也能当「超过上限就提前返回全 0」的依据。

36. 已经和牌的 14 张帧（`dist(counts) == -1`）走的是「和牌帧」分支：6 个枚数项按设计为 0、打点 = 该手牌的最大和牌得点 ⇒ 做「打一张即听」的抽样时要先 `if e.dist(c) == -1: continue`。

37. `values_both()` 的第二个返回值 `alt`（best 口径）**只有 6 个枚数项、打点项恒 0**（打点只在 `agg="sum"` 那份里）；另外，写含 `\e`、`\c` 之类反斜杠的文本（如 `` `test\expect_test.py` ``）时，字符串要加 r 前缀（raw 三引号），否则 Python 3.14 抛 `SyntaxWarning: invalid escape sequence`。

38. `replay.iter_events(game, ri)` 产出的 `state` 是**就地修改的同一个 dict**（`mjscore/replay.py:234` 明说 `state_after`）⇒ 循环里把 `st` 留到循环外使用必须先 `copy.deepcopy(st)`，否则拿到的是整局最后一个事件的状态（本轮示例取数就踩了这个）。

39. `agari.evaluate(hand, melds, win_tile=None, ...)` 判和牌要求张数与调用方式匹配：13−3n 张手牌**必须传 `win_tile`**，否则 `score()` 判「并未和牌」⇒ 返回 None（叶子明细会整片变成「无役 / 0」）。

40. 对整份语料（71 牌谱 / 37533 帧）逐帧跑带 `compute()` 的扫描要小心超时（仅 `dist` 全量就要约 150 s，再叠每帧的节点展开 ⇒ 300 s 上限会被 kill）；先用「只算 `dist`」粗筛候选，再对少数候选做节点计数 / 展开。

41. `expect.Expect` / `values` / `values_both` 的 `max_shanten` 默认是 `1`（`DEFAULT_MAX_SHANTEN`）：两向听帧不显式传 `max_shanten=2` 会得到 12 项全 0（文档 / 复现片段同理）。

42. 自己写「手牌字符串 → counts」的解析器时注意 `format` 的输出是「数字在前、花色字母在后」，不能按「遇到花色字母才结算」写（会把下一段数字算进上一个花色）；写含反斜杠路径的文本一律用 raw 三引号。

43. **期望打点要先归一化**（用户 m02389）：节点同时维护 `SC = Σ p × 得点` 与 `MS = Σ p`（只累加和牌叶子），**打点 = `SC / MS`**；但**打牌层仍按 `SC` 取 argmax**（= `p(后继 → 和牌) × 打点`，用户要求的「打牌选让期望打点最大的一张」），分母只跟这条 argmax 分支。`MS = 0`（听的牌都无役）时返回 0.0 而不是报错。别把「达到和牌状态的概率」乘进打点 —— 那是「听牌强度」要算的量。

44. **核对期望值 / 写参考实现时，手牌必须用 `expect.tiles_of(counts)` 重建**（5 的牌种取 `kind*4 + 1`）：用 `kind*4 + n` 造牌会把 5m / 5p / 5s 的第一张当成**赤 5**（牌 id 16 / 88），`agari.score` 会多算「赤宝牌」番 ⇒ 得点虚高（同一手 h1 的立直荣和会变成 5200 而不是 1300），看起来像模块算错。`tid_of(kind) = kind*4 + 1` 才是模块自己的口径（赤牌本轮不还原）。

45. **`compute()` 里的 keep = 「打掉一张后 13 张的向听数 == 该 14 张帧的向听数」的那些打牌**（`d0` 已是打牌层最小值，所以不是 `d0 − 1`）；`state` 里的 `dora` 存的是**牌 id**（要 `// 4` 才是 kind）；核对某个打点键时别忘 `("sc", assume, mode)` 里的 `mode` —— 把荣和项用 `TSUMO` 去比会得到「看着像模块错」的假 FAIL。
46. **从 `"%4d | %s"` 这种行号转储里目视抄锚点会多 1 个空格**（`|` 后面还有一个空格）：补丁器会报 `ANCHOR FAIL … count=0`。
   改长段代码 / 文档时别手抄锚点，改成**按行号切片**：`L[a-1:b] = text.split("\n")`（替换）、`L[a:a] = text.split("\n")`（在某行后插入），
   配 `assert marker in "\n".join(L[a-1:b])` 的上下文断言，并**自下而上**（行号递减）依次改。fail-fast 的补丁器在断言失败时不会写文件 ⇒ 源文件安全。

47. 重定向原生命令的输出时，PowerShell 的 `> file` 给出的是 **UTF-16LE（带 BOM，首字节 0xFF）**，不是 UTF-8 也不是 0 字节（第 1 条 / 第 21 / 22 条在这一点上要按本条更正）：
   读回时必须 `encoding="utf-16"`；更稳的做法是不重定向，直接让 Python 自己 `io.open(path, "w", encoding="utf-8", newline="\n")` 写文件（本仓库的驱动脚本都这么做）。

48. **参考实现要镜像被测模块的兜底分支**：m02766 把枚数分母改成「只数有役听牌」后，参考侧的 `sum(avs) / nfuro` 在 `nfuro == 0`（整帧没有有役听牌）时抛
    `ZeroDivisionError`（`test\expect_test.py:573 section3b`）—— 模块的 `Expect._pick_tenpai` 是「分母 ≤ 0 ⇒ 0.0」，参考侧也要写 `(sum(avs) / nfuro) if nfuro > 0 else 0.0`。
    另外新插入的断言不能引用后面才定义的变量（`TQ_SUM` 在 section2 后半才赋值 ⇒ `UnboundLocalError`），就地展开成元组即可。
49. **合成用例别忘了「立直家自己牌河里的牌也是主视角可见牌」**：危险两面组数的算例要「看到 2m x2、3m x1」，
    若把立直家的安全牌也做成 3m（它的牌河里有 1 张），可见数就变成 2 => 両面 23m 的组数是 2 x 2 = 4 而不是 2 x 3 = 6
    （第一版测试就是这么写错的）。给算例配安全牌时用不属于任何筋组的字牌（如 4z）最省事。
50. **拿不到全局出牌序就别硬算「立直动作发生后打出的牌」**：replay 的状态里只有各家自己的牌河顺序
    （river 条目没有全局序号）=> 要从事件流维护 `DangerLog`。好在被鸣走的牌仍留在 river 里（标 `called=True`），
    所以「全局出牌序」与「四家牌河」可以逐牌种互相核对（本模块把它当不变量）。
51. **mjlog 的 `REACH step="1"` 与 `step="2"` 之间恰好夹着 1 张别家的出牌**（545 次立直全部如此，其中 18 次后面还紧跟
    一个 `AGARI`）=> 「立直动作发生后」的口径取 **step=1（宣告）那一刻**：宣告之后、别家在这中间打出的那张也算安全牌；
    暗杠不是出牌事件，天然不会进「立直后的出牌」。
52. **HTTP 路由是前缀匹配，特殊接口必须排在通用接口之前**：`/api/analyze-progress` 要排在 `/api/analyze` 前面、
    `/api/download-progress` 要排在 `/api/download` 前面，否则请求会被前缀更短的 handler 先吃掉。
53. **极简假 DOM 的元素没有 `.style`**：`test\apptest.js` 的 `El` 只实现了 `textContent` / `childNodes` / `querySelector` 等，
    往 `el.style.width` 写值会抛 `TypeError: Cannot set properties of undefined (setting 'width')`。
    前端写 DOM 样式前要先判空（本轮把进度条封装成 `setBar(id, pct)`，其中 `if (el && el.style)` 兜住）。
54. **残留的 `setInterval` 会让假 DOM 测试的 node 进程永不退出**：分析 / 下载进度轮询没停，测试就算跑完也不结束
    （实测 300 s 超时被 kill）。本轮在结果块之后加 `setTimeout(function () { process.exit(problems.length ? 1 : 0); }, 0)`，
    等所有同步断言跑完再退。
55. **前端帧特征面板按 key 缓存**（`FeatPanel.key === ck` 直接返回），同一 idx 的前后两段测试要显式清 `App.featPanelState.key`，
    否则第二段拿到的还是上一段的旧行。
56. **加了 float 特征后 `test\mjscore_test.py` 的值域检查必须区分 `kind == "float"`**（否则 12 个期望特征会被判「不是整数」），
    同时 `store.SCHEMA_VERSION` 要跟着 2 → 3；另外「第二类特征在 node 路径下由 python 补齐」会带来一条 warning，
    凡是断言 `analyze` 无警告的地方都要区分工具（python 无警告 / node 有一条补齐警告）。
57. **假 DOM 测试里子进程 / 网络调用的超时值是硬伤**：`/api/analyze` 现在要一次跑完整目录（含 17 个第二类特征），
    默认 15 s 的 `urlopen(timeout=15)` 必然超时（实测 `TimeoutError` 打断整轮），长跑接口要显式传 `timeout=3600`。
58. **`Start-Process` 起不了可执行的后台进程**：进程会存在，但 CPU 恒为 0、脚本一行都不执行（`-WindowStyle Hidden` 与否都一样）。
    要跑超过单次调用上限的长任务，用 `cmd /c start "" /b cmd /c '"python.exe" "驱动.py" > "console.log" 2>&1'`；
    驱动脚本本身写成「`runpy.run_path(测试脚本, run_name="__main__")` + 把 `sys.stdout` 换成实时 flush 的 Tee 写日志」，
    这样日志文件会边跑边增长，可以就地轮询进度（本环境的子进程管道限制见第 22 / 31 条，`subprocess.run` 要在驱动里 monkeypatch）。
59. **单次调用有 300 s 硬上限**：实测脚本打印到 `elapsed 300.0 s` 后 shell 被重置（`The persistent pwsh shell was reset`），
    所以 `test\mjscore_test.py`（约 45 分钟）这类长测试必须按第 58 条丢到后台，不能指望一次调用跑完。
60. **`store.totals(conn)` 的键是 `{"frames", "sources", "rounds"}`**（不是 `"frame"`），探针里写 `totals(conn)["frame"]` 会 `KeyError: 'frame'`。
61. **补丁锚点要跟目标文件的换行一致**：`js\app.js` / `js\ui.js` / `test\apptest.js` / `log.md` 是 CRLF，`index.html` / `style.css` / `js\mjsfeat.js` / 多数 `mjscore\*.py` 是 LF —— 锚点里写 `\n` 之前先 `nl = "\r\n" if "\r\n" in s else "\n"`，把 old / new 一起 `.replace("\n", nl)`；另外 `$env:TEMP` 是**会话级子目录**（本会话 `…\Temp\dsh-dAhF4u`），临时脚本路径不要硬编码，用 argv 传进去。
62. **补丁脚本的 EDITS 元组要按定义解包**：本想用 4 元组 `(tag, old, new, label)` 却写 `for tag, old, new in EDITS` ⇒ `ValueError: too many values to unpack (expected 3, got 4)`（改补丁器自己的那一行比重发整个补丁便宜）。

63. **JS 测试递归找语料时，路径要相对最初的 root 拼**（`path.relative(baseRoot, p)`）。按递归层级的 root 去 relative 只会拿到 basename
    ⇒ `ENOENT …\data\<特征码>.xml`。牌谱被搬到 `data\paipu\<时间戳>\` 后，`test\selftest.js` / `test\uitest.js` 就是这样静默扫到 0 个牌谱、「假通过」的；
    两个测试现在都改成 `walkXml(root, out, baseRoot)` + 按 `BASE_IDS`（5 个基础牌谱特征码）挑选。
64. **`store.set_meta()` 只 `INSERT OR REPLACE`、不 commit**：造库 / 改 meta 的探针必须自己 `conn.commit()`，否则 `close()` 一执行就回滚，`meta` 表是空的、
    `app_version_of()` 返回 `''`（第一次造「旧版本库」就踩了这个，还以为是校验没生效）。
65. **`store.check_version()` 先查 `meta.schema_version`，缺行就直接放行**（当作全新库，不校验 `app_version`）；所以造「由旧版本软件生成的库」时
    必须同时写 `schema_version` 与 `app_version`，否则版本校验根本不触发。
66. **`store.connect()` 里版本校验失败要先 `close()` 再抛**，否则 Windows 上这个 sqlite 文件一直被占着，之后既删不掉也覆盖不了（`WinError 32`）；
    相应地 `cli.list_dbs()` 不能用 `store.connect()` 去读不兼容库的 meta（会抛异常），要 raw `sqlite3` 打开读 `meta` 表，再把 `app_version` / `compatible: False` 填回去。
67. **往长测试里插新断言的两条禁忌**：① 别覆盖既有变量 —— 我把「扩充全重复 400」「版本不匹配 400」两条插在 `POST /api/analyze` 与原有的 `d` 断言之间，
    `d` 被改写成 400 错误体，害得 `analyze 摘要` / `补齐警告` 两条读到 `None` 假失败；② 别在依赖全局状态的断言之前调用会重置该状态的接口 ——
    `/api/analyze` 一进来就 `progress_reset()`，插在进度断言之前会把快照改成 `tool='auto' / files_done=0`，于是「进度快照记录工具 / 已完成牌谱数」两条假失败。
    修法：整段移到进度断言之后 + 变量改名（`st5 / d5`）；一次全量跑 53 分钟，这类顺序错误代价很高。
68. **正则替换里的 `\\` 只落成「一个」反斜杠**：`re.subn(r"python analyze\.py", r"python tools\\analyze.py", s)` 写出的文本是 `python tools\analyze.py` ——
    落在 docstring 里是 `\d`（`SyntaxWarning: "\d" is an invalid escape sequence`），落在普通字符串字面量里是 `\a` = BEL 控制字符（`--help` 打出乱码，静默不报错）。
    改法：路径统一用**正斜杠**（`python tools/analyze.py`）；批量替换后必须用 `compile(src, path, "exec")` + `warnings.simplefilter("always")` 扫一遍。
69. **行号转储的缩进不能目视抄**：`"%4d | %s"` 转储在 `|` 后自带 1 个空格，照抄后锚点比文件实际多 1 个空格（`count=0`）。
    改法：补丁一律用**行号切片**（`L[a-1:b] = text.split("\n")`）+ 上下文断言，并自下而上（行号递减）依次改。
70. **PowerShell 不能重定向原生命令的 stdout**：`git status > f` 得到空文件、`$LASTEXITCODE` 为空；`<原生命令> | Select-Object -First N` 会吞掉输出并让 `$LASTEXITCODE=1`。
    要么直接打屏，要么让 python 自己 `io.open(..., "w")` 落盘（含中文的日志一律用 python 读）。
71. **本机 `ssh` 客户端坏了**（`failed to initialize w32posix wrapper`，连接卡死到超时），只能走 HTTPS + PAT；系统级 git 是 `core.autocrlf=true`，
    仓库里必须 `git config core.autocrlf false` 才不会把 LF 改成 CRLF；`data/`（约 36 MB）默认由 `.gitignore` 排除。
72. **目录结构改造后要逐项核对路径引用**：`web/js/tiles.js` 的 `TILE_DIR` / `web/js/ui.js` 的 `BACK_SRC`（`file:` 协议用 `../media/tiles/`、否则 `/media/tiles/`）、
    `mjscore/node_harness.js` 的 `JS_DIR`、`mjscore/server.py` 的 `/` → `/web/index.html` 重写、`tools/analyze.py` 的 `sys.path`（项目根 = 上一级）、
    `tools/download_tenhou.py` 的 `PROJECT_ROOT`、以及 `test/*.js` 里的资源路径；漏一处就是 404 或运行期错误。
73. **静态页面搬家后不能只做「内部 URL 改写」**：`/` 若内部改写成 `/web/index.html` 而不真正跳转，页面里的相对引用（`style.css` / `js/*.js`）会按**浏览器地址**（`/`）解析到根目录 ⇒ 全部 404。
    正确做法是 302 跳转（浏览器地址随之改变），相对引用才会落在 `/web/` 下；改完只要抓一次 `/` + 页面里所有相对引用，看是否都 200。



---
*最后更新：第 23 轮（用户 m04115：修「扩充现有数据库」把库名拼成 `<名字>.sqlite.sqlite` 导致报「数据库不存在」的 bug（`cli.db_path_of()` + `server._db_of()`）；与向听数有关的特征内部值 3 一律显示 `>=3`（`cli.feat_value_text()` / `web/js/app.js` 的 `fmtFeatValue()`，检索仍按内部整数匹配，`3` / `3-5` / `>=3` 都命中内部值 3）；新增作者信息（`mjscore\__init__.py` 的 `AUTHOR` / `AUTHOR_EMAIL` + `/api/health` `/api/features` + 页眉 `#appAuthor`）；项目结构整理 —— 前端移到 `web/`（`index.html` / `style.css` / `js/`）、命令行移到 `tools/`（`analyze.py` / `download_tenhou.py`），根目录只留 `server.py`，并顺手修掉批量替换引入的 `\a`（BEL）/ `\d`（SyntaxWarning）缺陷；GitHub 本地已 `git init` + 提交 `ceda372`（78 文件 / 32315 行），推送待账号 / PAT。测试：`test\apptest.js` 276 OK、`test\mjscore_test.py` 全量 通过 217 项 / 失败 0 项（wall 3658.0 s ≈ 61.0 分钟，exit=0）、`test\agari_test.py` 182 / `test\danger_test.py` 29 / `test\expect_test.py` 73 / `test\shanten_test.py` 92 / `test\selftest.js` / `test\uitest.js` 全绿。追加修正（用户 m04553）：`/` 与 `/index.html` 由内部改写改为 **302 跳转**到 `/web/index.html`（否则页面里的 `style.css` / `js/*.js` 会解析成旧路径而 404）；本节见第 17 节；当前有效展示规则 = 5.1~5.7；下一步见第 18 节。）*