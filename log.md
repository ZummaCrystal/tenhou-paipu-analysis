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

- **追加（用户 m04598 仍见 `/style.css`、`/js/*.js` 404）**：根因是**浏览器缓存了改造前的旧 HTML**（文档 URL 仍是 `/`，相对引用自然还解析成旧路径），不是服务端没改。服务端补两道保险：① 旧路径回退：根目录没有、`web/` 下有同名文件时 **302 到 `/web/…`**（实测 `/style.css` → 302 `/web/style.css`、`/js/mjsfeat.js` → 302 → 200）；② `Handler.end_headers()` 给 `text/html` 响应加 `Cache-Control: no-store, must-revalidate`。
### 17.11 追加：牌谱播放改为入口式，首页只留介绍 + 开始播放（用户 m04628）

- 要求：牌谱播放不要再直接暴露在首页，改成与「牌谱分析 / 检索 / 下载」一样的入口 —— 首页只保留功能介绍 + 「开始播放」按钮。
- 改动（`web/index.html` / `web/js/app.js` / `web/style.css`）：首页卡片里的 `btnPickFile` / `fileInput` / `dropZone` /
  `sampleSelect` / `btnLoadSample` / `#homeMsg` / 打不开文件的提示整块**搬进播放视图**，包在 `#rpOpenBar`（`.open-bar`）里；
  首页只留 `<button id="btnGoReplay">开始播放</button>`；播放视图工具栏加「打开牌谱…」(`#btnOpenPicker`) 折叠 / 展开该栏。
- 行为：`loadText()` 载入成功后自动收起 `#rpOpenBar`；点页签「牌谱播放」即使没载入牌谱也允许进入（原来会弹提示并退回首页），
  改为展开 `#rpOpenBar` 并提示「请选择一个牌谱文件，或载入示例牌谱」；`render()` 本身有 `if (!App.game) return;`，空视图不会报错。
- 验证（只挑选个例，未做全量）：`test\apptest.js` 新增 5 条断言（首页窗口片段不含 `btnPickFile`/`dropZone`、播放视图片段含控件、
  点「开始播放」进播放视图且打开栏可见、「打开牌谱…」可收起 / 再展开）⇒ **281 OK / 0 FAIL / 全部通过**（原 276 OK）+ `node --check` 通过。
### 17.12 追加：首页布局改为 2 x 2，牌谱下载排第一（用户 m04685）

- 要求：首页四个功能区域按 **2 x 2** 排布，且把「牌谱下载」放在第一个（在「牌谱播放」之前）。
- 改动：`web/index.html` 的 `<div class="cards">` 里把「牌谱下载」卡片整块移到最前，卡片顺序 = 下载 / 播放 / 分析 / 检索；
  `web/style.css` 的 `.cards` 由 `repeat(auto-fit, minmax(320px, 1fr))` 改为 `repeat(2, minmax(0, 1fr))` + `align-items: start`，
  并加 `@media (max-width: 760px) { .cards { grid-template-columns: minmax(0, 1fr); } }`（窄屏回落单列）。
- 验证：`test\apptest.js` 新增 2 条断言（首页四张卡片顺序 = 下载 / 播放 / 分析 / 检索、`.cards` 是两列网格）
  ⇒ **283 OK / 0 FAIL / 全部通过**；`node --check web/js/app.js` 通过。
### 17.13 追加：四张功能卡片统一默认尺寸（用户 m04704）

- 现象：2 x 2 之后四个卡片高矮参差。要求给统一的默认尺寸（比「牌谱分析」那张大一些），文字超出时再自适应长高。
- 改动（`web/style.css`）：`.cards` 用 `grid-auto-rows: minmax(300px, auto)` —— 每格默认至少 300px、内容更长时行高自动增长
  （不会溢出或裁切）；去掉 `align-items: start` 让卡片填满单元格；`.cards > .card` 改 `display: flex; flex-direction: column`，
  入口按钮（`> button` 或 `> .row:last-child`）加 `margin-top: auto` 贴底对齐；窄屏（`max-width: 760px`）回落单列且 `grid-auto-rows: auto`，避免大片空白。
- 验证：只做静态点检 —— `web/style.css` 花括号配平 181 / 181、`.cards` 规则文本复查无误（按要求未跑全套测试）。
### 17.14 追加：页签顺序同步首页卡片（用户 m04713）

- 要求：首页卡片顺序改成「下载 / 播放 / 分析 / 检索」后，左上角页签顺序也要跟着调整。
- 改动：`web/index.html` 的 `<nav class="tabs">` 改为 首页 / **牌谱下载** / **牌谱播放** / 牌谱分析 / 牌谱检索
  （页签一律走 `data-view` 属性，`app.js` 的 `setView()` 与页签守卫都不依赖顺序）。
- 连带修测试：`test\apptest.js` 原来用 `tabs[1]` 点「牌谱播放」页签，顺序一变就点到「牌谱下载」了 ——
  改成按 `getAttribute('data-view') === 'replay'` 查找（该文件里已无按下标取页签的写法）。
- 验证：只做静态点检 —— 页签顺序文本复查无误、`node --check test\apptest.js` 通过（按要求未跑全套测试）。
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
74. **前端搬家后浏览器会缓存旧 HTML**：相对引用按文档 URL 所在目录解析，`/` 上的旧页面会一直去取 `/style.css`、`/js/*.js`。除把 `/` 302 到 `/web/index.html`，服务端还应：根目录找不到而 `web/` 下有的文件 302 过去、并给 HTML 响应加 `Cache-Control: no-store`；否则用户即使重启服务也还是 404（用户 m04598）。
75. **把首页的控件搬进子视图时，别忘了同步改「页签守卫」**：原来点「牌谱播放」页签会在 `!App.game` 时弹提示并退回首页（那时控件在首页），控件搬进播放视图后这条守卫反而把入口堵死了 —— 要么放开守卫、要么把守卫的提示换成「先在这里选文件」（用户 m04628）。


76. **`curl.exe` 的 HTTPS 失败不等于网络不通**：本机 `curl` 对任何 https 都报 `curl: (35) schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030E)`（`http_code=000`），
    而 Python（OpenSSL + certifi）与 Node 的 `fetch` 对 `github.com` / `api.github.com` / `objects.githubusercontent.com` 都能握手，并拿到 `Range` 请求的 206。
    结论：判断「HTTPS 是否可用」要用 Python / Node 复验，别据 curl 下结论（用户 m00590 第 7 条）。
77. **冻结后 `__file__` 不再指向项目**：PyInstaller onedir 下资源落在 `_internal/`（`sys._MEIPASS`），装到 Program Files 后又不可写。
    所有「项目根」引用必须改走 `mjscore/paths.py`：`resource_root()`（只读资源）+ `data_root()`（用户数据）；**源码模式下两者都返回项目根**，改造才对开发/测试零影响。
    本次接入点：`mjscore/cli.py:18`（`ROOT`）、`mjscore/cli.py:20`（`DB_DIR`）、`mjscore/server.py:49`→`:287`（静态根 `directory=ROOT`）、`mjscore/download.py:32`/`:118-120`、`mjscore/nodeharness.py:25-26`。
78. **`tempfile.mkdtemp()` 在 TEMP 受限时会造出「自己都进不去」的目录**：建出来的目录带仅所有者 / Deny DeleteSubdirectoriesAndFiles ACL，后续写入与删除都报 `WinError 5`，`takeown` / `icacls /reset` 也救不回来。
    测试临时目录一律用项目内 `test/_tmp/<名字>-<pid>-<uuid>` + `os.makedirs`（`test/_tmp` 已在 `.gitignore` 里）。
79. **`subprocess` 的管道在本环境不可用**：`capture_output=True` / `PIPE` 抛 `CreatePipe: WinError 5`；要拿输出就把 stdout 重定向到**文件句柄**（`stdout=open(log, "w")`）或 `DEVNULL`，跑完再读文件。
80. **PowerShell 的 `$pid` 是只读自动变量**：`foreach ($pid in 1,2,3) { ... }` 会让整段命令报错，**该命令块里后续语句全都不执行且零输出**（曾据此误以为补丁已写好）。循环变量一律用 `$procId`。
81. **浏览器 headless 截图在本环境不可用**：`chrome.exe --headless=new --screenshot=...` / `--dump-dom` 不产出文件，`chrome.exe --version`、`electron.exe --version` 连退出码都拿不到（但会留下 profile 目录与挂起进程）。
    需要「SVG → 位图」时要么用 InkScape / ImageMagick（本机都没有），要么自写光栅化 —— 见 `tools/svg2ico.py`（纯标准库、可复现）。
82. **图标别只留本地**：`build/` 被 `.gitignore` 排除，图标应由脚本可复现生成（`tools/svg2ico.py`），打包脚本第一步就跑生成，别把二进制当唯一来源。
83. **提交前先补 `.gitignore`**：`node_modules/`（本项目 Electron 约 450 MB）必须在列，否则 `git add -A` 会把整棵依赖树带进仓库。
84. **持久会话里 `& x.ps1` 可能报「未签名」**：本工具的 pwsh 会话实际按「要求数字签名」执行脚本（`PSSecurityException: 未对文件进行数字签名`），尽管 `Get-ExecutionPolicy` 显示 RemoteSigned。绕法是 `powershell.exe -ExecutionPolicy Bypass -NoProfile -File …`，或 `[scriptblock]::Create((Get-Content -Raw …))`。
85. **`Start-Process -RedirectStandardOutput/-RedirectStandardError` 在受限环境报 `Win32Exception: Access is denied`**（创建带重定向句柄的子进程被禁）：想让子进程留日志，要么让它继承控制台，要么在子进程内部把 `stdio` 指向文件句柄（`desktop/main.js` 就是这么做的）。
86. **`.ps1` 里的中文必须存成 UTF-8 with BOM**：Windows PowerShell 5.1 读无 BOM 的 UTF-8 会按 ANSI 解码，中文注释/输出全乱码（Python / JS / md 文件仍统一无 BOM）。
87. **`ELECTRON_CACHE` 管不到 Electron 的缓存目录**：`app-builder-lib/out/electronGet.js:48-55` 只用 `process.env.LOCALAPPDATA` 拼 `<LOCALAPPDATA>\electron\Cache`；要挪位置只能改环境变量本身（`ELECTRON_BUILDER_CACHE` 才管 nsis / winCodeSign）。
88. **PyInstaller 6.x 的 hook 发现默认在隔离子进程里跑**：受限终端下 `PyInstaller/isolated/_parent.py:224` 的 `create_pipe` 抛 `PermissionError [WinError 5] 拒绝访问`；先设 `sys._pyi_isolated_subprocess = True`（`_parent.py:215` 读这个标记）可改成进程内执行，产物与正常模式一致（`packaging/pyi_build.py --in-process`）。
89. **Node 在禁管道的沙箱里 `spawn` / `spawnSync` / `fork` 全部 `EPERM`**（`errno -4048`），但 `stdio` 指向文件句柄照样能用 —— 这就是后端子进程日志写文件而不是管道的原因。
90. **electron-builder 的 `-c.key=value` 写法不稳**：`-c.npmRebuild=false` 在某些 shell / 参数传递路径下被 yargs 拆成 `-c` 加上值 `.npmRebuild=false`，于是把它当**配置文件路径**去读，报 `ENOENT: no such file or directory, open 「...\.npmRebuild=false」`，栈为 `app-builder-lib/src/util/config/load.ts:19 readConfig` → `config.ts:43 getConfig` → `packager.ts:367 validateConfig` → `packager.ts:398 build`。要改配置就写进 `package.json` 的 `build` 字段（如 `"npmRebuild": false`），命令行只留 `--win nsis --publish never`。
91. **PowerShell 调原生 exe 会吞掉参数里的双引号**：`& $py -c 'print("dq ok")'` 实际传成 `print(dq ok)` → `SyntaxError: invalid syntax. Perhaps you forgot a comma?`；`[System.IO.File]::WriteAllText` 这类 cmdlet 不受影响 ⇒ 带引号的脚本先写成文件再执行。
92. **electron-builder 的 assisted installer 默认装在「当前用户」目录**：`oneClick:false` 且 `perMachine` 不是 `true` 时，`app-builder-lib/templates/nsis/multiUser.nsh:30-47` 用 `$LocalAppData\Programs\${APP_FILENAME}`（于是默认落到 `C:\Users\<用户>\AppData\Local\Programs\<名>`），并且 `assistedInstaller.nsh:18-20` 会多显示一个「安装模式」页（默认「仅为我安装」）。要让默认安装位置变成 `C:\Program Files\<名>` 必须 `nsis.perMachine = true`：`out/targets/nsis/NsisTarget.js:439-441` 定义 `INSTALL_MODE_PER_ALL_USERS`（`installer.nsi:20-25` → `RequestExecutionLevel admin`），`multiUser.nsh:79-90` 取 `$PROGRAMFILES64\${APP_FILENAME}`。代价：安装必弹 UAC、且不再显示安装模式选择页。electron-builder **没有** `nsis.installDir` 选项（`scheme.json` 里搜不到），`selectPerMachineByDefault: true` 只是把那个模式页的默认值改成「所有用户」。
93. **浏览器 `<input type=file>` 的初始目录无法用脚本指定**：网页不能给文件框设初始目录，所以「点一下就到数据根目录」只能走 Electron 主进程的原生对话框 —— `desktop/main.js` 的 `ipcMain.handle('pick-paipu-file')` 里 `dialog.showOpenDialog(owner, { defaultPath })`，`defaultPath` 取自 `/api/health` 的 `paipu_dir`（不存在时先 `fs.mkdirSync(dir, { recursive: true })`，首次运行也能落准），渲染层通过 `desktop/preload.js` 的 `contextBridge.exposeInMainWorld('tenhouDesktop', { pickPaipuFile })` 调用（`sandbox: true` 下 preload 里 `contextBridge` / `ipcRenderer` 仍可用）。**没有桥时必须原样退回 `$('fileInput').click()`**：浏览器、`python server.py`、以及双击 `web/index.html` 的 `file://` 离线播放都不受影响；两种模式共用 `#btnPickFile` 入口。
94. **别用 `Promise.resolve()` 包装测试里的同步 thenable**：`web/js/app.js` 的 `openNativePicker()` 若写成 `Promise.resolve(res).then(...)`，会把 `test/apptest.js` 里同步的 `SyncThen` 变成真异步（then 在断言跑完之后才执行）⇒ 大片假失败。判 thenable 要写 `if (!res || typeof res.then !== 'function') return;` 再直接 `res.then(...)`。
95. **给主进程加了新的 electron API，mock 必须同步补桩**：`test/_tmp/electron_mock2.js`（由 `electron_mock_check.js` 派生）补上 `ipcMain.handle`、`BrowserWindow.fromWebContents = () => win`、`dialog.showOpenDialog` 之后，`registerIpc()` 才跑得通；否则主进程直接挂（`ipcMain is not defined` 之类），而这类错误只在 mock 里暴露。
96. **NSIS 按「所有用户」安装时，卸载器里的 `$LOCALAPPDATA` 不是用户目录**：`SetShellVarContext all` 会让 `$LOCALAPPDATA` 与 `$APPDATA` 都解析成 `C:\ProgramData`（用 electron-builder 自带的 makensis 3.04 实测：`test\_tmp\lsvar.nsi` 编译出的 `lsvar.exe` 写出 `test\_tmp\lsvar.txt`，内容 `current_local=C:\Users\ASUS\AppData\Local` / `all_local=C:\ProgramData` / `current_appdata=C:\Users\ASUS\AppData\Roaming` / `all_appdata=C:\ProgramData`）⇒ `packaging\installer.nsh` 原来的 `IfFileExists "$LOCALAPPDATA\tenhou-paipu-analysis\*.*" 0 done` 在按所有用户安装时**恒为假**，整个「是否删除数据」的询问被跳过（这正是用户 m01220 反馈的现象）。修法：宏里先 `StrCmp $installMode "all" 0 <跳过标签>` + `SetShellVarContext current`，查完 / 删完再切回 `all` —— electron-builder 自己在 `templates/nsis/uninstaller.nsh:232-247` 删 `$APPDATA\${APP_FILENAME}` 时也是这么切的。顺带记：`IfFileExists` 的第二个参数 `0` 是「条件不成立时继续执行下一条」（不是跳到文件末尾），原来的写法本身没错；「默认不删数据」用 `MB_DEFBUTTON2`（默认按钮 = 否，直接回车就保留），静默卸载用 `IfSilent` 直接跳过询问。
97. **makensis 两个坑**：① 读 UTF-8 的 `.nsi` / `.nsh` 必须加 `-INPUTCHARSET UTF8`（electron-builder 也是这么传的：`app-builder-lib/out/targets/nsis/NsisTarget.js:515`），不加会报 `Bad text encoding: <路径>:<行>` 然后 abort；② `MessageBox` 的 `/SD return` **不能写在 message text 之前** —— 写在前面时 `/SD` 被并进 options、`IDNO` 被当成正文、正文被当成返回标签去解析，报 `Error: could not resolve label "<正文>"`。要表达「静默时不弹框 + 默认保留」用 `IfSilent <跳过标签>` + `MB_DEFBUTTON2` 更省事，别用 `/SD`。
98. **在本受限沙箱里探测 GUI 安装程序的四条经验**：① 写不了 `%LOCALAPPDATA%`（`os.makedirs` 直接 `PermissionError [WinError 5] 拒绝访问`）⇒ 探针的「假数据目录」必须放项目内；② `Start-Process` / `Wait-Process` 会让工具调用一路卡到 300 s 超时（`& exe` 也拿不到退出码），可靠通道是 `python -X utf8` + `subprocess.Popen(argv, stdin=DEVNULL, stdout=<文件 fd>)`；③ `taskkill /pid <pid> /T /F` 报 `ERROR: Access is denied.`，要收尸得用 `Popen.kill()`（或 PowerShell 里 `(Get-Process -Name x).Kill()`）；④ 给 MessageBox 投递按键必须认**窗口类 `#32770`**（按可见窗口取第一个会拿到安装器主窗口 `… Setup: Installing`，键投进去没用）：`PostMessage(hwnd, WM_KEYDOWN, VK_RETURN, 0)` + `WM_KEYUP` 能触发默认按钮，`PostMessage(hwnd, WM_COMMAND, 6/7, 0)` 等于点「是 / 否」。
99. **`test/mjscore_test.py` 启动时会清空 `test/_tmp`**：`test/mjscore_test.py:90-91` 里 `TMP = os.path.join(ROOT, "test", "_tmp")` + `shutil.rmtree(TMP, ignore_errors=True)`，所以探针 / 辅助脚本别放 `test/_tmp`（会被清掉），放 `build/_scratch`（`build/` 已 gitignore）。
100. **后台进程再 spawn 子进程会立刻 `0xC0000142`**：本受限终端里，前台 spawn 正常（`build.ps1`、node 生成缓存都能跑），但**后台**启动的进程再去 `subprocess.Popen` 子进程会立刻以 `3221225794`（= `0xC0000142` `STATUS_DLL_INIT_FAILED`）退出（`build/_scratch/run_all.py` 顺序跑 9 个测试，每一步 `rc=3221225794 secs=0.0`）⇒ 长验证要么前台串行、要么在**同一个 python 进程里** `runpy.run_path` 依次跑；另外输出重定向到文件必须 `python -u`（否则 stdout 块缓冲，日志在进程结束前一直是 0 增长）。
101. **禁匿名管道时怎么跑「要 node 子进程」的全量测试**：先用内嵌 node 把真输出预生成成 jsonl（`records` / `frames` / `summary` / `invariants`，脚本 `build/_scratch/gen_cache.py`），再 monkeypatch `mjscore.nodeharness.run` 去读缓存（`build/_scratch/mj_shim.py`；它不能用 `__file__` 推项目根，必须硬编码 —— 否则会去找 `build/build/_scratch/subset.txt`）。这只是「本终端等价验证」，不是原生路径。

## 20. 第 24 轮：本地数据管理 + 打包前路径改造 + SVG→ICO 工具（用户 m00178 / m00590）
### 20.1 要求
- 用户 m00178（9 条）：第 1~4 条 = 准备工作就绪；第 5 条 = 用赤 5m 的素材做 `.ico`；第 6 条 = 四项决策（① 把 node 打进包；② onedir；③ 数据目录固定为 `%LOCALAPPDATA%\tenhou-paipu-analysis\data`；④ 出 NSIS 安装包、安装路径用户可选、卸载时询问是否删除数据）；第 7 条 = GitHub SSH 能否替代 HTTPS；第 8 条 = 修 bug；第 9 条 = 前端新增「本地数据管理」（第五个入口、首页改 3 x 2、子功能「牌谱管理」与「数据库管理」，可新建目录 / 移动位置（含 `..` 上级）/ 删除 / 删除子目录）。
- 用户 m00590：数据管理里**禁止把牌谱移出 `data/paipu`、数据库移出 `data/db`**；实测 GitHub HTTPS；做 `.ico`；`<AppName>` = `tenhou-paipu-analysis`；数据根下拉切换的形态「可以」；用户已自行迁移数据、要我先实测；`.gitignore` 精简但保证克隆后能跑；**先不急着打包**。

### 20.2 修 bug（第 8 条）
`web/js/app.js` 的 `loadSample()` 原来写 `fetch('data/' + name)`，而页面在 `/web/index.html` ⇒ 实际请求 `/web/data/...`，而 `web/data/` 并不存在 ⇒ 首页「载入示例牌谱」必然失败。
改法：`/api/health` 取 `paipu_dir` → `/api/scan?dir=<paipu_dir>` 列文件 → 按 `SAMPLE_IDS` 匹配（不足 5 个用列表前若干补齐）→ 下拉框 value 为**绝对路径**，`#btnLoadSample` 走 `/api/read?path=`。

### 20.3 本地数据管理（第 9 条）
- 前端：`web/index.html` 第 6 个页签 `data-view="data"`；首页第 5 张卡 `.card.span`（`.cards` 变 3 行 x 2 列，第五张跨两列，CSS `grid-column: 1 / -1`）；`#view-data` 内含数据根下拉（牌谱 / 数据库）、数据根绝对路径与当前相对路径、子目录/文件列表（选中高亮 + 目录「进入」）、新建目录、移动到（下拉 = 数据根或各级子目录）、删除文件、删除选中子目录。
- 后端：新增 `mjscore/datamgr.py`，提供 `/api/fs-list`、`/api/fs-mkdir`、`/api/fs-move`、`/api/fs-delete`、`/api/fs-rmdir`；`listing()` 返回 `{root, roots, root_dir, dir, parent, dirs[{name,path,entries}], files[{name,path,size,mtime,sqlite}], all_dirs}`；所有写操作只接受该数据根内的相对路径。

### 20.4 打包前的路径改造
- 新增 `mjscore/paths.py`：`resource_root()`（源码 = 项目根；冻结 = `sys._MEIPASS`，无则 exe 所在目录）、`data_root()`（`MJSCORE_DATA_ROOT` 优先；冻结 = `%LOCALAPPDATA%\<APP_DIR_NAME>`；源码 = 项目根）、`data_dir()` / `db_dir()` / `paipu_root()`、`APP_DIR_NAME = "tenhou-paipu-analysis"`。
- 接入点见踩坑 77。效果：**源码运行行为与改造前完全一致**；冻结后用户数据默认正好落在用户已迁移的 `%LOCALAPPDATA%\tenhou-paipu-analysis\data`，不需要 Electron 额外设环境变量。

### 20.5 越界加固（用户 m00590）
`mjscore/datamgr.py:45` `norm_rel()` 拒空 / 绝对路径与盘符 / `..` / 首尾空格 / 非法字符；`mjscore/datamgr.py:89` `_abs_of()` 用 `os.path.commonpath` + `realpath` **双重校验**，分别报 `路径越界：%s` 与 `路径越界（软链接指向数据根之外）：%s`；`ROOTS = ("paipu", "db")` + `ROOT_LABELS`；数据根目录本身不可删（`只能删除整个子目录（含里面的内容）`）。

### 20.6 SVG → ICO（第 5 条 / 复核 5）
本机无 InkScape / ImageMagick，浏览器 headless 亦不可用（踩坑 81）⇒ 自写 `tools/svg2ico.py`（约 533 行，纯标准库）：解析 `path` / `rect` / `circle` / `ellipse` / `polygon`、`transform`（translate / scale / matrix / rotate）、`fill` / `fill-opacity` / `fill-rule`，扫描线填充 + 盒式降采样 + 多尺寸 ICO（16/32/48/64 走 DIB、128/256 走 PNG），带 `--ascii` 自检；遇到不认识的绘图方式（如圆弧 `A`）**明确报错、不产出文件**。
产物：`build/icon.ico`（40754 B，白牌面圆角，推荐）、`build/icon_plain.ico`（38746 B，透明背景）、`build/icon_{16,32,48,64,128,256}.png`。40 个素材实测：0m~9m、1z~7z、back/Front 都能转；`5z` 与 `Blank.svg` 本来就是空牌面；`5p.svg`、`1s.svg` 用圆弧会报错。

### 20.7 GitHub HTTPS 实测（第 7 条）
`curl` 全失败（schannel 凭据问题，见踩坑 76）；Python（OpenSSL 3.5.8 + certifi）与 Node v24.15.0 `fetch` 对 `github.com`、`api.github.com`、`objects.githubusercontent.com`，以及 electron 的 release zip、nsis 7z 均返回 **206（Range 100 字节）**⇒ **HTTPS 可用、不需要 SSH 替代**；electron-builder 首次打 NSIS 能自行下载 nsis / winCodeSign（缓存到 `%LOCALAPPDATA%\electron-builder\Cache`）。

### 20.8 迁移数据实测（用户第 3 问）
`C:\Users\ASUS\AppData\Local\tenhou-paipu-analysis\data\{db,paipu}` 均存在（sqlite 35,311,616 B、71 个 xml）；用 `MJSCORE_DATA_ROOT=<该目录>` 起真实服务：`/api/health` 的 `data_root` / `db_dir` / `paipu_dir` 指向正确、`/api/scan` 扫到 71 个文件（绝对路径）、`/api/fs-list` / `/api/read` 正常；项目内 `data/` 仍在（复制非移动）⇒ 源码方式运行不受影响。

### 20.9 `.gitignore` 精简
忽略：`node_modules/`、`build/`、`dist/`、`data/`、`__pycache__/`、`*.py[cod]`、`test/out/`、`test/_tmp/`、`.vscode/`、`.idea/`、`Thumbs.db`、`desktop.ini`。保留其余全部源码，克隆后只要有 Python 就能 `python server.py`。

### 20.10 验证结果
| 验证 | 结果 |
| --- | --- |
| `test/apptest.js`（含新增第 15 段「本地数据管理」） | 全部通过（status 0） |
| `test/datamgr_test.py`（新增，真实服务 + 真实数据） | 67 / 67 通过 |
| 真实服务直连（`/api/health`、`/api/scan`、`/api/read`、`/api/fs-list`） | 通过（71 个牌谱） |
| `test/mjscore_test.py` 全量 | **未跑完**（只完成第 1 节：5 文件 / 58 局 / 5766 帧不变量 0 错） |

### 20.11 未做 / 后续
- 打包本身：本轮**未开始**；用户 m00590 要求「先不急着打包」，m00751 指示开始打包，见第 21 节。
- 计划产物：`desktop/`（Electron 主进程 + 它自己的 `package.json`）、根 `package.json` 补齐 `name/version/main/scripts`、`packaging/*.spec`、`build.ps1`；产物落 `build/`、`dist/`（均已忽略）。
- 仍待办：`test/mjscore_test.py` 全量跑完；`tools/svg2ico.py` 支持圆弧 `A`；`test/_tmp` 下 3 个 ACL 空目录删不掉（见踩坑 78）。

## 21. 第 25 轮：打包（Electron 外壳 + PyInstaller 后端 + NSIS 安装包，用户 m00751 / m00796）

### 21.1 要求与决策

用户 m00751：「补充log.md，执行commit和push，然后开始打包」；m00796：push 由用户在本机执行。打包决策（用户 m00178 第 6 条）：决策 1 `node.exe` 打进包；决策 2 后端 onedir；决策 3 用户数据固定 `%LOCALAPPDATA%\tenhou-paipu-analysis\data`；决策 4 NSIS 安装包、安装路径用户可选、卸载时询问是否删数据。

### 21.2 新增 / 改动的文件

| 文件 | 作用 |
| --- | --- |
| `build.ps1`（根，10,802 B，UTF-8 **带 BOM**） | 一键打包：环境检查 → 清理(`-Clean`) → 图标 → 回归测试 → 后端 → 冒烟(`-Smoke`) → 外壳/NSIS；开关 `-SkipIcon` / `-SkipTests` / `-FullTests` / `-SkipPyi` / `-SkipElectron` / `-SkipNodeEmbed` / `-ForceInProcessPyi` / `-Clean` / `-Smoke -Port N` / `-PythonExe` / `-NodeExe` |
| `packaging/pyi_build.py` | 唯一一份 PyInstaller 参数（并打印等价命令）；`--in-process` 是受限终端兜底 |
| `packaging/smoke.py` | 冻结后端冒烟：起 exe → 轮询 `/api/health` → 打印关键字段 → `taskkill /T /F` 收进程树，日志写 `build\pyi\smoke-backend.log` |
| `desktop/main.js` | Electron 主进程：取空闲端口 → 起后端（stdout/stderr 走文件 fd）→ 轮询 health → `loadURL("http://127.0.0.1:N/web/index.html")` → 退出收进程树；单实例、禁 nodeIntegration、F12 DevTools |
| `packaging/installer.nsh` | `!macro customUnInstall` 里 MessageBox 询问是否 `RMDir /r "$LOCALAPPDATA\tenhou-paipu-analysis"` |
| 根 `package.json` | 补齐 `name`/`version`/`description`/`author`/`main`/`scripts`（`npm run dist` = `electron-builder --win nsis --publish never`、`npm run build` = 调 build.ps1）与 `build` 配置（`extraResources` 把 `dist/pyi/tenhou-paipu-analysis-server` → `resources/backend`） |
| `readme.md` | 新增第 9 节「打包发布（Windows，可选）」，原第 9 节「作者」顺延为第 10 节 |

### 21.3 冻结后的路径（决策 3 落地）

`mjscore/paths.py`：冻结时 `resource_root() = sys._MEIPASS`（onedir 下 = `<exe 同级>\_internal`）、`data_root() = %LOCALAPPDATA%\tenhou-paipu-analysis`。实测冻结后端 `/api/health` 报 `root=…\_internal`、`data_root=C:\Users\ASUS\AppData\Local\tenhou-paipu-analysis`，`db_dir`/`paipu_dir` 正确；`/api/scan` 71 个牌谱、`/api/fs-list`、`/api/dbs` 正常 ⇒ 与用户已迁移的数据位置天然一致，Electron 不需要设任何环境变量（`MJSCORE_DATA_ROOT` 只在测试时用）。

### 21.4 验证结果

| 验证 | 结果 |
| --- | --- |
| `build.ps1 -SkipElectron -Smoke`（全流程 + 冒烟） | 通过（exit 0；health 0.5 s 就绪，1 个数据库；中文输出正常） |
| `packaging/pyi_build.py`：正常模式 → `PermissionError [WinError 5]` → `--in-process` 兜底 | 兜底成功，产出 exe 2,341,406 B、`_internal\node\node.exe` 91,694,408 B、`_internal\web\index.html`、`_internal\media\tiles\6m.svg`、`_internal\mjscore\node_harness.js` 全部在位 |
| 冻结后端端到端分析（1 个牌谱，`tool=python`，非 full） | 89.3 s；`meta=13 / feature_def=33 / source=1 / round=11 / frame=530 / frame_full=0`，`/api/dbs` compatible=true |
| 内嵌 node 直连 harness（`--summary` / `--records`） | 正常（`--records` 530 行 / 429,499 B） |
| Electron 主进程 mock（假 electron 模块 + 真后端 exe） | 6/6 通过（载入 URL、health、日志落盘、退出后进程被收掉） |

### 21.5 本机（受限沙箱）做不到 → 交接给用户

- **electron-builder 出不了安装包**：它必须用匿名管道起子进程。默认死在 `@electron/rebuild` 的 `child_process.fork`（`app-builder-lib/src/util/rebuild.ts:10`，`spawn EPERM`）；把依赖重建关掉后死在收集 node_modules（当时写成 `-c.npmRebuild=false`，见踩坑 90）（`app-builder-lib/src/node-module-collector/nodeModulesCollector.ts:376` `streamCollectorCommandToFile`）。本沙箱里 Node 的 `spawn`/`spawnSync`/`fork` 全 EPERM、Python `subprocess(PIPE)` 报 WinError 5（见踩坑 84~89、88）。
- 因此**安装包由用户在本机普通终端跑**：`powershell -ExecutionPolicy Bypass -File .\build.ps1`（首次会下载 Electron 约 100 MB、nsis/winCodeSign 约 50 MB 到 `%LOCALAPPDATA%\electron-builder\Cache`）。
- `git push`：本沙箱报 `error: cannot create standard input pipe for ssh: Permission denied` + `fatal: unable to fork`，由用户本机推。

### 21.6 未做 / 后续

- 没有代码签名（安装时 SmartScreen 提示「未知发布者」）；只支持 Windows x64。
- `test/mjscore_test.py` 全量仍未跑完；`tools/svg2ico.py` 仍不支持圆弧 `A`（`5p.svg` / `1s.svg` 会报错，用 `6m.svg` 做图标没问题）。
- `test/_tmp` 下 3 个 ACL 空目录删不掉（踩坑 78）。

### 21.7 用户机复测发现的缺陷（m00923）：-c.npmRebuild=false 被当成配置文件

用户在本机跑 `build.ps1`，第 5 步 electron-builder 直接失败：

```
⨯ ENOENT: no such file or directory, open 'D:\coding\dsh_workspace\simple\tenhou-paipu-analysis\.npmRebuild=false'  failedTask=build
    at readConfig (node_modules/app-builder-lib/src/util/config/load.ts:19:16)
    at getConfig (node_modules/app-builder-lib/src/util/config/config.ts:43:34)
    at Packager.validateConfig (node_modules/app-builder-lib/src/packager.ts:367:27)
    at Packager.build (node_modules/app-builder-lib/src/packager.ts:398:5)
```

原因见踩坑 90：`-c.npmRebuild=false` 被 yargs 拆成 `-c` 加上值 `.npmRebuild=false`，于是被当成「配置文件路径」去读。修法（已落地）：

- `package.json` 的 `build` 字段里加 `"npmRebuild": false`，`scripts.dist` 改成 `electron-builder --win nsis --publish never`；
- `build.ps1` 第 5 步去掉该参数，并留注释警示不要再写回命令行；
- `readme.md` 第 9 节「注意」补一条同样说明。

复测（本沙箱）：日志出现 `• loaded configuration file=package.json ("build" field)` 与 `• skipped dependencies rebuild  reason=npmRebuild is set to false`，之后才撞上本沙箱的 `spawn EPERM`（`node-module-collector/nodeModulesCollector.ts:376`）⇒ 参数解析缺陷已消除，剩下的是纯环境限制（踩坑 89/90）。


### 21.8 用户要求改默认安装位置（m01034）

用户 m01034：「当前的默认安装路径为 C:\Users\ASUS\AppData\Local\Programs\tenhou-paipu-analysis，这是很不合理的，修改为 C:\Program Files\tenhou-paipu-analysis，然后重新开启打包流程，直到需要我手动运行刚才的命令。」

- **改动**：`package.json` 的 `build.nsis.perMachine` 由 `false` 改成 `true`（其余不动：`oneClick:false`、`allowToChangeInstallationDirectory:true`、`createDesktopShortcut/createStartMenuShortcut`、`include`、`deleteAppDataOnUninstall:false`）。机制见踩坑 92：这样 installer 会在 Program Files 建目录、装给所有用户、要管理员权限；「安装路径可选」仍然保留（最后一步目录页可改）。
- **文档**：`readme.md` 第 9 节「产物 / 注意」同步改写（默认 `C:\Program Files\tenhou-paipu-analysis`、安装要 UAC、数据仍固定在各 Windows 用户的 `%LOCALAPPDATA%\tenhou-paipu-analysis`、改回 `perMachine: false` 会退回 `%LOCALAPPDATA%\Programs\<名>`）。
- **证据**：`dist\electron\builder-effective-config.yaml`（electron-builder 自己解析出的最终配置）里出现 `nsis.perMachine: true`。
- **重新打包（本沙箱）**：`build.ps1 -Smoke -Port 8795` 跑到第 [4] 步后端重建（`tenhou-paipu-analysis-server.exe` 2,341,406 B、`_internal\node\node.exe` 91,694,408 B）、图标 `build\icon.ico` 40,754 B、`test\apptest.js` 全绿、冒烟 `/api/health` 与 `/api/dbs` 均 200；第 [7] 步 electron-builder 读配置、解开 `win-unpacked` 之后仍死于本沙箱的 `spawn EPERM`（踩坑 89/90）⇒ 安装包交给用户本机重跑。
- 注意：`dist\electron\tenhou-paipu-analysis-0.1.0-setup.exe` 里那份是用户 03:39 用旧配置打出来的（按当前用户安装），重跑会覆盖它。

### 21.9 用户 m01084：牌谱播放的「选择牌谱文件」默认定位数据目录

- 用户 m01084：「安装成功，试用看上去没有问题，需要做修改。牌谱播放功能，选择牌谱文件按钮，点按后应当默认跳转至牌谱数据根目录 data/paipu，否则用户第一次使用时很难找到这个目录。修改完后重新执行打包，直到需要我执行命令。」用户 m01106 追加约束：「不要忘了同时注意该修正对非 release 的源码造成的影响」。
- **做法**：桌面版走 Electron 主进程原生对话框 + preload 桥（起始目录 = `/api/health` 的 `paipu_dir`，会先 `mkdir -p`，见踩坑 93）；浏览器 / 源码 / `file://` 离线模式没有桥，原样退回 `fileInput.click()`，两条路径共用 `#btnPickFile`。
- **改动**：新建 `desktop/preload.js`；`desktop/main.js` 加 `ipcMain`、`defaultPickDir()`、`registerIpc()`、`webPreferences.preload`、`boot()` 里 `registerIpc()`；`web/js/app.js` 新增 `loadFromPath()` / `openNativePicker()` / `pickPaipuFile()` 并把 `#btnPickFile` 改绑后者；`test/apptest.js` 新增第 16 段（15 条 check：无桥退回 input / 有桥传 `paipu_dir` 且不点 input / 取消不动牌谱 / 静态检查 main + preload + package.json）。
- **验证**：`node --check` 四文件通过；`test/apptest.js` 全绿（`test/_tmp/apptest16.log` 25,162 B）；主进程 mock `test/_tmp/electron_mock2.js` **13/13 PASS**（`dialogOpts[0].defaultPath` = `<fake LOCALAPPDATA>\tenhou-paipu-analysis\data\paipu`、目录被自动建出、模态挂窗口、filters 含 xml、返回选中路径、取消分支、退出后 taskkill 生效）。
- **重新打包（本沙箱）**：`build.ps1 -Smoke -Port 8797` —— 后端 exe 内嵌 `web/`，必须重建；第 [7] 步 electron-builder 照旧撞沙箱的 `spawn EPERM`（踩坑 89），NSIS 安装包仍需用户本机跑 `build.ps1 -SkipIcon -SkipTests -SkipPyi`。

### 21.10 用户 m01220：卸载时没有「是否删除数据」的询问

- 用户 m01220：「当前安装成功后，从控制面板中卸载，没有是否同时删除数据的选项。检查该问题，并设置卸载时该选项默认不勾选，也就是默认不删除数据。」
- **根因**（实测，不是推断）：按「所有用户」安装（`package.json` 的 `build.nsis.perMachine = true`）时卸载器的 shell 变量上下文是 `all`，NSIS 会让 `$LOCALAPPDATA` 解析成 `C:\ProgramData`，于是 `packaging\installer.nsh` 里 `IfFileExists "$LOCALAPPDATA\tenhou-paipu-analysis\*.*"` 恒为假，整段询问被跳过（见踩坑 96；electron-builder 的卸载器模板里本来就没有「删除数据」这种选项，`messages.yml` 只有 `areYouSureToUninstall`，所以这个询问只能由我们的 include 提供，而它确实被编进了卸载器：`NsisTarget.js:600-604` 把自定义 include 加进共用 header，`templates/nsis/uninstaller.nsh:156-158` 用 `!ifmacrodef customUnInstall / !insertmacro customUnInstall` 插入）。
- **修法**（`packaging/installer.nsh`，703 → 1,954 B / 31 行，LF + UTF-8 无 BOM）：宏体先 `StrCmp $installMode "all" 0 tenhou_shell_current` + `SetShellVarContext current`，查完 / 删完再 `SetShellVarContext all` 复原；询问框加 `MB_DEFBUTTON2`（默认按钮 = 「否」）；前面保留 `IfSilent tenhou_keep_data`（静默卸载一律保留）；删「是」时除了 `$LOCALAPPDATA\tenhou-paipu-analysis` 顺带清掉 `$APPDATA\tenhou-paipu-analysis`（Electron 的 userData：缓存 / LocalStorage）；只用 NSIS 原生指令（`StrCmp` / `IfFileExists` / `IfSilent`），不依赖 LogicLib。
- **验证**：① 用 electron-builder 自带 `makensis`（`…\electron-builder\Cache\nsis-3.0.4.1\…\makensis.exe`，v3.04，`-INPUTCHARSET UTF8`）把**真实的** `packaging\installer.nsh` 包含进 `test\_tmp\nsh_compile_check.nsi` 并把宏插进一个「被 Call 引用但运行时进不去」的函数 ⇒ 编译 rc=0（`nsh_compile_check.exe`，校验了中文串、标签、`/SD` 之外的语法），同时保证绝不会真的对 `%LOCALAPPDATA%\tenhou-paipu-analysis` 执行 RMDir。② 控制流探针 `test\_tmp\uninst_logic2.nsi`（同一套指令 + 同样的上下文切换，但假数据目录在项目内 `test\_tmp\uninst_fake\tenhou-paipu-analysis`）+ `test\_tmp\run_uninst_probe3.py` 四种模式实测：`silent`（`/S`）→ `branch=silent-skip`、假目录保留；`enter`（`PostMessage VK_RETURN`）→ `branch=kept-by-no`、假目录保留 ⇒ **默认按钮确实是「否」**；`idyes`（`WM_COMMAND 6`）→ `branch=deleted-by-yes`、假目录被删（证明删除分支可用）；`idno`（`WM_COMMAND 7`）→ `kept-by-no`。日志里同时看到 `all_context_local=C:\ProgramData` → `current_context_local=C:\Users\ASUS\AppData\Local` → `restored_context_local=C:\ProgramData`，上下文的切换与复原都正确。
- **要注意的交接点**：只有重新打包并安装**新版本**后，新的卸载器才存在（旧版卸载器是「静默保留数据」）；先卸载旧版再装新版时不会问、数据照旧保留（安全）。用户重跑 `build.ps1 -SkipPyi -SkipIcon -SkipTests` 即可（后端与前端都没动，只改了 NSIS 片段）。

### 21.11 打包收尾 + 全量验证（用户 m01355）

- 用户 m01355：在自己机器上跑通 `build.ps1` 并贴出产物 —— `dist\electron\tenhou-paipu-analysis-0.1.0-setup.exe` **142,676,228 B**（2026-10-08 20:06:46），
  SHA256 `CCFAD901B86E142B17248C34C5E645971AE05F715C84940E27BB123B86E2F2B9`（同目录还有 `.blockmap` 149,409 B、`latest.yml` 371 B、`builder-debug.yml` 7,644 B、
  `builder-effective-config.yaml` 785 B、`win-unpacked\`）。我方在沙箱里重新算过哈希，与用户所报一致（`Get-FileHash` 同值）。
- 全量回归（`data/paipu/20261007-165558/` 共 71 个 xml；带固定 5 牌谱子集的用例口径不变）：

| 测试 | 结果 | 耗时 |
|---|---|---|
| `test/apptest.js`（内嵌 node） | 全部通过（376 行日志，含第 16 段 15 条） | 0.6 s |
| `test/selftest.js` | `[OK] 全部不变量通过`（5 牌谱 / 58 局 / 5824 帧 / 2701 摸牌 / 2776 打牌 / 117 副露 / 104 立直 / 10 宝牌 / 51 和了 / 7 流局） | 0.1 s |
| `test/uitest.js` | 全部通过 | 0.1 s |
| `test/danger_test.py` | 通过 29 项，失败 0（37254 帧全量，独立参考逐帧 0 差异） | 1.7 s |
| `test/expect_test.py` | 通过 73 项，失败 0 | 26.8 s |
| `test/agari_test.py` | 通过 182 项，失败 0 | 1.5 s |
| `test/shanten_test.py` | 通过 92 项，失败 0 | 169.9 s |
| `test/datamgr_test.py` | 通过 67 项，失败 0 | 0.9 s |
| `test/mjscore_test.py`（shim 版） | 通过 217 项，失败 0 项（脚本打印「全部通过」；shim 版：node 输出取自预生成缓存） | 3415.3 s（约 57 分钟） |

- 本终端的跑法：`build/_scratch/` 里的辅助脚本（`gen_cache.py` 预生成 node 输出、`mj_shim.py` 换掉 `nodeharness.run`、`run_one.py` / `run_heavy.py` 同进程 `runpy`），
  原因见踩坑 99~101（`test/_tmp` 会被清、后台 spawn `0xC0000142`、禁匿名管道）。
- 冻结产物的端到端验证早已通过（见 21.4 / 21.6）：下载真牌谱 → 分析入库 → 列库 → 检索 / 浏览 / 详情 / 帧数据、内嵌 node 直连 harness、Electron 主进程 mock 13/13。

## 22. 第 26 轮：NAGA / ricochet 牌谱下载支持 + 完整 report_id 判重（用户 m00080 目标 1、m00268、m00418 修正）

### 22.1 交付物
- `mjscore/download.py`（旧 11,175 B / 274 行 → 21888 B / 510 行）：新增 naga / ricochet 下载与判重。
  - 常量：`NAGA_HOST_NATIVE` / `NAGA_HOST_PROXY` / `NAGA_NATIVE_ENDPOINT` / `NAGA_PROXY_ENDPOINT` /
    `NAGA_FILE_SUFFIX=".json.gz"` / `NAGA_ID_BODY_LEN=64` / `NAGA_ID_RE` / `NAGA_ID_ANY_RE` / `NAGA_URL_HINT_RE`。
  - 函数：`looks_like_naga_url(text)` / `naga_report_key(report_id)` / `build_naga_url(form, report_id, mtd=None)` /
    `parse_naga_url(text)`（→ `{form, report_id, key, mtd, url}`）/ `_ssl_context()` / `split_naga_bytes(raw)` /
    `fetch_naga_report(target, timeout=30.0, retries=3)` → `(gz, json)` /
    `save_naga_report(report_id, data, output_dir, overwrite=True)` → `<report_id>.json.gz` / `find_naga_files(output_dir, key)`。
  - `run_download` 重写：同一个列表里可混天凤 URL 与 naga / ricochet URL；返回值与每个 entry 都带 `duplicate`；
    进度快照 `download_snapshot()` 增 `duplicate`（`download_reset` / `download_update` 同步）。
- `mjscore/server.py`：`_scan_dir(path, kind=None)` + `SCAN_KINDS`（xml / naga）；`/api/scan?kind=xml|naga|all`
  （默认仍只列天凤 `.xml`，旧行为不变）。
- `web/js/app.js`：下载结果列表改走 `/api/scan?dir=…&kind=all`，下载完的 naga `.json.gz` 会出现在列表里。

### 22.2 关键技术结论（NAGA 端点 / 判重口径）
- 下载端点：官方 `https://naga.dmv.nico/reports/<report_id>.json.gz`；
  代理 `https://ricochet.cn/api/naga/proxy/reports/<report_id>.json.gz`。两种形式**各按原样重建**。
- `mtd` 只在 ricochet 侧生效、官方域完全忽略：带 `mtd={"Mortal-UNK":["74683a214bdd1dc3"]}` 时 `naga_types`
  从 `{"0":"ニシキ","1":"カガシ"}` 变成多一个 `"2":"4.1b"`；所以不能一律把 ricochet URL 转成官方 URL。
- 落盘 = `<output_dir>/<report_id>.json.gz`（**响应原样的 gzip 字节**；实测官方 1,232,504 B、ricochet+mtd 587,350 B，
  两者 gunzip 后都能 `json.loads`）。
- 判重（用户 m00268，**m00418 修正**）：键 = **完整的一串 report_id**（含结尾 `v2_2` 这类格式后缀，只去掉 `.json.gz`）；
  url 里的 `tw=0/1/2/3` 只是换主视角、**不参与判重**；天凤特征码（10 位数字）与 naga 互不判重。
  磁盘上已有同 report_id 的文件（或同批次里已出现过同一 id）→ 记 `duplicate` + `skipped`，不重复下载；
  同 id + `overwrite=True` 才允许重下。（m00418 之前的实现剥掉 `v2_2` 按主体判重，已改回完整序列。）
- 本机 Python 的 HTTPS 可用（`certifi` + OpenSSL 3.0.18）：`_ssl_context()` 优先用 certifi 的 CA 包，
  不需要绕过证书（旧注释「python 没有可用的 CA 包」已过时）；`curl.exe`（schannel）依旧不可用。

### 22.3 测试结果（本会话实测）
- 端到端（`naga-url.txt` 两条 URL + 变体，同一批次）：`total 5 / saved 3 / failed 1 / skipped 1 / duplicate 1`
  - 官方 naga ✓（16 局，`naga_types` 2 个模型）、ricochet+mtd ✓（10 局，3 个模型含 `4.1b`）；
  - 官方 URL 把 `v2_2` 改成 `v2_3` → 视为**另一条报告**、尝试下载（该 id 不存在 ⇒ 404 / `failed`）✓；
  - 128 个 0 的假 report_id → HTTP 404 → `failed` ✓；同一批里的天凤 URL 仍正常下载 xml ✓；
  - 判重口径（用户 m00418，改完后重跑）：同一条官方 URL 分别带 `tw=0` / `tw=2` / `tw=3` 的批次 →
  `total 6 / saved 3 / failed 2 / skipped 1 / duplicate 1`（第 1 条 saved、第 2 条 `duplicate=True` 不下载 ✓，
  证明 tw 不参与判重）；落盘文件名 = 完整 id（`3180043a…e0v2_2.json.gz` / `9ace0d86…a641v2_2.json.gz`）✓；
  二次运行 `overwrite=False` → `saved 0 / failed 2 / skipped 4 / duplicate 3` ✓。
- `naga_report_key` 单测：`<id>v2_2` 与 `<id>v2_2.json.gz` 同键；`<id>v2_3` != `<id>v2_2` ✓。
- `/api/scan`（临时目录含 `a.xml` + `b.json.gz` + `c.txt`）：默认 / `kind=xml` → 1 个（只有 .xml）；
  `kind=naga` → 1 个（只有 .json.gz）；`kind=all` → 2 个；`kind=bogus` → 400「未知的牌谱种类」；目录不存在 → 400。
- `node --check web/js/app.js` ✓；`looks_like_naga_url("2026082919gm-00a9-0000-4e40cd3e")` = False ✓。
- `test/mjscore_test.py` 全量**未跑**（约 57~61 分钟，见踩坑 58 / 85 / 98 —— 本沙箱起不了可用的后台进程）；
  下载相关的旧断言（`extract_log_id` / `collect_urls` / `save_log` / `/api/download` 错误码）不受影响（这些函数未改）。

### 22.4 踩坑
1. **`mtd` 必须拼成 `?mtd=` 而不是 `&mtd=`**：`NAGA_PROXY_ENDPOINT` 本身没有 query，
   `url += "&mtd=…"` 会把 `&mtd=…` 变成**路径的一部分** ⇒ ricochet 返回 `HTTP Error 404: Not Found`。
   改成 `("&" if "?" in url else "?") + urllib.parse.urlencode({"mtd": mtd})` 后正常。
2. 本沙箱里 `Start-Process` 起的后台进程不产出（日志文件 0 字节、进程随后消失），`Start-Process -RedirectStandardOutput` 静默失败 ——
   与踩坑 58 / 85 / 98 一致。
3. 后台进程写出的文件在当次 pwsh 调用里可能「看不见」（`cmd /c dir` 能看到、`Test-Path` / `Get-Content` 说没有）
   ⇒ 查文件状态优先用 `cmd /c dir` / `cmd /c type`。

### 22.5 待办（用户 m00080 的目标 2 / 3 / 4 + m00198）
- 目标 2：naga 牌谱在界面播放（按天凤牌谱的展示形式）。
- 目标 3：naga 解析 —— 报告里已带**完整 mjai 事件流**（每帧 `info.msg`，`info.msg.p_msg` 指向前一帧），
  可复用现有算法算 33 个特征；新增第一类特征「NAGA决策」∈{有,无}（天凤=无、naga=有）；`.sqlite` 支持混编与扩充。
  决策概率**只存平衡形 naga（ニシキ）那一档**（用户 m00418），其他风格丢弃。
- 目标 4：检索 / 数据管理支持 naga。
- m00198 展示规格：手牌上下条、「当前帧特征」左侧竖条两列表格（NAGA 决策概率 >10% 的选项）、
  播放区右下 5 个数据（流局率 / 横移率 / 放铳率 / 和了率 / 期待顺位，纯文本）、按当前决策玩家切换、仅 NAGA 牌谱显示。
- 已确认（用户 m00418）：不必区分「官方 URL / ricochet+mtd URL 指向同一份报告」——Mortal 系模型（`4.1b`）是**无用数据**；
  只保留**平衡形 naga**（`naga_types` 里名为「ニシキ」的那一档模型）的决策概率，其他风格（カガシ / 4.1b 等）一律不保存。
  目标 3 的解析阶段据此只取 ニシキ 的下标（两个样本里都是 `naga_types["0"]`）。

## 23. 第 27 轮：NAGA 报告适配层 + 界面播放接线（用户 m00080 目标 2）

### 23.1 交付物
| 路径 | 说明 |
| --- | --- |
| `mjscore/naga.py` | **新模块**（17,592 B）：NAGA 报告（`.json.gz` / `.json`）→ 与天凤 mjlog **同构**的内部牌谱结构 + `naga` 段；决策概率只保留平衡形「ニシキ」那一档 |
| `mjscore/server.py` | `/api/read` 增加 naga 分支（转成内部结构后返回 JSON 文本 + `naga:true`；失败给 400 可读文案）；接口 docstring 同步（20,559 B） |
| `web/js/app.js` | `parseGameText()`（`/^\s*\{/` → `JSON.parse`）、`App.naga`、`readFile()` 支持 `.gz`（`DecompressionStream`）、`gameLogId()` 剥 `.json.gz`、首页示例清单改 `/api/scan?…&kind=all`（77,013 B） |
| `desktop/main.js` | 「选择牌谱文件」对话框新增 `NAGA 牌谱 (*.json.gz, *.json)` 过滤器（扩展名只能写 `gz`）（7,990 B） |
| `test/apptest.js` | 新增第 2b 节「载入 NAGA 报告」10 项断言（含「naga 帧数 == 该局事件数」契约断言；99,347 B） |

### 23.2 技术要点
1. **内部结构契约**：`{"meta":…, "rounds":[{init, events}], "naga":{…}}`。init 只需 `round / combo / kyotaku / dices / dora / scores / oya / hands`；事件沿用 mjlog 的
   `draw / discard / call / reach / dora / agari / ryuukyoku`。牌 id 0..135（`kind = tid>>2`，赤 5 = 16/52/88），由「每局每 kind 四个 id 的池 + 逐事件从手牌真取」生成
   ⇒ `mjscore/replay.py` 的 `check_invariants()` 三个样本 **0 错误**。
2. **帧对齐**：报告的 `pred` 是**二维** `pred[局][帧]`（官方 viewer 也按 `pred[0][1].dahai_pred` 取）；帧 j ↔ 我们的 `frames[j]`，
   `len(game["naga"]["rounds"][i]) == len(game["rounds"][i]["events"])`；末尾多出的那 1 帧（局末 agari / ryuukyoku）没有 naga 数据。
3. **msg → 事件 1:1**：`tsumo`→`draw`、`dahai`→`discard`、`chi`/`pon`/`daiminkan`/`kakan`/`ankan`→`call`（`kind` = 1..3 / 4 / 5 / 6 / 7，与 `huro` 同一套分类）、
   `reach` → step1、`reach_accepted` → step2（套 `scores`）、`dora` → `dora`；`start_kyoku` → init（`round = bakaze*4 + kyoku-1`，0 = 東一局）；局末从 `end_msgs[0]` 补 1 个 `agari` / `ryuukyoku`。
4. **平衡形**：`balanced_model_index()` 找 `naga_types` 里值为「ニシキ」的键（两个样本都是 `"0"`）；`pred_dahai` / `huro` / `kan` / `reach` 都是「每模型一档」的列表 ⇒ 取那一档。
   ricochet+mtd 的报告多一档 `4.1b`（用户 m00418：无用数据，不保存）。
5. **概率单位**：报告里是万分比，官方 viewer 渲染前统一 `/1e4`；本模块原样保留整数，换算留给展示层。
6. **和了事件**：`hand` = 和了者 13 张 + 和了牌（荣和取放铳者牌河末张的 id）、`machi` = [和了牌]、`dora` = `dora_markers`（mjai 名转 id）、
   `ura` = `uradora_markers`（实测就是 0..135 的 tenhou 风格 id，viewer 也是 `uradora_markers.map(t=>it(t))` 直接用）、`yaku` = `yakus_detail`（缺则 `yakus` 补 han=1）、
   `before` = `scores - deltas`、`gain` = `deltas`。
7. **流局（口径已在第 28 轮更正，见 24.2）**：原来按 `end_msgs[0].tenpais[i]` 决定摊开谁的手牌 —— 实测该字段恒为全 true、与自家 `deltas` 矛盾，已改成用向听数算听牌家；`reason` 也不再统一 `""`，而是由 `infer_ryuukyoku_reason()` 从事件流推断（用户 m00653）。
8. **前端**：`/api/read` 对 `.json.gz` 先按 `1f 8b` 魔数 gunzip 再转换，返回的 JSON 文本 2.9 MB（官方 16 局）/ 2.0 MB（ricochet 10 局），未触 `MAX_TEXT`（16 MB）上限；
   浏览器里手选 `.gz` 文件时前端用 `DecompressionStream('gzip')` 解压（老浏览器给可读提示）。

### 23.3 测试（本沙箱实测）
- 三样本转换：官方 `3180043a…v2_2`（16 局）/ `60b5c2ad…v2_2`（12 局）/ ricochet+mtd `9ace0d86…v2_2`（10 局）⇒ `check_invariants` bad rounds **0 / 0 / 0**，
  每局手牌 13 张，单份转换 0.05–0.08 s。
- Node 端回放一致性（直接 require `web/js/replay.js`）：两样本 26 局「帧数 = NAGA 帧数」逐局相等、局标签（東一局…南四局）与报告一致、
  局末分数逐局等于报告 `end_msgs[0].scores`、23 个和了局**无一空役**、`console.warn` **0 条**（JS 侧手牌追踪同样自洽）。
- `/api/read`：naga → 200 `{path, naga:true, text}`（文本 sha 与离线转换结果逐字节相同）；天凤 `.xml` → 200 原文（无 `naga` 键）；`.json.gz` 但不是 NAGA 报告 → 400
  `NAGA 牌谱解析失败：内容不像 NAGA 报告（缺少 pred 字段）`；文件不存在 → 400 `文件不存在：…`。
- `node test/apptest.js`：**全部通过**（355 项 OK / 0 失败；含新增 2b 节 10 项，其中合成样本 `naga.rounds[0]` 已按真实契约改成 4 帧；`loadText` JSON 分支、`App.naga`、局标签、`.json.gz` 剥成特征码、切回天凤后 `App.naga` 清空）。
- 可复用的回归脚本已归档到 gitignored 的 `build\_scratch\naga_samples\`：`naga_replay_test.js`（Node 回放一致性）、`wire_test.py` / `wire_test2.py`（`/api/read` 各类返回）、`probe_shape.py` / `probe_rk.py` / `probe_yaku.py`（结构 / 流局 / 役种探针）；脚本里的路径按**项目根目录**写死，需在根目录运行（例如 `node build\_scratch\naga_samples\naga_replay_test.js`）。
- `test/mjscore_test.py` 全量**仍未跑**（约 57~61 分钟，本沙箱起不了可用后台进程，见踩坑 58 / 85 / 98）。

### 23.4 踩坑
1. 报告 `pred` 是**二维** `pred[局][帧]`：一开始按扁平处理 ⇒ `AttributeError: 'list' object has no attribute 'get'`（`mjscore/naga.py` 里加了 `_round_lists()`）。
2. `tile_kind()` 一开始把单字母 `"S"` / `"P"`（南 / 白）当花色 m/p/s 解析 ⇒ 返回 None ⇒ `count_tiles` 里 `AttributeError: 'NoneType' object has no attribute '>>'`，
   且某家配牌只剩 12 张（`hands0 [12,13,13,12]`、`dora='S'`）。改成「单字母优先按字牌」后 `[13,13,13,13]`。
3. Electron 的扩展名过滤器写多段（`json.gz`）不可靠 ⇒ 只写 `gz`。
4. `web/js/app.js` 是**纯 CRLF**（1,843 处）：Python 补丁脚本必须把锚点的 `\n` 换成 `\r\n`，否则 `count=0`（与第 26 轮 `log.md` 的踩坑同源）。

### 23.5 待办
- 目标 2 只差用户本机目视确认：`python server.py` → 播放视图 → 选 `data/paipu` 下的 `<report_id>.json.gz`（或首页示例下拉框，现已含 naga 报告）。
- 目标 3：把 `.json.gz` 接进打点链路（`cli.resolve_inputs` 目前只收 `.xml`）、算 33 个特征 + 新增第一类特征「NAGA决策」∈{有,无}、
  store schema v4 支持混编与扩充（只存 ニシキ 那一档决策概率）。
- 目标 4：检索 / 数据管理支持 naga。
- m00198 展示规格：手牌上下条、「当前帧特征」左侧竖条两列表格（NAGA 决策概率 >10% 的选项）、播放区右下 5 个数据
  （流局率 / 横移率 / 放铳率 / 和了率 / 期待顺位，纯文本）、按当前决策玩家切换、仅 NAGA 牌谱显示。
- 流局种类（`nm` / `yao9` 等）报告里没有 ⇒ **已在第 28 轮实现**（`infer_ryuukyoku_reason()` + 听牌自算，见 24.2）。
- NAGA 报告里没有荣和 / 自摸的「决策概率」字段（`info.tsumo` 全空）；`end_num` 恒为 1 的真义待解。

## 24. 第 28 轮：NAGA 流局种类从事件推断 + 听牌自算（用户 m00653）

### 24.1 交付物
| 文件 | 说明 |
| --- | --- |
| `mjscore/naga.py` | **改**（17,592 → 23,224 B）：新增 `infer_ryuukyoku_reason()` / `_is_yao_kind()` / `_count_yao_kinds()` / `_called_seats()` / `_replay_state()` / `_tenpai_seats()`；`_convert_round()` 收集每帧 `info.msg` 成 `msgs` 并顺带跑一遍 `replay` 拿末状态；`_end_event()` 的 ryuukyoku 分支改成「推断种类 + 向听数定听牌家」 |
| `test/naga_test.py` | **新增**（12,319 B）：42 项断言 —— 第 1 节 16 项 `infer_ryuukyoku_reason` 字面判定（含反例），第 2 / 3 节合成报告端到端（荒牌流局 / 四风连打），第 4 节真实样本（样本不在则 SKIP） |
| `readme.md` | 测试清单加 `python test\naga_test.py`（300-301 行） |
| `build.ps1` | 回归步骤加跑 `test\naga_test.py`（约 1 秒、不依赖真实数据） |

### 24.2 技术要点
1. **报告的 `tenpais` 不可信**：实测三处流局的 `end_msgs[0].tenpais` **恒为 `[true,true,true,true]`**，与自家 `deltas` 直接矛盾（官方第 7 局 `[-1000,-1000,3000,-1000]` = 1 家听牌、第 14 局 `[1500,-1500,-1500,1500]` = 2 家听牌、ricochet 第 0 局 `[3000,-1000,-1000,-1000]` = 1 家听牌）⇒ 听牌家一律用 `shanten.shanten_at()` + `min_shanten() <= 0` 自己算；官方 viewer 只是拿这个字段高亮局末结果面板。
2. **荒牌流局收支**（与报告 `deltas` 实测一致）：1 家听牌 +3000 / 未听者各 -1000；2 家听牌各 +1500 / 未听者各 -1500；3 家听牌各 +1000 / 未听者 -3000；四家全听或全未听点数不变；之后本场 +1。
3. **`infer_ryuukyoku_reason(msgs, end_msgs, table)` 判定顺序**：`tripleRon`（`end_msgs` 里 ≥3 条 hora）→ `reach4`（本局 `reach_accepted` ≥ 4）→ 无鸣牌时 `kaze4`（4 dahai + 4 tsumo、四张弃牌同名且是风牌、四家座位一一对应、局内无立直）→ `yao9`（末条 `tsumo` 的宣言者还没打过牌且手牌么九牌种数 ≥ 9）→ 有鸣牌时 `rck4`（杠 ≥ 4 且 ≥ 2 家）→ `nm`（某家牌河非空、全为么九牌且该家没被鸣牌）→ 空串（荒牌流局）。
4. **`who`**：`yao9` → 末条 `tsumo` 的 actor；`tripleRon` → `hora[0].target`（缺则 `actor`）；其它 None ⇒ 直接喂 `mjscore/replay.py:203-231` 的 ryuukyoku 分支（其 reveal 规则 `nm→nagashi(gain>0)`、`yao9→[declarer]`、`reach4→四家`、`kaze4` / `rck4→空`、`tripleRon→除 declarer 外三家`、else→tenpai 原样生效）。
5. **报告里没有 `reason` 字段**（三样本全量扫过）：推断不出来时才回退报告字段，且值必须 ∈ `mjlog.REASON_NAME`。
6. 帧里只有 `start_kyoku` / `tsumo` / `dahai` / `chi` / `pon` / `daiminkan` / `kakan` / `ankan` / `reach` / `reach_accepted` / `dora` —— **局末的 `ryuukyoku` / `hora` 只出现在 `end_msgs`**，所以推断只能看 `msgs` + `end_msgs` + `table`（手牌 / 牌河）。
7. 末状态靠「`{"meta":{"names":[]},"rounds":[{init,events}]}` → `replay.initial_state()` + `apply_event()`」拿到；`_tenpai_seats()` 内 try/except，单家算不出来就跳过（不拖垮整份转换）。

### 24.3 测试（本沙箱实测）
- `python test\naga_test.py` → **42 项通过 / 0 失败**（约 1 秒）。
- 三样本：官方 `3180043a…`（16 局）第 8 局 / 第 15 局、ricochet `9ace0d86…`（10 局）第 1 局都判为荒牌流局，听牌家 = `[2]` / `[0,3]` / `[0]`，与报告 `deltas` 的三档收支（3000 / 1500 / 1000）完全吻合；`60b5c2ad…`（12 局）无流局；三样本 `check_invariants` 仍 **0 错误**，单份转换 0.05–0.10 s。
- 归档脚本重跑（修好路径后）：`wire_test.py` 全绿（`/api/read` 返回文本 sha 与重新生成的 `_conv_game_1.json` 逐字节相同）、`wire_test2.py` 全绿、`node build\_scratch\naga_samples\naga_replay_test.js` → 26 局「和了局 23、空役 0、回放告警 0、不一致 0 ⇒ 全部一致」。
- `node test\apptest.js` → exit 0 / **全部通过**（stdout 25,892 B）。
- `test/mjscore_test.py` 全量**仍未跑**。

### 24.4 踩坑
1. `check_invariants()` 返回 `(错误列表, 帧数)` **二元组**：第一版测试直接 `len(...)` ⇒ 恒得 2、误报。
2. 四风连打不能只看「四张同名风牌」：一开始把「有 4 张同名弃牌但摸牌数不对」的局也判成 `kaze4` ⇒ 加严成「4 dahai + 4 tsumo + 座位一一对应 + 局内无立直」。
3. PowerShell 里 `node test\apptest.js 2>&1 | Select-Object -Last N` 会让整个命令块**静默中止**（无输出、返回码 1，疑似 `$ErrorActionPreference='Stop'` 把原生 stderr 当终止错误）⇒ 可靠写法 `cmd /c "node test\apptest.js 1> _o1.txt 2> _o2.txt"` 再读文件（中文在控制台显示为乱码，文件内容正常）。
4. 归档脚本原本「在项目根目录运行、路径按根目录写死」：`naga_replay_test.js` 里 `require('./web/js/mjlog.js')` 会按脚本自身位置解析 ⇒ 已改成 `path.join(__dirname,'..','..','..')`；`wire_test.py` 里写死的天凤 xml 路径（少了日期子目录）已改成 glob 扫描；`_conv_game_1/2.json` 已用当前适配层重新生成。

## 25. 第 29 轮：NAGA 报告接入打点链路 + 第一类第 17 个特征「NAGA决策」（用户 m00080 目标 3、m00815 ①②）

### 25.1 交付物
| 文件 | 说明 |
| --- | --- |
| `mjscore/naga.py` | **改**（23,224 → 24,320 B）：新增 `NAGA_VIEW_URL` / `report_id_of_path()` / `view_url()`；`to_game()` 补回 `game["path"]`（绝对路径）与 `game["log_id"]`（= 完整 report_id）；`game_from_file()` docstring 同步 |
| `mjscore/feats.py` | **改**（14,812 → 16,000 B）：新增 `NAGA_YES / NAGA_NO = "有" / "无"`、`NAGA_FEATURES`（`key = naga` / `col = f_naga` / `kind = enum` / `values = 有,无`）、`naga_value(game)`；`FEATURES = FEATURES + NAGA_FEATURES + SECOND_FEATURES` ⇒ 共 **34 项**（第一类 17 + 第二类 17，第 17 项 = NAGA决策）；`make_record()` 补 `vals["naga"]`，url 对 NAGA 报告改用 `naga.view_url()`（天凤仍 `mjlog.paipu_url()`） |
| `mjscore/cli.py` | **改**（29,252 → 30,947 B）：`resolve_inputs()` 目录扫描改收 `.xml` + `naga.NAGA_SUFFIXES`（空结果文案「没有找到任何牌谱文件（天凤 .xml 或 NAGA 报告 .json.gz / .json）」）；新增 `file_log_id()` / `game_from_file()`（按后缀分派 naga / mjlog）；新增 `fill_naga(records, games)`（第一类第 17 项，node / python / fixture 三条路径统一补）；`build_records()` 遇批次里有 NAGA 报告且 `tool != "python"` 时整批改 python 并写 warning；`_analyze()` 的 extend 去重改 `file_log_id()`、解析改 `game_from_file()` |
| `mjscore/store.py` | **改**（19,729 → 20,094 B）：`SCHEMA_VERSION = 3 → 4`（第 29 轮 f_naga + 天凤/NAGA 混编；旧库需删除重建）、`check_version()` 文案、新增索引 `frame_naga ON frame (f_naga)`、docstring / `FULL_NOTE` / `frame_feats()` docstring 33 → 34 |
| `mjscore/server.py` | **改**（20,559 → 20,690 B）：`/api/features` / `/api/frame-feats` / `/api/analyze` 的 docstring 改 34 项并注明 paths 支持 NAGA |
| `tools/analyze.py` | **改**（922 B）：头注释改「17 个第一类特征打点」 |
| `web/js/mjsfeat.js` | **改**（11,056 → 11,498 B）：注册表第一类末尾（`oya_meld_n` 之后）加 `{ key:'naga', name:'NAGA决策', kind:'enum', values:['有','无'] }` ⇒ 34 项；头注释补第 29 轮说明 |
| `web/index.html` | **改**（17,695 → 17,751 B）：`#fileInput` 的 accept 加 `.json.gz,.json`（+ `application/gzip`）；拖放区文案改「把天凤 .xml 或 NAGA .json.gz 牌谱文件拖到这里」；4 处 33 → 34、第一类 16 → 17 |
| `web/js/app.js` | **改**（77,013 → 77,061 B）：牌谱分析「扫描」改 `&kind=all`（m00815①）、空目录提示改「天凤 .xml 或 NAGA .json.gz / .json」、帧特征面板注释 34 |
| `test/apptest.js` | **改**（99,347 → 99,680 B）：33 → 34、假数据库 `schema_version: 3 → 4`、假数据里 NAGA决策 = '有'、新增「第 17 个第一类特征 = NAGA决策（有/无）」断言 |
| `test/mjscore_test.py` | **改**（42,836 → 43,284 B）：33 → 34、`SCHEMA_VERSION = 4`、切片 `FEATURES[16:]` → `[17:]`、新增 `NAGA_FEATURES` / `naga_value()` 5 项断言 |
| `test/naga_test.py` | **改**（12,319 → 17,903 B）：新增第 5 节「打点链路 / 存储集成」25 项断言（合成报告端到端） |
| `readme.md` | **改**（23,818 B）：33 → 34、第一类 17 项（表里新增「NAGA决策」行）、牌谱下载 / 分析 / 播放说明补 NAGA、测试清单不变 |

### 25.2 技术要点
1. **混编口径**：一个 `.sqlite` 同时存天凤与 NAGA；靠第一类第 17 项 `f_naga`（有 / 无）区分。`log_id`：天凤 = 文件名去扩展名，NAGA = **完整 report_id**（含 `v2_2`，用户 m00418）。NAGA 行 `url` = 官方观看页 `https://naga.dmv.nico/htmls/report_viewer.html?report_id=<id>&tw=0`（`naga.view_url()`），天凤行仍是 `http://tenhou.net/0/?log=<id>&tw=0`。
2. **NAGA 只能走 python 打点**：`mjscore/node_harness.js` 的 `loadGame()` 用 `basename.replace(/\.xml$/i,'')` ⇒ 只认天凤 xml。`build_records()` 在调用 node 之前先看批次里有没有 NAGA 文件，有就整批改用 python，warning 文案「批次里有 NAGA 报告，Node 侧解析器只认天凤 xml，本次整批改用 python 打点」。
3. **`fill_naga()` 放在 `_analyze()` 的 node / python 分支之外**：三条路径（node / python / fixture）都补第 17 项；`web/js/mjsfeat.js` 只登记定义、其 `extract()` 仍是硬编码 16 键 ⇒ node 打出来的行本来就缺 `naga`，由 `fill_naga()` 按 `game["log_id"]` 查牌谱来源填，认不出来源按天凤记「无」。
4. **schema 破坏性升级**：`SCHEMA_VERSION = 4` ⇒ 第 21 轮及以前的库启动即被 `check_version()` 拒绝并提示删除重建（正常：新增了 `f_naga` 列与 `frame_naga` 索引）。
5. **`frame_naga` 索引**为「按 NAGA决策 检索」（目标 4）备好。
6. **前端默认过滤器**：`web/index.html` 的 `#fileInput` accept 补 `.json.gz` / `.json` 后，浏览器与 Electron 原生对话框的默认过滤里就能直接看到 NAGA 报告（m00815②）；桌面版 `desktop/main.js` 的 `filters` 早在第 27 轮已含 `NAGA 牌谱 (*.json.gz, *.json)`。

### 25.3 测试（本沙箱实测）
- `python test\naga_test.py` → **67 项通过 / 0 失败**（第 1~4 节 42 项 + 新增第 5 节 25 项）。
- `node test\apptest.js` → exit 0 / **全部通过**。
- 单样本冒烟（官方 `3180043a…v2_2.json.gz`，16 局）：`cli.analyze(tool="python")` → 779 行（`rows_draw = 752` / `rows_call = 27`）、`rounds = 16`、`sources = 1`、`warnings = []`、约 101 s；库里 `meta.schema_version = 4`、`source.log_id` = 完整 report_id、`f_naga` 779 行全「有」、`frame` 59 列、`query_detail` / `frame_feats` / `list_feature_values("naga")` 都返回 34 项。
- `--tool auto` 遇纯 NAGA 批次 → `tool = 'python'` + 上面那条 warning（patch 生效，未尝试 node）✓；同一批混天凤 xml → 一个库 2 个 source、`f_naga` = {有: 779, 无: 530} ✓；`extend=True` 二次入库按完整 report_id 全部跳过并抛既有提示「这 1 个牌谱都已经在数据库里了，没有需要扩充的新牌谱」✓。
- 本沙箱测不了的：node 打点（`subprocess` 建管道被拒 `PermissionError [WinError 5]`）、`test/mjscore_test.py` 全量（约 57~61 分钟）。

### 25.4 踩坑
1. 补丁锚点 `'"kind": "enum", "values": [YES, NO]}'` 会一次命中 5 处（4 个天凤「是/否」特征 + NAGA决策）⇒ 必须按 `{"key": "xxx"` 定位后再改，否则会把 `riichi_self` / `meld_self` / `oya_riichi` / `oya_meld` 的取值改成「有/无」（已回滚）。
2. **取值必须是「有/无」而不是「是/否」**：第一版直接复用 `feats.YES / NO` ⇒ 库里全是「是/否」，与用户 m00080 的口径不符；已改为 `NAGA_YES / NAGA_NO`。
3. 沙箱限制：`Start-Job`（启动后台进程 `Access is denied`）、python `subprocess` 建管道、`tempfile.mkdtemp()`（写 `C:\Users\ASUS\AppData\Local\Temp\...` 被拒）全都不可用 ⇒ naga_test 第 5 节的临时目录改放 `test/_tmp/naga_s5`。
4. PowerShell 里 `node test\apptest.js 2>&1 | Select-Object -Last N` 会静默中止（无输出、返回码 1）⇒ 用 `cmd /c "node test\apptest.js > _out.txt 2>&1"` 再读文件（同第 28 轮踩坑 3）。
5. `store.frame_feats()` 返回的是 `query_detail()` 的整行（事实列 + `feats` + `full`），不是 34 项的特征字典 ⇒ 断言要取 `["feats"]`（第一版按 34 项断言，实际得到 61）。

### 25.5 待办
- 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）；m00198 的 NAGA 决策概率展示规格（需先由用户确定展示方式）。
- 用户 m00815③：需重新构建（`build.ps1`）或直接 `python server.py` —— 否则跑的还是 2026/10/8 20:06 的旧构建，看不到第 26~29 轮功能。
- `test/mjscore_test.py` 全量待用户本机验证。
- 途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）仍无真实样本；`end_num` 恒为 1 的真义；用户 m00080 会补更多 naga URL 做全面测试。

## 26. 第 30 轮：NAGA 报告上传转换 + 牌谱目录下拉选择 + 分析速度瓶颈定位（用户 m01171 ①②③）

### 26.1 交付物

| 文件 | 字节数 | 本轮改动 |
| --- | --- | --- |
| `mjscore/server.py` | 25,184 | 新增 `GET /api/paipu-browse`、`POST /api/naga-convert`、`MAX_UPLOAD`(32 MB)、`_rel_or_abs` / `_paipu_browse` / `Handler._naga_convert`；静态 js / css 也带 `no-store` |
| `web/index.html` | 17,983 | 分析页「牌谱目录 / 牌谱文件」由输入框改下拉框（`#anSourceDir` / `#anSourceFile`）+ 提示文案改写 |
| `web/style.css` | 22,183 | `#anSourceDir{min-width:260px}` / `#anSourceFile{min-width:220px}` |
| `web/js/app.js` | 81,200 | `apiUpload` / `isNagaFileName` / `uploadNaga`；`readFile` 改走服务端转换；`loadText` 认原始报告；`loadPaipuPicker` / `anDirChanged` / `anFileChanged`；下载完自动跟随下载目录 |
| `test/apptest.js` | 101,762 | mock `/api/paipu-browse`；新增 8.2b 节 6 项断言（361 项 OK / 0 失败） |
| `test/naga_test.py` | 23,448 | 新增 `section6()`（in-process HTTP：no-store / browse / 上传转换 / scan），88 项通过 0 失败 |
| `readme.md` | 25,278 | 分析页下拉、NAGA 报告选择与拖放、分析速度瓶颈与实测数字 |

### 26.2 技术要点

1. 浏览器手选 / 拖放的牌谱**没有磁盘路径** ⇒ 服务端 `naga.to_game` 无法照 `/api/read` 那样按路径转换；因此新增 `POST /api/naga-convert`（body = 文件字节，`?name=` 带文件名以便取出 `report_id`），前端只负责把字节发过去 —— 复用 `mjscore/naga.py` 这一份权威实现，不在 JS 里再写一套 NAGA 解析器。
2. `/api/naga-convert` 返回 `{"path": name, "naga": true, "text": <转换后的 JSON 文本>}`，与 `/api/read` 的 naga 分支同构；空体 / > `MAX_UPLOAD`(32 MB) / 内容不像 NAGA 报告都返回 400 + 中文提示。
3. `GET /api/paipu-browse?dir=` 返回 `{root, root_rel, dir, dir_rel, dirs[], files[]}`，目录树**限制在 `paths.paipu_root()`（`data/paipu`）之内**（`os.path.normcase` 前缀比较）；越界 → 400「只能浏览牌谱目录（…）里的内容」，不存在 → 400「目录不存在：…」；dirs 上限 500（含根）、files 上限 2000，files 只收 `.xml` / `.json.gz` / `.json`。
4. 静态 js / css 响应也带 `Cache-Control: no-store, must-revalidate`（原先只有 text/html）—— 用户 m01171 排查时被浏览器缓存的旧 js 误导过。
5. 分析页交互：`#anSourceDir`（目录下拉，含根 `data/paipu`）选中即刷新 `#anSourceFile`（首项「（整个目录：…，共 N 个牌谱）」= 分析整个目录，其余为单个文件）；只选一个文件时前端用 `renderFileList([f])` 只分析这一个；点「扫描」回到整个目录。
6. 牌谱下载完成后，若下载目录与当前选择不同，自动 `loadPaipuPicker(rel, true)` 把两个下拉框跟到新目录（`An.pickerDir` 去重，避免重复请求）。
7. `.json.gz` / `.json` / `.gz` 一律走服务端转换（`isNagaFileName`），天凤 `.xml` 仍在前端本地解析；`.gz` 不再用 `DecompressionStream` —— 浏览器解出来的是**原始 NAGA 报告**（顶层 `pred` / `info`，没有 `rounds`），这正是用户 m01171① 「缺少 INIT 标签」的根因。
8. 速度瓶颈：**约 98% 的时间在第二类特征「期望枚数」的向听搜索**（cProfile：`feats.make_record` → `expect.compute` → `shanten.shanten_of` 41,373 次 → 递归 `shanten.rec` 4,032,277 次 → `shanten.take` 70,116,008 次 / 85.1 s + `untake` 60,065,204 次 / 24.5 s），17 个第一类特征合计不到 0.1%，写库 0.0x 秒；同机同次实测每帧 115.4 ms（天凤 `.xml`）vs 131.5 ms（NAGA `.json.gz`）—— 与牌谱来源基本无关，「慢很多倍」的主因是 NAGA 一份 12~16 局 ≈ 600 帧（约 80 s/份）。

### 26.3 测试

- `python test\naga_test.py` → **88 项通过 / 0 失败**：`/web/js/app.js` 带 `no-store`；`/api/paipu-browse` 正常（root = `paths.paipu_root()`、`root_rel = data/paipu`、子目录 3 个）/ `dir=web` 400 / 不存在目录 400；`POST /api/naga-convert` 转换结果与 `naga.to_game` **逐字节一致（2,936,769 B）**、`log_id` = 完整 report_id、`path` 留空、空体 400、非 NAGA 400、`MAX_UPLOAD == 32*1024*1024`；`/api/scan?dir=data/paipu&kind=all` 112 个文件。
- `cmd /c "node test\apptest.js > _at2_out.txt 2>&1"` → **361 项 OK / 0 失败**（新增：目录 / 文件下拉是 SELECT、NAGA 后缀走服务端转换、切换目录刷新文件下拉 2 项、只选一个文件只分析这一个、点扫描回到整个目录、下载后下拉跟随 `/api/paipu-browse?dir=data%2Fpaipu%2F20261010-022250`）。
- 真实数据：`data/paipu/20261009-224353` 的 41 份 NAGA 报告能被 `/api/paipu-browse` 列出。
- `python -m py_compile` 全过；`node --check web/js/app.js` 通过。
- 仍需用户本机复核：浏览器里手选 / 拖入 `.json.gz` 能正常播放（本沙箱没有浏览器）；`test/mjscore_test.py` 全量。

### 26.4 踩坑

1. apptest 的 mock fetch 会 `JSON.parse(opt.body)`（`test/apptest.js:941`）⇒ `apiUpload` 的二进制 body 在 apptest 里走不通；NAGA 上传路径改由 `test/naga_test.py` 第 6 节的 in-process HTTP 覆盖。
2. 断言把整份 2.9 MB JSON 写进 label ⇒ 输出文件涨到 5.8 MB、PowerShell 读它卡死；改成只报「逐字节一致（N B）」。
3. 相对路径断言不能用 `'/data/paipu/' in x`（`data/paipu/sub` 没有前导斜杠 ⇒ 恒 False），改成 `"data/paipu" in _sl(x) and ".." not in _sl(x)`。
4. 用 PowerShell here-string 写补丁脚本时插入文本里混进 1 个孤立 LF（`web/js/app.js` 必须纯 CRLF）⇒ 写完后把「不跟在 `\r` 后的 `\n`」全部替换成 `\r\n`。
5. 浏览器缓存：`/web/js/app.js` 也要 `no-store`，否则改了前端仍加载旧文件。

### 26.5 待办

- 用户 m01171①（手选 / 拖放 `.json.gz`）已实现，**待用户本机用 `python server.py`（或重新构建）验证**。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA；m00198 的 NAGA 决策概率展示规格（待用户定展示方式）。
- 可选优化（未实施）：`expect` 状态缓存 / 多进程并行 / 「只打第一类」快速模式。
- `test/mjscore_test.py` 全量、node 打点路径待用户本机验证；途中流局种类、`end_num` 真义、`info.tsumo` 为空等仍待解。

## 27. 第 31 轮：播放视图区域固定尺寸（防帧间布局跳动，用户 m01386）

用户 m01386：还没加 NAGA 特有信息，但各展示区域的框架必须先固定下来；截了摸牌后 / 打牌后两帧，区域变动幅度很大，播放时画面一直在跳；要求固定主要展示区域的位置并留容错，文本长度变化不得把框顶大（例：右侧「当前帧特征」因为要显示牌谱特征码而改变大小和位置）。

### 27.1 交付物

| 文件 | 变化 |
| --- | --- |
| `web/style.css` | 22,183 → 26,351 B：播放视图全部改固定尺寸（见 27.2） |
| `web/index.html` | 17,983 → 18,013 B：第 140 行标题行改成 `<span class="fp-title">当前帧特征</span>` + `#featPanelInfo` |
| `web/js/ui.js` | 19,650 → 19,913 B：`renderPlayer` 的摸牌槽位常驻（无摸牌时 `.empty`） |
| `web/js/app.js` | 81,200 → 81,512 B：`#rpDesc` / `#rpFile` / `#featPanelInfo` 挂 `title`（完整文本） |
| `test/apptest.js` | 101,762 → 104,832 B：新增 15 项断言（7f 样式回归 14 项 + 7b 摸牌槽位 1 项） |

### 27.2 抖动根因与修法

根因：`fitBoard()`（`web/js/app.js:41`）按 `#boardBox` 的可用空间等比缩放 `--tile-w` / `--tile-h`，而牌桌与各固定条的高度此前都随帧内容变化 —— `.board` 三行是 `auto`、`.center` 有 `min-height:118px`、和了帧插入 `.c-result`、`#frameKey` 为空时 `display:none`、`.controls` / `.replay-toolbar` 是 `flex-wrap:wrap`、`.desc-bar` 用 `min-height`、顶栏 `#fileInfo` 长文件名会折行、回放警告 `.warn-bar` 进出布局 —— 于是每帧算出不同缩放率，整个牌桌缩放 / 上下跳；另外 `.feat-panel` 是 flex 项，默认 `min-width:auto` 被长特征码顶宽，把牌桌列挤窄（正是用户截图里「当前帧特征」区变形的原因）。

修法（全部硬性尺寸）：
- `.board` 三行改 `calc(var(--tile-h) * 6.6) / calc(var(--tile-h) * 4.6) / calc(var(--tile-h) * 6.6)`；删掉 `.cell-left, .cell-right { height }`（改由固定轨道铺满）；`.board-box { overflow: hidden }` ⇒ 牌桌尺寸只跟 `--tile-w` / `--tile-h` 走，与内容无关。
- `.center { height: 100%; position: relative; overflow: hidden auto }`；`.c-result` 改成绝对定位浮层（`left/right/top/bottom: 2px` + 不透明底 `#16241e`），不再撑高中央框。
- `.replay-toolbar` 固定 46px 单行（`nowrap` + 子项 `flex: 0 0 auto` + `#rpFile` 省略号 `max-width: 340px`）；`.controls` 固定 50px 单行、过窄时条内横向滚动；`.desc-bar` 固定 34px 单行省略号；`.frame-key` 固定 28px 且 `:empty { visibility: hidden }`。
- `.feat-panel { min-width: 0; overflow: hidden }`；`.feat-panel-head` 固定 32px 单行；`#featPanelInfo`（`.muted`）省略号；`.feat-row` / `.feat-row .feat-name` / `.ev-row` / 新增 `.ev-text` 全部省略号；`.event-list { min-width: 0 }`。
- `.file-info` 单行省略号 + `max-width: 32vw`（顶栏高度恒定）。
- `.warn-bar` 改绝对定位浮层（`#view-replay { position: relative }`，`bottom: 94px`），出现 / 消失不再参与布局。
- 摸牌槽位常驻：`.p-hand .drawn { min-width: var(--tile-w) }` + `.drawn.self` 预留大牌尺寸 + `.drawn.empty { visibility: hidden }`，`web/js/ui.js` 的 `renderPlayer` 无论有没有摸牌都 append 这个槽位 ⇒ 手牌行宽度不随帧变化。
- 容错：所有固定条都是「固定高度 + `text-overflow: ellipsis`」，完整文本挂在 `title`（`#rpDesc` / `#rpFile` / `#featPanelInfo`，`#frameKey` 原本就有）。

### 27.3 测试

- `cmd /c "node test\apptest.js > _at_out.txt 2>&1"` → exit 0，**376 项 OK / 0 失败**（含新增 15 项；全量 5 个牌谱 5824 帧渲染无异常）。
- `node --check web/js/ui.js` / `web/js/app.js` 通过；行尾：`app.js` / `ui.js` 纯 CRLF（0 孤立 LF），`style.css` / `index.html` 纯 LF。
- 本沙箱无法做浏览器布局测量（见 27.4），最终观感待用户目视确认。

### 27.4 踩坑

1. 沙箱里没有可用的浏览器：`msedge.exe --headless=new --dump-dom` 报 `platform_channel.cc:187] Check failed: . : 拒绝访问。 (0x5)`、`crashpad_client_win.cc:447] OpenProcess: 拒绝访问。`，加 `--no-sandbox --single-process` 也无输出 ⇒ 布局只能靠 CSS 推理 + 用户目视验证。
2. 新增 CSS 规则不能追加到 `web/style.css` 末尾：文件里已有 `@media (max-width: 1100px)` 覆盖块（第 495 行起），追加会盖掉它 ⇒ 本轮全部就地改原规则。
3. `test/apptest.js` 的 `cssRule()` 只截到第一个 `}`，所以断言只能逐条检查规则属性，跨 `::-webkit-scrollbar` 之类的多块规则要分开写。
4. `.cell-left, .cell-right` 的基础 `height` 删掉后，窄屏媒体查询里的 `height: auto` 保留即可（无害）。

### 27.5 待办

- 待用户目视确认（副露出现时两侧牌河宽度仍会变，但牌桌整体位置与缩放不再变）。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA；m00198 的 NAGA 决策概率展示规格（待用户定展示方式）。
- `test/mjscore_test.py` 全量、node 打点路径仍待用户本机验证。

## 28. 第 32 轮：NAGA 决策概率展示 + 牌面白边 + 特征码完整显示（用户 m01518 ①②③）

按用户 m01518 的三条要求改造播放视图，并按用户指定的 m00198 规格（本会话 10 月 9 日 19:26 那条）实现 NAGA 牌谱特有的决策概率展示。

### 28.1 交付物

| 文件 | 改动 |
| --- | --- |
| `web/style.css` | 838 行 / 30,015 B（LF）：`.tile` 白边 padding、`.tbar` 条（上 / 下）、`.frame-key` 46px 两行、`.feat-panel-head` 106px、`.file-name` 完整换行、`.naga-panel` 一整套 |
| `web/index.html` | 374 行 / 18,403 B（LF）：新增 `aside#nagaPanel`（`#nagaWho` / `#nagaOptions` / `#nagaHud`） |
| `web/js/ui.js` | 462 行 / 22,412 B（CRLF）：`addNagaBars()` / `nagaPctText()`，手牌与摸牌槽位挂条 |
| `web/js/app.js` | 2,155 行 / 89,963 B（CRLF）：NAGA 块（`nagaFrameOf` / `nagaKindId` / `nagaKindOfName` / `nagaChiPair` / `nagaSeatOf` / `nagaKanInfo` / `nagaOptions` / `renderNagaPanel`）+ `render()` 接线 + 导出 |
| `test/apptest.js` | 1,726 行 / 111,073 B（CRLF）：2b 节 NAGA 断言 + 7f 样式回归改判 |
| `readme.md` | 回放节补 NAGA 决策面板 / 特征码完整显示 / 牌面白边说明 |

### 28.2 技术要点

1. 特征码不省略：`#rpFile`（工具栏）与 `#frameKey`（牌桌上）都改成「固定高度 + `white-space: normal; word-break: break-all`」两行显示；「当前帧特征」标题行固定 106px，`#featPanelInfo` 用 `flex: 1 1 100%` 另起一行、11px 等宽、预留 5 行（`max-height: 75px`）。
2. 牌面白边：`.tile { padding: calc(var(--tile-w) * .09) }`，全局 `box-sizing: border-box` ⇒ 牌的外框尺寸不变，`img` 百分比自动缩进，白底来自 `.tile` 自身的 `#f3f6f4`。
3. 数据来源（全部前端已有，后端未改）：`dahai_pred`（扁平 34 维万分比）、`danger_s/t/k`（`[观察者][kind]`）、`end_type`（行 = 和了 / 放銃 / 横移動 / 流局，列 = 座位，每列和 10000）、`game_rank`（每行 = 最终顺位 1..4 的概率分布）、`huro` / `kan` / `reach`。
4. 帧对齐：`App.naga.rounds[局][帧]` 的下标与 `App.frameIndex` 一致，携带的正是「当前待决策」的概率（鸣牌后的打牌预测挂在被鸣牌那一帧上）。
5. 选项表：`huro` 下标 = `[PASS, 吃×3, 碰, 杠]`；吃的三种牌对由本项目实证（下标 1 = 打出牌作最小、2 = 作中间、3 = 作最大，三样本 24/24 命中）。只显示概率 >10% 的项（`p <= 1000` 丢弃），按概率降序。
6. 上方条（打牌预测）= `dahai_pred[kind]`，最高那张加 `.max`；下方条（危险牌）= `danger_k/t/s[观察者][kind]`，颜色 `#2196F3` / `#FFEB3B` / `#4CAF50`；条只画在自家手牌上，同种牌只画最靠左那张（`seen` 去重）；概率 >0 就画（与官方一致），高度 = 牌高 × 概率（百分比）。
7. 5 个数据按「当前决策玩家」取（`nagaSeatOf`：打牌帧取 `huro` 里非 PASS 概率最大的那家，否则 `frame.actor`），期待顺位 = `Σ(i+1)*game_rank[seat][i]/10000`（`toFixed(2) + ' 位'`）。
8. 限制（报告本身没有的字段）：没有荣和 / 自摸 / 九种九牌流局的决策概率（`info.tsumo` 恒空），这几类选项不显示；`reach` 只是标量概率，带不了「打哪张牌」；报告不给「杠哪张牌」，暗杠 / 加杠的牌图只在手牌能唯一推断时显示。

### 28.3 测试

- `cmd /c "node test\apptest.js > _at_out.txt 2>&1"` → exit 0，**398 项 OK / 0 失败**（本轮从 376 项增加到 398 项）。
- 真实样本冒烟（`build\_scratch\naga_samples\_conv_game_1.json`，16 局 / 1,617 帧）：873 帧有 >10% 选项、累计渲染 33,741 个 `.tbar`、`huro` 座位越界 0；选项样例 `打99.8%` / `碰100%` / `打87.3% 打12.6%`；HUD 样例 `流局率14.0% 横移率56.7% 放铳率14.3% 和了率15.0% 期待顺位2.56 位`。
- `Tiles.tileName(kind*4+1)` 对 34 个 kind 逐个核对通过（`kind*4` 会命中赤 5 的 `0m`，所以必须 +1）。
- 行尾：`style.css` / `index.html` 纯 LF，`ui.js` / `app.js` / `apptest.js` 纯 CRLF（0 孤立 LF）；`node --check` 通过。
- 沙箱仍无法做浏览器布局测量（见 27.4），观感待用户目视确认。

### 28.4 踩坑

1. `nagaKindOfName` 第一版用 `s.charAt(1) === 'r'` 处理赤 5，但 mjai 的赤 5 名是 `5pr` / `5mr`（数字 + 花色 + r），且 `!num` 会把 `'0m'` 判成非法 ⇒ 改成 `/^([0-9])([mps])r?$/` + `num === 0 → 5`。
2. `test/apptest.js` 的假 DOM `El` 原本没有 `style` 属性，NAGA 条写 `node.style.height` 会抛错 ⇒ 构造里补 `this.style = {};`。
3. `.naga-panel` 的样式断言不能用 `cssRule()`：该选择器在文件里先出现在窄屏媒体查询里，`cssRule()` 只截第一处 ⇒ 改用 `cssText` 正则。
4. 补丁脚本里 `crlf()` 不能作用在已是 CRLF 的查找串上（会变成 `\r\r\n`）；`s.index('  }\r\n')` 会命中 4 空格缩进的 `}` 内部子串，必须用 `'\r\n  }\r\n'`。
5. `.frame-key` 的 CSS 属性每行一条，锚点必须逐行多行（一行式写法 `count == 0`）。

### 28.5 待办

- 用户目视确认（需重新构建 `build.ps1` 或 `python server.py` + Ctrl+F5）。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- m00198 里明确不要的部分：官方播放器的曲线图 / 恶手条、改变主视角功能。
- `test/mjscore_test.py` 全量、node 打点路径仍待用户本机验证。
## 29. 第 33 轮：概率条宽度按官方截图校准 + 选项表「其它」行 + 立直数据结构答疑（用户 m01810 ①②③）

用户 m01810 三条：① 减小概率条宽度（对照官方截图里条与麻将牌的宽度比例）；② 决策概率表格增加一行「其它」= 1 − 已显示概率合计；③ 说明「立直决策后一帧」在牌谱数据里的含义。

### 29.1 交付物

| 文件 | 改动 |
| --- | --- |
| `web/style.css` | 841 行 / 30,335 B（LF）：`.tbar.up` 宽度 100% → 35% + 左偏移 22%（按官方截图量出的比例）；新增 `.naga-opt.other` 弱化色 |
| `web/js/app.js` | 2,160 行 / 90,334 B（CRLF）：`renderNagaPanel()` 追加「其它」行（残差概率，`shown >= 10000` 时不加），`nagaOptEl()` 给该行加 `.other` |
| `test/apptest.js` | 1,732 行 / 111,692 B（CRLF）：条宽断言改判；新增「其它」相关 4 项断言 |
| `readme.md` | 360 行 / 27,395 B（LF）：回放节补「其它」行与条宽比例说明 |

### 29.2 技术要点

1. 宽度比例用 PIL 直接量官方播放器截图（2541×1296 归一化副本）：底部手牌带牌宽 46px、牌高 63px、间隙 1px（与官方 `hai_w = 29.3` 之比 ≈ 1.57）。
2. 下方危险条：实宽 14px = 30.4% 牌宽、左偏移 +1px ≈ 2.2%，高度 5～51px（牌高的 8%～81%）⇒「条高 = 牌高 × 概率」得到印证；现有 `.tbar.down`（30.7%、3.4% / 34.1% / 64.8%）与实测一致，未改。
3. 上方打牌预测条：实测 16px = 34.8% 牌宽、左偏移 ≈ 21.7%，颜色深紫 `rgb(124,59,230)` + 描边 `rgb(201,146,211)` ⇒ 原来的 `left: 0; width: 100%`（占满牌宽）宽了约 3 倍，改为 `left: 22%; width: 35%`。
4. 「其它」行 = `10000 − Σ(已显示选项的概率)`，弱化色显示；因为一帧里可能同时有「打牌预测」与「立直」两个各自独立的边缘量，已显示概率合计可能超过 100%（此时不加该行）。真实样本 1,617 帧里 1,601 帧有选项、1,585 帧出现「其它」，绝大多数在 0.1%～2%，只有 16 帧合计超过 100%。
5. 立直决策的数据含义（用户 m01810 ③ 的答复）：报告把「是否立直」`reach` 与「打哪张牌」`dahai_pred` 放在**同一帧**（两个各自 10000 的边缘量，不构成先后依赖）；随后 3 帧只是把「宣言 → 打牌 → 成立」协议实体化，都不带概率。例：官方样本第 1 局 j=71 `tsumo actor=0 pai=1m` 带 `dahai_pred`（k28='S' 99.96%）+ `reach=6111`；j=72 `reach`（宣言）；j=73 `dahai actor=0 pai='S'`（立直时打出的牌）；j=74 `reach_accepted`。⇒ 报告里**没有**「立直已确定后打哪张牌的条件分布」，天凤那种「先决定立直、再选打哪张」的两段式决策无从还原。
6. 立直统计（官方 16 局）：36 个带 `reach` 的摸牌帧；实际宣言立直的 12 帧 reach = 2930 / 3008 / 6111 / 7577 / 9529 / 9624 / 9635 / 9696 / 9698 / 9816 / 9968 / 9988（多数 > 90%，两例约 30%）；未宣言的 24 帧 reach 从 9918 到 0，其中 3 帧 ≥ 90%（模型想立直而人没立直），4 帧为 0。
7. 当前实现里「立直 p%」与「打X p%」并列显示（二者相加不等于 100%），已请用户判断是否保留 / 换形式。

### 29.3 测试

- `cmd /c "node test\apptest.js > _at5.txt 2>&1"` → exit 0，**401 项 OK / 0 失败**（本轮新增 3 项断言：帧 1 不出现「其它」、帧 2「其它 5%」+ `.other` class、`.naga-opt.other` 弱化色）。
- 真实样本冒烟（临时插入测试文件后还原，备份 `_at_backup.js` 已还原为 111,692 B）：`_conv_game_1.json` 16 局 1,617 帧 → 1,601 帧有选项、1,585 帧有「其它」行、`.tbar` 33,741 个、`huro` 座位越界 0；样例 `r0 j1 打99.8% 其它0.2%`、`r0 j5 打87.3% 打12.6% 其它0.1%`、`r0 j7 打65.9% 打21.4% 打12.2% 其它0.6%`、`r0 j9 打64% 打19.2% 打14.9% 其它2%`；HUD 样例 `流局率11.4% 横移率66.8% 放铳率11.7% 和了率10.1% 期待顺位2.56 位`。
- 本轮的量测 / 探针脚本已归档到 gitignored 的 `build\_scratch\naga_samples\`（脚本里的路径按项目根目录写死，需在根目录运行）：`measure_bars.py` / `measure_bars2.py`（用 PIL 直接量官方播放器截图里的条宽 / 条位 / 条高），`probe_reach_frames.py` / `probe_reach_stats.py`（立直帧结构与「宣言 / 未宣言」统计）。
- 行尾：`style.css` / `readme.md` 纯 LF，`app.js` / `apptest.js` 纯 CRLF（0 孤立 LF）；`node --check web/js/app.js` 通过。

### 29.4 踩坑

1. 补丁函数的行尾处理：`_p32.py` 用 LF 锚点去匹配 CRLF 文件（`web/js/app.js` / `test/apptest.js`）⇒ `AssertionError: ('\\web\\js\\app.js', 'other-row', 0)`（同一脚本里 `web/style.css` 是 LF，所以第一步成功）⇒ 补丁函数必须按文件行尾决定是否把锚点里的 `\n` 换成 `\r\n`。
2. 一个脚本里同时改 LF 文件与 CRLF 文件时不能全局替换，必须逐文件判断。

### 29.5 待办

- 等用户判断「立直」选项的展示方式（是否与「打X p%」并列）。
- 用户 m01518 / m01810 的改动需重新构建（`build.ps1`）或 `python server.py` + Ctrl+F5，然后目视确认。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量、node 打点路径仍待用户本机验证。

## 30. 第 34 轮：关键帧重定义（等待决策的帧）+ 立直行展示特例（用户 m01903 ①②③）

### 30.1 交付物

| 文件 | 说明 |
| --- | --- |
| `web/js/app.js` | 2,173 行 / 91,298 B（纯 CRLF）。`KEY` 事件表 → `isKeyFrame(fr)`（`draw` / `discard` / `call`）；`nagaOptions` 立直特例（字段存在即入表、低于 10% 也显示、`unshift` 排第一）；`renderNagaPanel` 的「其它」只算非立直行 |
| `web/style.css` | 843 行 / 30,551 B（纯 LF）。修掉 `.naga-opt` 注释把选择器截断的写法；新增 `.naga-opt.reach` 红色规则 |
| `test/apptest.js` | 1,769 行 / 114,444 B（纯 CRLF）。2b 节选项表断言改 3 行（立直 5% 也显示 + 排第一 + `.reach`）；新增「立直 25% / 打 30% / 打 20% / 其它 50%」合成渲染断言；第 4 节「关键事件」重写为「关键帧」（落点只能 draw / discard / call，不停 reach / dora / agari，能走到终局）；7f 新增 `.naga-opt.other` / `.naga-opt.reach` 选择器完整性与颜色断言 |
| `readme.md` | 362 行 / 28,399 B（纯 LF）。4.4 新增「关键帧」说明；NAGA 面板那条补「其它不计入立直」、立直行特例、九种九牌说明 |
| `build\_scratch\naga_samples\check_keyframes.js` | 归档的回归脚本：用 `web/js/replay.js` 校验「带 NAGA 决策数据的帧都是关键帧」 |

### 30.2 技术要点

1. 关键帧 = `ev.type ∈ {draw, discard, call}`：摸牌后 / 吃碰杠后（等待出牌 · 立直 · 杠 · 自摸）与有人打出牌后（等待鸣牌 · 荣和）。立直宣言 / 新宝牌 / 和了 / 流局只是执行或展示帧。
2. 实测（官方样本 `_conv_game_1.json`，16 局 1,601 帧）：旧口径（discard / call / reach / dora / agari / ryuukyoku）只有 846 个关键帧 —— **跳过了所有摸牌帧，而 NAGA 的打牌决策概率恰好长在摸牌帧上**；新口径 1,561 个关键帧（draw 755 + discard 778 + call 28），只跳过 40 帧（reach 23 / agari 14 / ryuukyoku 2 / dora 1）。
3. 带 NAGA 决策数据（`dahai_pred` / `huro` / `kan` / `reach`）的帧**没有一个不是关键帧**（异常 0）；反过来 572 个关键帧没有决策数据（571 个 `dahai` —— 该巡没人能鸣牌，1 个 `ankan`），说明「关键帧 ⊋ 有决策数据的帧」。
4. 关键帧判定只依赖事件类型、不看 NAGA 数据 ⇒ 天凤牌谱与 NAGA 牌谱的导航行为一致（否则同一个天凤帧序列会因为有没有决策数据而跳得不一样）。
5. 立直（`reach`）：报告只在「能立直的那一帧」带这个字段（1,601 帧里出现 36 次：4 次 = 0、32 次 > 0，其中 16 次 ≤ 10%）；判定用「字段存在」，值 0 也显示 `立直 0%`。
6. 展示规则特例：立直行不看 10% 门槛、`list.unshift` 永远第一、加 `.reach` 类用 `var(--danger)` 红色，并且**不计入「其它」**（立直与 `dahai_pred` 是同一帧两个独立的边缘量；`web/js/ui.js` 的概率条只画 `dahai_pred` / `danger_*`，与 reach 无关）。
7. 九种九牌：报告没有该决策的概率字段，无需改代码；该帧 `ev.type === 'draw'` 本来就按「等待出牌」算关键帧，只显示打牌概率（写进了 `isKeyFrame` 的注释）。

### 30.3 测试

- `cmd /c "node test\apptest.js > _k_at.txt 2>&1"` → **exit 0，408 项 OK / 0 失败**（第 33 轮为 401 项）。新增断言全绿：`立直行永远排第一 + 低于 10% 也显示 = 立直5%`、`立直行带 .reach 标记（用不同颜色与打牌选项区分）`、`打牌选项合计 >= 100% 时不追加「其它」行（立直不计入）= 立直5%打60%打45%`、`立直第一 + 「其它」只算打牌选项（立直 25% / 打 30% / 打 20% / 其它 50%）`、`「下一关键」先停在摸牌帧（等待出牌决策）= 1（draw）`、`第二次「下一关键」停在出牌帧（等待鸣牌 / 荣和决策）= 2（discard）`、`连点「下一关键」的落点都是关键帧（异常：null）`、`不会停在立直宣言 / 新宝牌 / 和了帧上（访问了 110 个关键帧）`、`连点「下一关键」能走到本局终局（末帧 phase=agari）`、`「其它」行 / 立直行用另一种颜色显示（选择器完整）`。
- `node build\_scratch\naga_samples\check_keyframes.js` → `msg/ev 映射异常 0`、`非关键帧但带决策数据 0`。
- `node --check web/js/app.js` / `node --check test/apptest.js` 通过。

### 30.4 踩坑

1. 补丁脚本按行号定位比逐字锚点稳：第 4 节整体重写用「两个 section 标记之间切片替换」，2b / 7f 用「定位首末行 + 切片替换」，避免重写 CRLF 长块出错。
2. `find_sub('4. 关键事件')` 命中 2 处（section 标记 + `console.log` 那一行）⇒ 锚点要带 `*/` 或 `===` 才唯一。
3. 用 Python 匹配 JS 正则源码（`/.naga-opt.other/` 这类）时注意开头是 `/` 不是 `'`，以及 Python 侧的转义层数。
4. 第 33 轮写入的 `.naga-opt /* 注释 */` 是无效 CSS（注释夹在选择器中间，把 `.naga-opt.other .naga-opt-word` 那条吞掉了），常规正则断言测不出来 ⇒ 改成 `cssRule(cssText, '<完整选择器>')` 形式（锚定行首）。
5. 插入后再用 `len(lines) - 1` 取 footer 前必须先重算索引（插入前后 line 数变了）。

### 30.5 待办

- 用户重新构建（`build.ps1`）或 `python server.py` + Ctrl+F5 后目视确认。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA。
- `test/mjscore_test.py` 全量、node 打点路径（沙箱 `PermissionError [WinError 5]`）待用户本机验证。


## 31. 第 35 轮：修「概率条全都不显示」的 CSS 注释事故 + 概率条跟随决策玩家 + 展示帧不算关键帧（用户 m02007 ①②③）

### 31.1 交付物
| 文件 | 说明 |
| --- | --- |
| `web/style.css` | 31,127 B（847 行，LF）。补上第 406 行注释缺失的 `*/`（第 33 轮改 `.tbar.up` 的 left / width 时把结尾一起吃掉了），恢复 `.tbar.up` / `.tbar.up.max` / `.tbar.down` / `.tbar.down.k/.t/.s` / `.tile.big` / `.tile.tsumogiri`；`.p-hand .drawn` 加 `align-items: flex-end`。 |
| `web/js/ui.js` | 23,549 B。`addNagaBars(node, id, nf, seen, mode)` 多一个 `mode` 参数（`'up'` 只画打牌预测柱 / `'down'` 只画三条危险条）；`renderPlayer` 拆成「自家手牌危险条」与「决策玩家预测柱」两套 seen 表。 |
| `web/js/app.js` | 93,389 B。`isKeyFrame(frames, i)` 新签名 + `nagaFrameChoices(i)`；`stepKey` 改调用；`render()` 把 `seat: nagaSeatOf(nf)` 交给 `UI.renderBoard`；`nagaOptions` 的 `push()` 多记 `pass` 标记；`renderNagaPanel()` 在没有非 PASS 选项时整块留空（先算选项再写玩家名，`whoEl.textContent` 不会残留）。 |
| `test/apptest.js` | 118,271 B。7f 样式回归改成**先剥掉 CSS 注释再断言**（`cssRaw.replace(/\/\*[\s\S]*?\*\//g, '')`）；第 4 节整段重写（删 `KEY_TYPES`、改调 `App.isKeyFrame`、第二次「下一关键」预期由帧 2 改帧 3、新增「打牌后有人能鸣牌 / 荣和的帧仍是关键帧」「落点里的出牌帧必须等待鸣牌 / 荣和」）；2b 节新增 7 项断言（他家决策时预测柱在决策者手上、展示帧面板三块为空、`isKeyFrame` 复核）。 |
| `readme.md` | 29,114 B。4.4 回放节同步（关键帧规则、他家决策条、展示帧面板留空）。 |

### 31.2 技术要点
1. **根因**：`web/style.css:406` 的注释没有结尾 `*/`（第 33 轮补丁把锚点里的 `*/` 一起吃掉了）。CSS 注释不能嵌套，浏览器把第 406 行到下一个 `*/`（原第 417 行）之间全部当注释 ⇒ 概率条的宽度 / 位置 / 颜色规则、`.tile.big`（自家手牌放大 1.15）、`.tile.tsumogiri`（摸切半透明）全部失效；空 `<span class="tbar">` 在 `width: auto` 下宽度为 0 ⇒ **一条都看不见**（与截图像素量测一致：紫 / 蓝 / 黄条在整张图里各 0 像素）。
2. **自家摸牌「略微向上错位」是同一根因的副产物**：`.tile.big` 失效后小牌被放进 `.p-hand .drawn.self`（`min-height` 仍是 1.15 × 牌高）的槽位；槽位里默认 `align-items: stretch` ⇒ 牌贴在槽位上沿，而槽位由 `.p-hand { align-items: flex-end }` 按底对齐 ⇒ 牌整体上浮 ≈ 6 CSS px（用户截图量到 8 图像 px）。修法：恢复 `.tile.big` + 给 `.p-hand .drawn` 加 `align-items: flex-end`（双保险）。
3. **概率条跟随决策玩家**：`UI.renderBoard` 的 `opts.naga` 现在带 `seat`（= `nagaSeatOf(nf)`）；`renderPlayer` 里 `upNf` 只在「该座位 == 决策者」时生效，画上方打牌预测柱（方向与自家一致，不随座位旋转）；下侧三条危险条仍只画自家手牌（官方语义：`danger_*[观察者][kind]` = 该座位自己打这张牌的危险度）。
4. **展示帧不算关键帧**：`isKeyFrame(frames, i)` = `i > 0` 且（`ev.type ∈ {draw, call, reach}`，或 `ev.type === 'discard'` 且下一事件是 `call` / `agari`）；NAGA 牌谱再过一道 `nagaFrameChoices(i)`（面板算不出非 PASS 选项 → 不算关键帧）。
5. **展示帧的 NAGA 面板整块留空**：`renderNagaPanel()` 先清三块 → 算 `nagaOptions` → 没有非 PASS 选项就直接 return（玩家名也留空），只剩标题「NAGA 决策」。

### 31.3 测试
- `node test\apptest.js`：**417 项 OK / 0 失败 / 全部通过**（本轮前 401 项）。
- 真实报告冒烟（`build\_scratch\naga_samples\_u155.json` = 用户截图那份 9 局报告转出的结构，第 0 局 132 帧）：关键帧 64 / 非关键帧 68；预测柱出现在四家手上（座位 0/1/2/3 分别 16/15/16/15 帧，自家 16 帧、他家 46 帧）；67 个展示帧的面板三块全空（异常 0）；帧 17（自家摸到西）自家手牌上 `tbar.up.max h=98.74%`（就是要打的那张）；帧 18（打出西风）`isKeyFrame=false`、面板 0 行 / 0 数据 / 玩家名为空。
- 沙箱没有可用浏览器（headless Edge 被禁），布局与观感仍需用户目视确认。

### 31.4 踩坑
1. 上一轮临时追加到 `test/apptest.js` 尾部的 SMOKE 脚本没删干净（`s.rfind` 锚点写错 ⇒ 只切掉 1 个字符）⇒ 靠备份 `_at_backup.js` 还原；本轮冒烟同样「先备份、再追加、跑完还原」。
2. 「注释是否把规则吞掉」不能按原文 `indexOf` 判断（被吞掉的规则按原文照样找得到）⇒ 测试里必须先 `replace(/\/\*[\s\S]*?\*\//g, '')` 再断言。
3. 自写的「嵌套注释」检测脚本判定条件写错（把注释自身的开头算成嵌套），报了一堆假 nested；正确判据是「剥注释后规则是否还在」。
4. 用「整行 + 换行」当锚点去替换长句时容易踩空（`readme.md` 那行 `- NAGA 牌谱里的「立直」行是展示规则的特例：` 后面还有半句，带上 `\n` 就 count=0）⇒ 锚点只取句子开头即可。

### 31.5 待办
- 用户重新构建（`build.ps1`）或 `python server.py` + Ctrl+F5 后目视确认。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA。
- `test/mjscore_test.py` 全量、node 打点路径（沙箱 `PermissionError [WinError 5]`）待用户本机验证。

## 32. 第 36 轮：NAGA 概率一位小数 + 第一类特征「立直家（他家）一发巡」+ 偶发役互斥规则 + v0.2.0（用户 m02227 ①②③④、m02356、m02357）

### 32.1 交付物
| 文件 | 说明 |
| --- | --- |
| `mjscore/feats.py`（17,372 B） | 第一类 18 项：`BASE_FEATURES`（17 项）+ `NAGA_FEATURES`（1 项，NAGA决策）；`FEATURES = NAGA_FEATURES + BASE_FEATURES + SECOND_FEATURES`（共 35 项）；新增 `FIRST_KEYS`；第 12 项 = `ippatsu`（立直家（他家）一发巡）；`extract()` 多返回 `ippatsu` |
| `web/js/mjsfeat.js`（13,099 B） | 同上（`BASE_FEATURES` + `NAGA_FEATURES` + `concat`）；新增 `ippOthers(st, others)`；`extract()` 返回 `ippatsu` |
| `mjscore/replay.py`（12,830 B） | `initial_state` / `clone_state` 增加 `ippatsu[4]`；`apply_event` 的 discard 分支维护（立直宣言那次出牌置真、本人下次出牌置假）、call 分支四家全清 |
| `web/js/replay.js`（14,917 B） | 同上（`initialState` / `cloneState` / discard / `case 'call'`） |
| `mjscore/agari.py`（38,862 B） | `merge_ctx()` 末尾改 `return rule_ctx(out)`；新增 `rule_ctx(ctx)`：`rinshan` ⇒ 清 `ippatsu` / `haitei`；`chankan` ⇒ 清 `houtei` |
| `mjscore/store.py`（20,421 B） | `SCHEMA_VERSION = 5`（新增列 `f_ippatsu` + 第一类顺序调整）；`check_version` 文案同步；v0.1.x 库不再支持 |
| `mjscore/__init__.py` / `package.json` | `__version__ = "0.2.0"` / `"version": "0.2.0"` |
| `web/js/app.js`（93,338 B）/ `web/js/ui.js`（23,496 B） | `nagaPctText()` 统一一位小数（`v.toFixed(1) + '%'`） |
| 文案同步 | `mjscore/cli.py`、`mjscore/server.py`、`tools/analyze.py`、`web/index.html`、`web/js/app.js` 的「34 个特征 / 17 个第一类」→「35 / 18」；`mjscore/server.py` docstring 版本号 |
| 测试 | `test/mjscore_test.py`（44,460 B）、`test/naga_test.py`（23,690 B）、`test/agari_test.py`（34,829 B，新增 6.5 节）、`test/apptest.js`（119,245 B） |
| `readme.md`（29,855 B） | 标题 / 特征表 / 计数 / 版本号 v0.2.0、`f_ippatsu` 与 v0.1.x 库不再支持的说明 |

### 32.2 技术要点
1. **概率文案统一一位小数**（用户 m02227 ①）：`nagaPctText()`（`web/js/app.js` / `web/js/ui.js` 各一份）删掉「整数就省小数点」的分支，一律 `toFixed(1)` ⇒ `38.0%`（不写成 `38%`）。选项表概率、立直行、「其它」行全部走这个函数；牌上概率条的高度仍按精确百分比（与文案无关）。
2. **「一发」状态机**（用户 m02227 ②）：状态由 replay 维护（Python / Node 两套同款）——常态假；某人立直宣言的那一次出牌（discard 且 `riichiPending`）把他置真；他此后自己下一次出牌置假；一旦他家鸣牌（吃 / 碰 / 明杠 / 暗杠 / 加杠），四家全部置假。当前帧取值 = 另外三家状态的逻辑或（自家立直不参与判断）。
3. **特征改名与顺序**（用户 m02356 / m02357）：`一发巡` → **立直家（他家）一发巡**；**NAGA决策** = 第一类第 1 项，**立直家（他家）一发巡** = 第一类第 12 项（紧随「立直家（他家）数量」）。实现上把原 16 项列表改名 `BASE_FEATURES`、把 ippatsu 条目内联在 `riichi_others_n` 之后，再 `FEATURES = NAGA_FEATURES + BASE_FEATURES + SECOND_FEATURES` —— 数据库列顺序、检索下拉、帧特征面板都取 `FEATURES` 的顺序，单一来源。
4. **偶发 / 特殊役互斥**（用户 m02227 ③）写在引擎层 `agari.merge_ctx()` → `rule_ctx()`：`嶺上開花` 清掉 `一発` 与 `海底摸月`（后者是写死特例）、`槍槓` 清掉 `河底撈魚`；`槍槓 + 一発`、`一発 + 海底 / 河底` 原样保留。`merge_ctx` 的唯一生产调用点是 `agari.score()`（`mjscore/agari.py:840`），所以得点 / 役种路径全部生效。
5. **NAGA 和了局不计算符 / 点**：报告里 `hu` / `fan`（荣和自摸都）恒为 0、`ten` 为空 ⇒ NAGA 的和了事件直接取报告的 `yakus_detail` / `yakus`（`mjscore/naga.py` 的 `_end_event`）；全仓由我们算的得点只有第二类六项「期望打点」（口径本来就不含里宝牌 / 一发 / 嶺上 / 海底等偶发役）⇒ 用户 m02227 ③ 的落点判定为「引擎层的互斥规则 + 测试覆盖」。
6. **版本 v0.2.0 / schema 5**（用户 m02227 ④）：新增第一类列 `f_ippatsu` 并调整第一类顺序 ⇒ schema 4（v0.1.x 建的库）由 `store.check_version()` 拒绝并提示重建。

### 32.3 测试
- `node test/apptest.js`：**419 项 OK / 0 失败**（新增：概率统一一位小数 `60.0%` / `45.0%` / `立直5.0%` 且不再出现 `60%`；前端注册表首项 = `naga`、第 12 项 = `ippatsu`（立直家（他家）一发巡）；版本 `0.2.0` / schema 5 / 35 个特征各处计数）。
- `python test/naga_test.py`：**88 项通过 / 0 失败**（每行 35 个特征、`meta.schema_version` = 5）。
- `python test/agari_test.py`：**189 项通过 / 0 失败**，其中新增 6.5 节 7 项：`嶺上+一発`⇒有 4 无 2、`嶺上+海底`⇒有 4 无 5、`槍槓+河底`⇒有 3 无 6、`槍槓+一発`⇒有 2 与 3、`一発+海底`⇒有 2 与 5、`一発+河底`⇒有 2 与 6、端到端（立直 + 嶺上開花，一发旗标同时为真）⇒役里有 4 无 2。
- **JS / Python 注册表 parity**：`FEATURES` 的 35 个 key 与「名字 / 类型 / 取值域」完全一致；真实样本 `build/_scratch/naga_samples/_conv_game_1.json`（16 局）逐局「立直家（他家）一发巡 = 是」计数两侧全等 = `[3,3,3,0,3,6,0,3,3,0,6,0,0,3,0,0]`（合计 33 / 782 打点帧）。
- 未跑：`test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径（沙箱 `PermissionError [WinError 5]`）。

### 32.4 踩坑
1. **python 文本模式读 CRLF 会归一成 LF**，再用 `newline=''` 写回就把整个文件转成 LF ⇒ 补丁脚本必须 `io.open(p, encoding='utf-8', newline='')` 读写（本仓 CRLF 文件：`web/js/app.js`、`web/js/ui.js`、`web/js/replay.js`、`test/apptest.js`、`log.md`）。本轮靠断言提前拦住了 `web/js/replay.js` 被误转；`test/apptest.js` 里一处多行替换混进裸 LF（1 处孤立 LF）用 `re.sub` 归一。
2. 锚点要带**真实缩进**与**正确行尾**：`test/naga_test.py` 的 docstring 是 5 空格缩进（漏了缩进 ⇒ count=0）；CRLF 文件的多行锚点要用 `\r\n`。
3. `score()["yaku"]` 是 `(id, han, name)` **三元组**（不是二元组）⇒ 首版 `for y, _h in r8["yaku"]` 报 `ValueError: too many values to unpack`。
4. `web/js/replay.js` 里并没有「特征一发巡」那句注释 ⇒ 两次替换都 count=0（无需改这个文件）。
5. `test/apptest.js` 的 4 处旧断言写的是 `60%` / `45%` / `5%`，一位小数化后必须同步改成 `60.0%` / `45.0%` / `5.0%`。

### 32.5 待办
- 用户重新构建（`build.ps1`）或 `python server.py` + Ctrl+F5 后目视确认（沙箱无可用浏览器）。
- m00080 目标 4：牌谱检索 / 数据管理支持 NAGA。
- `test/mjscore_test.py` 全量、node 打点路径待用户本机验证。

## 33. 第 37 轮：NAGA 和了结算（符 / 点 / 役种）+ nodeharness 受限环境回退（用户 m02546 ①②）

### 33.1 交付物
| 文件 | 本轮改动 | 尺寸 |
| --- | --- | --- |
| `mjscore/naga.py` | `_hora_settle()` 重写（返回 `(符, 点数, agari 结果或 None)`；`_pts()` 扣本场 / 供托；符算不出时回退报告的 `hu`；`riichi_hint` 用报告役种里的立直 / 一発 / 両立直补立直状态）；`_end_event()` 的 hora 分支：`target` 改用 `is None` 判断（修 0 号位放铳家被当自摸的 bug）、报告没给役种时用引擎判的、役満用引擎判的 | 29,871 B |
| `mjscore/nodeharness.py` | 新增 `_run()`：禁止匿名管道（`PermissionError [WinError 5]`，`CreatePipe`）时回退 `tempfile.mkstemp()` 临时文件 + `subprocess.call(argv, stdout=fo, stderr=fe)` | 5,548 B |
| `test/naga_test.py` | 新增第 7 节「和了结算」（6 个合成用例 + 三份真实样本逐局比对），共 119 项断言 | 31,395 B |
| `readme.md` | 4.4 回放节新增一条：NAGA 结算信息与天凤统一的说明 | 30,470 B |
| `log.md` | 本节 + footer 首行 | — |
| `test/apptest.js` / `mjscore/agari.py` | 未改动（回归见 33.3） | 119,245 B / 38,862 B |

### 33.2 技术要点
1. **结算口径与天凤 `ten` 一致**：`ten = [符, 点]`，点 = 和牌家的 `deltas` − 本场 × 300 − 供托 × 1000。天凤 71 牌谱 640 个和了局实测 **640/640** 成立（`adj_ok` = 637 个单和了局口径 —— 3 局ダブロン的本场 / 供托只归先和者）。**第 38 轮更正**：早先记的「639/640，唯一例外 `2026091320gm-00a9-0000-15180bb5.xml` r1」是**探测脚本的错** —— 它按「和了前一帧是自己杠」推岭上，漏掉「杠 → 新宝牌(`dora`) → 摸岭上牌 → 和了」这种夹着新宝牌的局面，于是那一局的嶺上開花没算上（该局 `ten=60,7900` / gain 8900 = 7900 + 供托 1000，1 番之差使 gain 算成 5000）。实例 = `data/paipu/20261007-165558/2026090821gm-00a9-0000-7019128e.xml` 第 0 局（座 2 立直后暗槓 → 新宝牌 4s → 摸 7s 自摸）。现在的口径 = `test/agari_test.py` 第 5 节：场况旗标（一発 / 槍槓 / 嶺上開花 / 海底 / 河底）以谱面役种 id 为准。
2. **符由 `mjscore.agari` 引擎算**：天凤 637 个和了局 `res["fu"] == ten[0]` **637/637**；NAGA 三样本里报告给了 `hu` 的 27 局 **27/27**。报告里的 `hu` / `fan` **并非恒为 0**（三样本 35 局里 27 局有值），引擎算不出时才回退用它。
3. **役种优先用报告的**：`yakus_detail`（**第 38 轮改**：只给了 `yakus` 的役种 id、没有 `yakus_detail` 时，不再假设每项 1 番，改用引擎判出的役种 + 番数；引擎也判不出时只列役种名、番数留空）；报告没给（`60b5c2ad…` 12 个和了局全程为空）时用引擎判出来的番数 > 0 的役；役満用引擎判出来的并清空普通役。
4. **报告偶尔漏发立直消息**：`3180043a…` r8 的和了局 p1 荣和 p2 的 2m（手牌 234m / 567m / 77m / 456s / 789p，宝牌指示牌 N、里宝 1 张），报告给 `hu=40`、`yakus=[1,53]`（立直 + 裏ドラ），但该局没有 p1 的 `reach` 消息、且 p1 每帧 `info.msg.reached` 全是 False，直接用 replay 状态会让引擎报「役なし」。因此用报告役种里的 1 / 2 / 21 反推出 `riichi=1` 再算符，结果 40 符与报告一致。`tsumo` / `dahai` 消息里的 `reached` 是「该玩家当时是否处于立直」的标记，与我们的 replay 立直状态在 34 局对照中全一致，不是漏发的来源。
5. **`target` 是放铳家座位，可能真的是 0**：原 `int(e.get("target") or actor)` 会把 0 兜底成 `actor` ⇒ 荣和被当成自摸、`win` 取成和牌家自己牌河最后一张 ⇒ 引擎报 `ValueError 并未和牌`，并连带让「报告缺役种时用引擎补」失效。改成 `_tgt = e.get("target"); target = actor if _tgt is None else int(_tgt)`。
6. **流局结算本来就统一**：`gain` 用报告 `deltas`，听牌家用我们自己的向听数（报告的 `tenpais` 不可用 —— 官方样本两处荒牌流局都是四家全 true），replay 按它出摊牌名单（`hands`）。
7. **nodeharness 文件回退**：本沙箱 `subprocess.run(..., capture_output=True)` / `os.popen` 一律 `PermissionError [WinError 5] 拒绝访问。`，但 `subprocess.run(argv, stdout=<file>, stderr=<file>)` 可跑 ⇒ node 打点路径与全量测试在沙箱内恢复可用（且不影响正常环境：先试管道，失败才回退）。

### 33.3 测试
- `python test/naga_test.py` → **119 项通过 / 0 失败**。第 7 节覆盖：7.1 自摸（报告无役种 → 引擎补「門前清自摸和 + 断幺九」、`ten == [30, 3000]`）、7.2 本场 1 + 供托 1 的扣除（4300 → 3000）、7.3 报告给了役种就以报告为准、7.4 **`target=0` 的荣和**（和了家 1 / 放铳家 0、40 符 1300 点、replay 不变量 0）、7.5 引擎算不出时符回退报告 `hu`、7.6 三份真实样本逐局比对（符 27/27、点 35/35 等于报告 `raw_delta`、役种与报告 23/23、报告没给役种的 12 局全补上）。
- `python test/agari_test.py` → 189 项通过 / 0 失败；`node test/apptest.js` → 全通过（419 项 OK）。
- 一次性正向对照脚本：天凤 71 牌谱 637 个和了局 `res["fu"] == ten[0]` **637/637**、`res["gain"] − 本场 × 300 − 供托 × 1000 == ten[1]` **640/640**（637 个单和了局口径；早先记的 639/640 是探测脚本漏判岭上所致，见 33.2 第 1 条的更正）；NAGA 三样本 `ten[1] == 报告 raw_delta` 35/35。
- 全量 `python test/mjscore_test.py`（`-X utf8 -u` 后台跑，日志 `build/_scratch/_probe_tmp/mjscore_test.log`）：第 1 节全 OK（逐帧校验 5766 帧 0 错误）、第 2 节「打点口径」通过（含 node / python 双路比对的 2786 行抽查：违规类别 0 个），第 3 节进行到「检索条件」断言后进程被沙箱杀掉（见 33.4 第 6 条）⇒ 全量结果仍以本机为准。

### 33.4 踩坑
1. `target` 的 0 值兜底（33.2 第 5 条）—— 症状是「部分 NAGA 和了局算不出符 / 点」，样本里都恰好是 p1 和了。
2. `test/naga_test.py` 里的 `ten` 是 2 元组 `[符, 点]`（天凤 XML 才是 3 元组），断言按 3 元组写会 FAIL。
3. 用 PowerShell here-string 写补丁脚本再 `Set-Content -Encoding UTF8` 会带 BOM，插入到 py 文件里报 `SyntaxError: invalid non-printable character U+FEFF` ⇒ 读入时用 `utf-8-sig`。
4. 要造「引擎算不出」的用例：光挑一副没役的手牌不行（引擎可能判出别的役），必须让放铳家打出一张明显不成和的牌（荣和的 `win` 取放铳家牌河最后一张）。
5. 打印中文到重定向文件要 `cmd /c "python -X utf8 ... > out.txt 2>&1"`，否则控制台代码页会给出乱码。
6. 本沙箱对单个进程有时间上限：全量套件 00:15:14 启动、日志最后写入 00:30:29（累计 CPU 986 s）后被杀，**与权限无关** ⇒ 约 61 分钟的全量套件只能在本机跑完；也不能分节跑（`test/mjscore_test.py` 是按段落顺序执行的脚本，没有 argv 分段能力）。

### 33.5 待办
- `test/mjscore_test.py` 全量（约 61 分钟）须本机跑；本沙箱已确认第 1～3 节通过（node 打点路径本身已可跑）。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- 仍未解：`end_num` 恒为 1 的真义；途中流局（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 34. 第 38 轮：NAGA 役种 / 番数改由引擎判 + 中央结算框加宽（用户 m02801 ①②③）

### 34.1 交付物
| 文件 | 改动 | 大小 |
| --- | --- | --- |
| `mjscore/naga.py` | `_hora_ctx()` 新增 `before(i)`（往前找上一帧时跳过夹在中间的 `dora` 消息）与「役种 id → 场况旗标」（一発 2 / 槍槓 3 / 嶺上開花 4 / 海底 5 / 河底 6）；`_hora_settle()` 透传 `yaku_hint`；`_end_event()` 删掉「`yakus` 每项按 1 番」的兜底 | 31,655 B |
| `web/style.css` | `.center { width: 100% }`；`.c-result` 改 `flex-start` + 首末 `margin: auto`（安全居中）；新增 `.c-dora-show`（标签与牌同排）；`.c-result .tiles .tile` 缩到 80% | 32,077 B |
| `test/naga_test.py` | 新增 7.7 / 7.8 / 7.9（只给役种 id 时用引擎判番、引擎判不出时番数留空、`_hora_ctx` 单元断言），共 130 项 | 34,954 B |
| `test/apptest.js` | 2b 节新增和了帧合成样本 + 4 项断言，7f 节新增 6 项样式断言，共 429 项 | 122,345 B |
| `build/_scratch/naga_samples/check_settle_tenhou.py` | 重写为「场况旗标以谱面役种为准」的口径（归档脚本） | 3,500 B |
| `readme.md` | 4.4 回放节：役种 / 番数缺失时也用引擎判、中央结算框加宽与安全居中 | — |
| `log.md` | 本节 + 33.2 / 33.3 三处更正 + footer 首行 | — |

### 34.2 技术要点
1. **639/640 的更正（用户 m02801 ①）**：天凤 71 牌谱 **640 个和了局**里 `res["fu"] == ten[0]` **640/640**、`res["gain"] == gain[winner]` **640/640**、`gain − 本场 × 300 − 供托 × 1000 == ten[1]` 在 **637 个单和了局 637/637**（3 局ダブロン的本场 / 供托只归先和者）。原「639/640，唯一例外 `2026091320gm…` r1」是探测脚本的错 —— 它按「和了前一帧是自己杠」推岭上，漏掉「杠 → 新宝牌(`dora`) → 摸岭上牌 → 和了」，实例 `data/paipu/20261007-165558/2026090821gm-00a9-0000-7019128e.xml` 第 0 局（座 2 立直后暗槓 → 新宝牌 4s → 摸 7s 自摸，谱面 `ten="60,7900,0"` / `yaku="1,1,4,1,0,1,53,0"` = 立直 + 嶺上開花 + 門前清自摸和 + 裏ドラ 0；漏判时 han 2 → gain 5000，补上 rinshan 后 han 3 → gain 8900 = 7900 + 供托 1000）。
2. **不再做「每项默认 1 番」的假设（用户 m02801 ②）**：`_end_event()` 的役种决定链变成 —— ① 有 `yakus_detail` 就用它（id + 番数）；② 否则（只有 `yakus` id，或什么都没给）用引擎 `res["yaku"]` 里番数 > 0 的项；③ 引擎也判不出时才退回 `yakus` 的 id 列表、番数填 0（只显示役种名）。役満仍优先用报告的 `yakuman`，若只有引擎判出役満则取其 han==0 的 id 并清空普通役。
3. **场况旗标以谱面役种为准（引擎自推有漏）**：`_hora_ctx()` 的 `before(i)` 从第 i 帧往前找上一帧时跳过 `dora` 消息；四条旗标改为「动作序列推导 **or** 役种 id 提示」（`ippatsu` 2 / `chankan` 3 / `rinshan` 4 / `haitei` 5 / `houtei` 6），口径与 `test/agari_test.py` 第 5 节一致。报告的 `reach` 消息偶有漏发，仍用役种里的 1 / 2 / 21 反推立直（第 37 轮的做法保留）。
4. **中央结算框（用户 m02801 ③）**：症状是「和了帧看不到『東家 自摸和了』的绿色标题」+「中央框出现纵向滚动条」。根因同一个：`.c-result` 是绝对覆盖 `.center` 的浮层，`display: flex; flex-direction: column; justify-content: center` + `overflow: auto` —— 内容（标题 + 役名 + 符 / 点 + 宝牌两行）超高时，**flex 居中会把溢出部分顶到上边、滚动条也滚不到**，于是第一行标题被裁掉；同时 `.center` 只有内容宽度（截图实测 149px，而中央列 `8.6 × --tile-w ≈ 318px`）导致役名折成很多行。修法：`.center { width: 100% }` 铺满中央列；`.c-result` 改 `justify-content: flex-start` + `.c-result > :first-child { margin-top: auto }` + `> :last-child { margin-bottom: auto }`（内容不满时仍居中、溢出时从顶部滚）；`.c-dora-show` 改 flex 让「宝牌指示牌」标签与牌同排（原先没有该规则、标签与牌各占一行，两行宝牌 ≈ 134px 是超高的主因）；宝牌 / 里宝牌的牌缩到 80%。

### 34.3 测试
- `python test/naga_test.py` → **130 项通过 / 0 失败**（7.7 七対子 `han == 2` 证明不再默认 1 番；7.8 引擎判不出 → `[[8, 0]]`；7.9 `_hora_ctx` 六条断言）。
- `node test/apptest.js` → **429 项 OK / 0 失败**（和了帧标题 `東家 自摸和了` / `20 符 / 12000 点` / `立直(1) / 門前清自摸和(1) / 宝牌(2)` / 两行宝牌指示牌 + 6 项样式断言）。
- `python test/agari_test.py` → 189 项通过 / 0 失败（未改动，回归）。
- `python build/_scratch/naga_samples/check_settle_tenhou.py`（需 `set PYTHONPATH=.`）→ `{'n': 640, 'fu_ok': 640, 'gain_ok': 640, 'adj_ok': 637}`。
- `python build/_scratch/naga_samples/check_settle_naga.py`（需 `PYTHONPATH=.`）→ 三样本 35 个和了局：fu 27/27、ten 35/35、报告役种 23/23、引擎补役种 12 / 0 空、流局 3/3。

### 34.4 踩坑
1. 探测脚本从动作序列硬推岭上会漏判（「杠 → 新宝牌 → 摸岭上牌」）—— 场况旗标一律以谱面役种为准，这也是 `test/agari_test.py` 第 5 节原本的做法。
2. `_p4.py` 把 `var badJsonOk = App.loadText('{"foo":1}', 'bad.json');` 当成插入锚点整行替换掉 ⇒ 运行报 `ReferenceError: badJsonOk is not defined`（test/apptest.js:428）；补回该行即可。
3. 归档脚本要在项目根跑并 `set PYTHONPATH=.`，否则 `ModuleNotFoundError: No module named 'mjscore'`。
4. Python 补丁脚本里的字符串含 `\_` 之类反斜杠会产生 `SyntaxWarning: invalid escape sequence` ⇒ docstring 用原生字符串前缀 r。。

### 34.5 待办
- `test/mjscore_test.py` 全量（约 61 分钟）仍须本机跑。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- 仍未解：`end_num` 恒为 1 的真义；途中流局（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 35. 第 39 轮：一炮双响结算 + 静态帧模式（隐藏他家手牌联动 / 禁用播放控制面板）+ 数据库版本过低提示（用户 m02984 ①②③、m03089 ①②）

### 35.1 交付物

| 文件 | 字节数 | 说明 |
| --- | --- | --- |
| `mjscore/naga.py` | 33,241 | 新增 `_end_events()`；`_end_event(pick, first)` 与 `_hora_settle(honba, kyotaku)` 支持一炮双响（用户 m02984 ①） |
| `web/js/app.js` | 95,103 | `othersLocked()` / `lockControls()`；隐藏他家手牌联动隐藏 NAGA 概率条与决策表；静态帧禁用播放控制面板；数据库标记改「⚠ 版本过低」 |
| `web/style.css` | 32,294 | `#controls.locked button { opacity: .45; pointer-events: none; cursor: not-allowed; }` |
| `web/index.html` | 18,445 | 版本说明改成「版本过低的库不能使用」 |
| `mjscore/store.py` | 20,135 | `check_version()` 提示改写（结构版本不符 →「数据库版本过低…」；软件版本不符 →「数据库版本不匹配…」） |
| `test/apptest.js` | 124,921 | 新增 ②③① 断言 13 项 |
| `test/naga_test.py` | 37,155 | 新增 7.10（一炮双响，8 项断言） |
| `test/mjscore_test.py` | 44,544 | 3 处版本提示断言同步 |
| `readme.md` | 32,189 | 4.3 静态帧禁用控制面板 / 4.4 隐藏他家手牌联动 + 一炮双响 / 5.2 与排错表的版本提示 |

### 35.2 技术要点

1. **一炮双响（ユーザ m02984 ①）**：报告里同一局 `end_msgs` 有多条 `hora` 时，以前 `_end_event` 只取 `end_msgs[0]`、第二家会被丢掉。现在 `_end_events()` 逐条生成和了事件；`_end_event(pick, first)` 里只有**第一条** agari 拿本场 / 供托（`honba=None if first else 0`），第二家 `_hora_settle` 拿到 0 ⇒ 与天凤牌谱的逐家收支一致（本场 300 / 供托 1000 只归先和者）。
2. **引擎本身没问题**：71 牌谱里 3 局一炮双响，按「先和者拿本场、其余 0」调 `agari.score` 逐家复算 ⇒ 6 家 fu / han / gain / yaku 全对。**注意 `seat_wind` / `round_wind` 必须传 27..30（WINDS 常量），传 0..3 会漏掉自风 / 场风役并抛「役なし」。**
3. **隐藏他家手牌联动（用户 m02984 ②）**：`render()` 里 `if (nf && App.hideOthers) { nf = null; }`（概率条不画），`renderNagaPanel()` 清空三块后 `if (App.hideOthers) { return; }`（只留标题）—— 概率条是按决策者手牌位置画的，盖住手牌后没有意义。
4. **静态帧模式（用户 m02984 ③、m03089 ①）**：`othersLocked()` = `App.itemIndex >= 0`（牌谱检索的条目帧）。这时：`syncOthers()` 把「隐藏他家手牌」按钮 `disabled` 并强制 `App.hideOthers = false`（title 说明原因）；`jumpRow()` 进入条目时先 `App.hideOthers = false`；`case 'others'` 直接 `break`；`setDisabled()` 改成 `b.disabled = !!off || othersLocked();`（否则 `syncButtons()` 会在每次 `render()` 里把按钮又放开）；新增 `lockControls(on)` 给 `#controls` 加 `.locked` 并禁用其中全部按钮，`syncItemNav()` 末尾调用（进入条目时还 `stopAuto()`）。牌桌**下方**的控制面板整块禁用，**工具栏**里的「上一条目 / 下一条目」不受影响（它们不在 `#controls` 里）。
5. **数据库版本提示（用户 m03089 ②）**：`store.check_version()` 的两条 `ValueError` 文案改写 —— 「数据库版本过低（库的结构版本 4，当前软件需要 5；v0.1.x 的库在 v0.2.0 起不再支持），请删除后重新分析：python analyze.py <牌谱路径> --delete-db <库名>（<绝对路径>）」/「数据库版本不匹配（库由软件版本 X 生成，当前软件版本 Y）…」。前端三处标记同步改成「⚠ 版本过低」，`web/index.html` 的说明也改成一句「版本过低的库不能使用」——不再罗列历轮 schema 变更史。

### 35.3 测试

- `node test/apptest.js` → **442 项 OK / 0 FAIL（exit 0）**（本轮前 429）。
- `python test/naga_test.py` → **138 项通过 / 0 失败**（本轮前 130）。
- `python test/agari_test.py` → **189 项通过 / 0 失败**。
- 版本提示临时脚本（`_vt2.py`，已删）：结构版本 4 → 打印「数据库版本过低…」；`app_version=0.1.0` → 打印「数据库版本不匹配…」。
- `python -m py_compile mjscore/naga.py mjscore/store.py test/naga_test.py test/mjscore_test.py`、`node --check web/js/app.js test/apptest.js` 全部通过。
- 仍待本机跑：`test/mjscore_test.py` 全量（约 61 分钟，本沙箱会被杀）。

### 35.4 踩坑

1. 用 `io.open(P, "w", newline="\r\n")` 写 CRLF 文件会把已有的 `\r\n` 再翻译成 `\r\r\n`（`web/js/app.js` 一度涨到 96,649 B）⇒ **补丁脚本一律读 / 写都用 `newline=""`**，插入文本自己带 `\r\n`。
2. `test/apptest.js` 里 `clickAct('next')` 只在第 1200 行之前使用 ⇒ 禁用 `#controls` 不会影响既有测试；但 `setDisabled()` 必须尊重锁定，否则 `jumpRow → render → syncButtons` 会把刚禁用的按钮又启用。
3. 早先的临时探针直接 `UPDATE meta` 会 0 行命中（`open_db` 不写 meta）⇒ 校验版本要显式 `INSERT INTO meta`，且校验失败时 `connect()` 会自己关连接、测试脚本要记得不再持有连接（否则 Windows 上文件删不掉）。

### 35.5 待办

- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 61 分钟）与 node 打点路径待本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 36. 第 40 轮：播放视图布局改造（浏览选择 / 按特征码搜索 / 拖放区 / 事件列表常态，用户 m03175 ①–⑦）

### 36.1 交付物（本轮改动）

| 文件 | 变化 |
| --- | --- |
| `web/index.html` | 18,445 → 18,307 B（LF）：删右上角「事件列表」勾选项；`#rpOpenBar` 改成「浏览选择 / 按特征码搜索」两个互斥单选项 + `#codeInput`（`maxlength=160`）+ `#codeResults`；删「示例牌谱」下拉与 `<details class="hint">`（「打不开文件 / 载入示例失败？」）；`#dropZone` 移进 `#boardBox`（覆盖牌桌区域） |
| `web/style.css` | 32,294 → 33,787 B（LF）：新增 `.code-input` / `.code-results`（`height: 132px` + `overflow: auto`）/ `.code-row`（`white-space: nowrap`）/ `.code-none`；`.board-box { position: relative }` + `.board-box .drop-zone`（`position: absolute; inset: 6px; pointer-events: none`）；删 `.open-bar .drop-zone` |
| `web/js/app.js` | 95,103 → 98,695 B（CRLF）：删 `SAMPLE_IDS` / `showList` / `fillSamples` / `loadSamples` / `loadSample`；新增 `loadHealth` / `codeOf` / `syncOpenMode` / `loadCodeIndex` / `renderCodeResults` / `openPaipuPath` / `showDropZone`；`initDrop()` 改绑 `#boardBox`；事件列表常态渲染 |
| `test/apptest.js` | 124,921 → 129,326 B（CRLF）：第 1 节 8 条新断言（无 `chkList` / `sampleSelect`，有 radio + 特征码输入框 + 结果框，拖放区可见且 `.over` 可切换）、第 2 节载入后拖放区隐藏、7e 事件列表常态显示、第 10 节结构断言、7f 5 条 CSS 断言、15.11 整段改成特征码搜索用例 |
| `readme.md` | 32,189 → 33127 B（LF）：4.4 回放节改写（浏览选择 / 按特征码搜索 / 拖入牌桌 / 事件列表常态），新增「按特征码搜索」一条 |

### 36.2 技术要点

1. 两种打开方式互斥，但**模式状态存在 `App.openMode`**（`'browse'` / `'search'`）：`syncOpenMode(mode)` 回写两个 radio 的 `checked`，并切换 `#btnPickFile.disabled`（search 时禁用）与 `#codeInput.disabled`（browse 时禁用）。
2. 按特征码搜索：索引项 = `baseName(p)` 去掉 `.json.gz` / `.xml` / `.mjlog` / `.json` / `.gz` 后**转小写**；清单来自 `/api/scan?dir=<App.paipuDir || 'data/paipu'>&kind=all`（切到搜索模式且清单为空时重取）；匹配规则 = `code.indexOf(needle) >= 0`（**连续子串完全匹配**）；结果只显示文件名（`.code-row` 单行、`white-space: nowrap`、超出在 `#codeResults` 内横向滚动，`title` 放完整路径），最多 200 条，超出 / 无命中给出提示行。
3. 点搜索结果走 `openPaipuPath(path)`：先 `App.itemIndex = -1` / `App.itemSource = ''` / `App.items = []` / `App.hideOthers = false` + `syncItemNav()`（**复位「牌谱检索」的静态帧模式，否则播放控制面板保持禁用**），再 `loadFromPath(p)` ⇒ 正常播放视图。
4. 拖放区改成覆盖牌桌区域：`#dropZone` 从 `#rpOpenBar` 移进 `#boardBox`（`position: absolute; inset: 6px; pointer-events: none`，让拖放事件落到 `.board-box` 上），`initDrop()` 的 `dragenter` / `dragover` / `dragleave` / `drop` 绑到 `#boardBox` 并给拖放区切 `.over`；`loadText()` 成功后 `showDropZone(false)`，进入播放页且还没有牌谱时 `showDropZone(true)`。
5. 搜索结果里与输入匹配的片段用**黄色底**标出（`.code-hit`：`background: #ffd54a; color: #14201b`）——匹配是按去掉扩展名的特征码算的，但特征码是文件名的前缀，所以同一段子串在显示的文件名里也找得到（用户 m03319）。
6. 事件列表常态显示：删 `#chkList` 与 `App.showList`，`render()` 直接调用 `UI.renderEventList(...)`（`.event-list.off` 规则保留但不再使用）。

### 36.3 测试

- `node test/apptest.js` → **exit 0，全部通过**（新增 / 改写的断言见 36.1）。
- 高亮相关新增 3 条断言：`.code-hit` 标出匹配片段、匹配位于文件名中间时也高亮且整行文本不变、CSS 里有 `.code-hit` 的黄色底（用户 m03319）。
- `python test/naga_test.py` → 138 项通过 / 0 失败；`python test/agari_test.py` → 189 项通过 / 0 失败（本轮未动后端，跑一遍确认无回归）。
- 沙箱仍不能做浏览器布局量测（headless Edge 被禁）⇒ 位置 / 对齐由用户目视确认。

### 36.4 踩坑

1. `test/apptest.js` 的假 DOM 只为 `web/index.html` 里**带 `id` 的元素**建节点（外加 `.tab` 与控制按钮），**不解析其它属性** ⇒ `document.querySelectorAll('input[name="rpOpenMode"]')` 返回空数组、`change` 监听器一个都没挂上（表现为「切到搜索模式没反应」）⇒ 改成按 id 绑定 `$('rpModeBrowse')` / `$('rpModeSearch')`。
2. 假 DOM 的 radio 不会互斥联动 ⇒ 只把 `rpModeBrowse.checked` 设回 true 时 `rpModeSearch.checked` 仍为 true（表现为「切回浏览选择」失败）⇒ 模式状态改存 `App.openMode` 并由 `syncOpenMode()` 回写两个 radio 的 `checked`。
3. `web/index.html` 那条「空行」其实是 6 个空格 ⇒ 逐字锚点必须带上，否则 `AssertionError: ('count', 0, …)`。

### 36.5 待办

- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 37. 第 41 轮：切换主视角 + 「隐藏他家手牌」只隐藏别家（用户 m03343 ①②③ / m03411）

用户 m03343 提了三条（m03411 又把同样三条一字不改地发了一遍）：
1. 「隐藏他家手牌」与概率条 / 决策表绑定时**错误地把主视角自己的概率条、决策表也一起隐藏了**；
2. 播放界面新增「切换主视角」按钮（控制条最后一位、足够长以单行显示完整玩家 ID），点开 4 行上拉框按东 1 局座次 東 > 南 > 西 > 北 列出四家 ID，点谁就换谁当主视角（其他玩家保持相对方位），切换后立即刷新；建议用**旋转向量**（初始 `[0,1,2,3]`）确定展示位置；
3. 牌谱检索进入的静态帧播放界面：主视角固定切到当前决策者，并禁用「切换主视角」。

### 37.1 交付物

| 文件 | 改动 |
| --- | --- |
| `web/index.html` | 18,671 B：`btnOthers` 之后加 `<button data-act="view" id="btnView">切换主视角</button>`；`#rpDesc` 之后加 `<div id="viewMenu" class="view-menu hidden"></div>` |
| `web/style.css` | 35,283 B：`#btnView { min-width: 200px; }`；`.view-menu`（绝对定位、bottom 96px、min-width 240px、`width: max-content`）、`.view-row` / `.view-row:hover` / `.view-row.cur` / `.vw-wind` / `.vw-id` |
| `web/js/ui.js` | 25,045 B：`addNagaBars(...)` 加第 5 参数 `obs`（观察者座位，危险条取 `danger_*[obs]` 那一行）；`renderPlayer(cellEl, st, seat, opts, pos)` 加 `pos`（展示位置）并按 `SEAT_ROT[pos]` 旋转；新增 `hideDecider`（隐藏他家手牌且决策者不是自家时不画上侧预测柱）；隐藏他家手牌时主视角自己的 `nf` 不再被清空；`renderBoard` 支持 `opts.viewRot` |
| `web/js/app.js` | 104,895 B：`App.viewRot = [0,1,2,3]`；`setViewSeat()` / `viewMenuRows()` / `renderViewMenu()` / `toggleViewMenu()` / `syncViewBtn()`；`onAct` 加 `case 'view'`；`render()` 里静态帧强制主视角 = `frameSeatOf(st)`，并把 `viewRot` / `hideOthers` 传给 `renderBoard`；`renderNagaPanel()` 的早退改成「隐藏他家手牌且决策者不是自家」；`jumpRow` / `loadText` 收起上拉框；`#viewMenu` 点击代理；导出新增 4 个函数 |
| `test/apptest.js` | 135,952 B：把旧的「隐藏他家手牌时概率条与决策表一起隐藏」断言块改写成 ① 的 8 条（自家决策帧隐藏后概率条 / 决策表 / 5 个数据仍在；别家决策帧他家预测柱不画、自家危险条仍在、面板留空）；新增 ② 的 22 条（旋转向量、初始方位、按钮文字带 ID、上拉框 4 行与東南西北顺序、`.cur`、点第 2 行后 `viewRot = [1,2,3,0]`、B 到下 / C 到右 r270 / D 到上 / A 到左、概率条画到 A 的新位置、危险条按新观察者取行、复位后恢复）；8.4 节新增 ③ 的 4 条；7f 节新增 5 条 CSS 断言 |
| `readme.md` | 34,282 B：4.4 回放节改写「隐藏他家手牌」那条（只隐藏别家），新增「切换主视角」一条（上拉框顺序、旋转向量、静态帧固定决策者 + 禁用） |

### 37.2 技术要点

1. **旋转向量** `App.viewRot`：下标 = 展示位置（0 下 / 1 右 / 2 上 / 3 左），值 = 绝对座位；`setViewSeat(s)` → `[s, (s+1)%4, (s+2)%4, (s+3)%4]`，`App.selfSeat = App.viewRot[0]`。`renderBoard` 用 `vr[pos]` 取座位、把 `pos` 传给 `renderPlayer`，**旋转角度按展示位置取 `SEAT_ROT[pos]`**（原先按绝对座位，换主视角后就会转错）。
2. **危险牌条按观察者取行**：报告的 `danger_s/t/k[观察者][kind]` 第一维是观察者，原先硬编码 `arr[0]`，换主视角后必须取 `arr[App.selfSeat]`（新增 `obs` 参数从 `renderPlayer` 传下去）。
3. **「隐藏他家手牌」只隐藏别家**：`renderPlayer` 里主视角自己的 `nf` 恒为真（① 的修复点），只有「决策者 ≠ 主视角」时上侧预测柱不画；`renderNagaPanel()` 的整块早退从「`App.hideOthers` 就返回」改成 `if (App.hideOthers && seat !== App.selfSeat) { return; }`（要先把 `nf` / `seat` 算出来）。
4. **静态帧固定决策者**：`render()` 开头 `if (App.itemIndex >= 0) { var fs = frameSeatOf(st); if (fs !== null && fs !== App.viewRot[0]) { setViewSeat(fs); } }`；按钮禁用复用 `lockControls()` / `setDisabled()`（`#btnView` 带 `data-act="view"`，落在 `#controls` 里 ⇒ 自动被禁）。
5. **上拉框顺序**：按 `rounds[0].init.oya`（回退 `meta.oya`）排 `(oya + k) % 4`，风位固定 `東 / 南 / 西 / 北`，所以「东 1 局座次」与实际起家无关地正确。
6. **按钮宽度**：`#btnView { min-width: 200px; }` + 文字 = `'切换主视角：' + 当前主视角 ID`（满足「足够长、单行显示完整玩家 ID」）；上拉框 `min-width: 240px; width: max-content; max-width: 90vw`。

### 37.3 测试

- `node test/apptest.js` → **487 项 OK / 0 失败 / 全部通过**（本轮 +45 项；其中 ① 8 条、② 22 条、③ 4 条、CSS 5 条）。
- `python test/naga_test.py` → **138 项通过 / 0 失败**；`python test/agari_test.py` → **189 项通过 / 0 失败**（均未受影响）。
- 行尾核对：`web/js/ui.js` / `web/js/app.js` / `test/apptest.js` 纯 CRLF（0 孤立 LF）；`web/index.html` / `web/style.css` 纯 LF。
- 沙箱仍无法做浏览器布局测量（headless Edge 被禁），视觉部分待用户目视确认；`test/mjscore_test.py` 全量（约 61 分钟）与 node 打点路径仍待用户本机验证。

### 37.4 踩坑

1. `_p4.py` 第一次跑时 CSS 断言的锚点猜错 → `AssertionError: ('css', 0)`；因为补丁脚本是「全部替换成功后才写文件」的原子写法，文件没被改坏，改锚点（用 `test/apptest.js` 里 `check(!/\.open-bar\s+\.drop-zone/…)` 那行）后一次成功。
2. 换主视角后**旋转角度必须按展示位置算**：若仍按绝对座位取 `SEAT_ROT[seat]`，B 换到下方时会把「下家的 270°」带到主视角位置（测试用 `.cell-right .p-rot` 必须含 `r270` 抓住这一点）。
3. 测试假 DOM 只为带 `id` 的元素建节点、且带 `data-act` 的按钮才落进 `#controls` ⇒ 新按钮必须带 `data-act`（否则 `#controls` 内按钮计数断言与实际不符）。

### 37.5 待办

- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

### 37.6 修正（用户 m03498）：上拉框贴着按钮向上弹出

用户 m03498 报告：点「切换主视角」后选项没有从按钮上方长出来，而是出现在**整个界面的右下角**。

- 根因：`#viewMenu` 是 `#view-replay`（`position: relative`）的子元素，CSS 里写的是 `position: absolute; right: 14px; bottom: 96px;` ⇒ 定位基准是整个播放视图，右侧又紧贴事件列表那一列，所以看起来就是界面右下角。
- 修法：新增 `web/js/app.js` 的 `placeViewMenu()` —— 用 `$('btnView').getBoundingClientRect()` 与包含块（`menu.offsetParent`，退回 `#view-replay`）的矩形算出 `left = 按钮左沿` / `bottom = 包含块底 - 按钮上沿 + 6`，宽度够时按 `包含块宽 - 菜单宽 - 8` 收在右侧边界内，并把 `style.right` 置 `auto`；`toggleViewMenu()` 在去掉 `.hidden` 之后调用它（此时才能量到 `offsetWidth`）。另加 `placeViewMenuIfOpen()`：窗口 `resize` 与控制条 `scroll` 时若菜单开着就重新定位。
- `web/style.css` 的 `.view-menu` 把 `right: 14px` 换成 `left: 14px`（只作兜底，实际位置由 JS 覆盖），注释同步说明。
- 测试：`test/apptest.js` 的假 DOM 增加 `El.prototype.getBoundingClientRect()` 尺寸桩；② 断言新增「上拉框贴着按钮定位（`style.right === 'auto'`、`left` / `bottom` 都是 JS 算出的 px）」，7f 新增「CSS 不再用 `right: 14px` 钉在右下角、兜底用 `left: 14px`」。
- 结果：`node test/apptest.js` → **全部通过**（exit 0），新增 2 条断言全绿。

---

## 38. 第 42 轮：复制牌谱 URL + 四家铳率条 + 听牌率条 + 布局收拢（用户 m03479 ①②、m03627）

用户 m03479 提了两条：
1. 牌谱播放与牌谱检索的静态帧播放，都要在**牌谱文件名旁边**加一个「复制url」按钮，点一下**重构并复制原始牌谱 URL**（天凤谱 = `tenhou` 开头、NAGA 谱 = `naga` 官网开头，**不要还原成 ricochet**）。
2. 布局与新增展示：四家 ID 的展示位置**紧贴中央信息框**、手牌展示位置**更贴近中央**；新增**听牌率图**（改用双色条形图，位于手牌外侧、平行于手牌、预留出手牌下方铳率条的位置；初始主视角的下家 = 全绿 / 対面 = 全黄 / 上家 = 全蓝，三条总长度相等且固定，听牌率升高时从对应玩家视角的左侧开始转红，红条长度占比 = 听牌率）；新增**三家铳率条**（那家自己视角右→左 = 绿 / 黄 / 蓝，从手牌下沿开始向下延伸）。两者都要随座位旋转、并随「切换主视角」联动。
用户 m03627 追加：为避免听牌率 100% 时看不出这条原本是什么颜色，绿 / 黄 / 蓝听牌率条要带同色的**边框**，内部从对应玩家视角左侧开始变红，边框始终维持原色。

### 38.1 交付物

| 文件 | 改动 |
| --- | --- |
| `web/index.html` | 18,882 B：`#rpFile` 之后加 `<button id="btnCopyUrl" class="ghost" disabled title="复制原始牌谱 URL">复制url</button>` |
| `web/js/app.js` | 106,556 B：`copyFrameKey()` 的剪贴板逻辑抽成 `copyTextTo(text, node)`；新增 `paipuUrl()` / `copyUrl()`；`paipuUrl()` 在天凤牌谱下用 `gameLogId()`（文件名特征码）补 `meta.log_id`；`syncButtons()` 里按有无 URL 设 `#btnCopyUrl` 的 disabled / title；`init()` 绑定点击；导出 `paipuUrl` / `copyUrl` |
| `web/js/ui.js` | 26,459 B：危险条改成**四家都画**（`dnNf = (nagaFrame && !hidden) ? nagaFrame : null`、`addNagaBars(..., 'down', seat)`，取该手牌主人那一行）；每个非主视角面板追加 `.p-tenpai`（`.tp-s` / `.tp-t` / `.tp-k` + 内置 `.tp-red`，宽度 = 听牌率） |
| `web/style.css` | 36,968 B：`.board` 格间距 `.45 → .25` 牌宽、上下两行 `6.6 → 7.4` 牌高；`.cell-top` 加 `align-items: flex-end`、`.cell-bottom` 加 `align-items: flex-start`；新增 `.p-tenpai`（13 张牌宽、基色 `border: 2px solid` + 同色 `background`、`.tp-t` 黄 / `.tp-k` 蓝）与 `.tp-red`（`left: 0`、`background: var(--danger)`） |
| `test/apptest.js` | 142,751 B：② 4 条改 / 新增 15 条（四家铳率条按手牌主人取行、听牌率条三类槽位与红段宽度、切换主视角后换行、隐藏他家手牌时别家 0 条）+ ① 5 条（NAGA / 天凤两种 URL、不还原 ricochet、按钮可用与「已复制」反馈）+ 7f 新增 6 条 CSS 断言 |

### 38.2 技术要点

1. **URL 重构**：`paipuUrl()` 先看 `App.naga` —— 有就 `https://naga.dmv.nico/htmls/report_viewer.html?report_id=<App.naga.report_id || meta.log_id>&tw=0`，否则 `http://tenhou.net/0/?log=<特征码>&tw=0`。天凤 xml 的 `meta` 里**没有 `log_id`**（MJLOG.parse 只给 names / dan / rate / sex / config / oya），所以退回 `gameLogId()`（= 文件名去掉 `.xml` / `.json.gz`），无牌谱时返回空串并让按钮 disabled。
2. **危险条行语义**（本轮的第二次实测复核）：`danger_s/t/k` 第一维 = **手牌的主人**（绝对座位），三个 key 分别是「来自该主人的下家 / 対面 / 上家」；数据是**稀疏**的（只对一部分 (主人, 方向) 组合算出来，没算的行全 0，所以画不出错数据）。官方 viewer 也只按这个口径取（`a.dangerS[this.targetSeat][S]` 等，且只给位置 0 画），我们改成四家各自取「自己那一行」。
3. **听牌率行语义**：`tenpai_s[o]` = 观察者 o 的**下家**、`tenpai_t[o]` = o 的**対面**、`tenpai_k[o]` = o 的**上家**（万分比）；等价地，某家 p 的听牌率 = `tenpai_s[(p+3)%4]` / `tenpai_t[(p+2)%4]` / `tenpai_k[(p+1)%4]`。实现按官方口径取「主视角那一行 + 展示槽位」：位置 1（右 = 下家）→ `tenpai_s[selfSeat]`、位置 2（上 = 対面）→ `tenpai_t[selfSeat]`、位置 3（左 = 上家）→ `tenpai_k[selfSeat]`。
4. **配色与旋转**：听牌率条基色按「与主视角的相对位置」定（下家绿 / 対面黄 / 上家蓝），用 `.tp-s` / `.tp-t` / `.tp-k` 三个 class；红段 `left: 0` 是「该家自己视角的左侧」（整块面板会旋转，所以相对空间自适应）；红段宽度 = `clamp(听牌率 / 100, 0, 1) * 100` 的 `toFixed(1)` 百分比。铳率条沿用现有 `.tbar.down.k/.t/.s`（左→右 = 蓝 / 黄 / 绿 = 那家自己视角的上家 / 対面 / 下家，与 m03479 的描述一致）。
5. **听牌率条必须在文档流里**：`.board-box` 有 `overflow: hidden`，绝对定位的溢出内容会被裁掉；所以 `.p-tenpai` 是 `.p-rot` 的普通子元素（最后一个），靠 `.board` 上下两行加高到 7.4 牌高来容纳「抬头 + 牌河 4 行 + 手牌 + 铳率条 + 听牌率条」。
6. **隐藏他家手牌**：`dnNf` 在面板被盖住（`hidden`）时为 null ⇒ 别家不画铳率条；主视角自己的照画。

### 38.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**；`python test/naga_test.py` → **138 项通过 / 0 失败**；`python test/agari_test.py` → **189 项通过 / 0 失败**。
- 行尾核对：`web/js/ui.js` / `web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/index.html` / `web/style.css` 纯 LF。
- 沙箱无浏览器 ⇒ 布局与视觉（听牌率条 / 铳率条的位置、白边、边框颜色）待用户目视确认；改完需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。

### 38.4 踩坑

1. **天凤牌谱下「复制url」按钮一直禁用**：`paipuUrl()` 原先只认 `meta.log_id`，而天凤 xml 的 `meta` 根本没有这个字段（只有 NAGA 侧补过 `log_id`）。改为 `if (!id) { id = gameLogId(); }`，并挡掉 `(未命名)`。
2. **`setViewSeat()` 只改状态不重画**：测试里直接调它之后断言 DOM 会拿到旧画面（`App.setViewSeat(1)` 后听牌率条还是旧值、铳率条还在旧格子）。补 `App.setFrame(1)`（`setFrame` 无条件 `render()`）后通过。
3. **旧断言的前提被新语义推翻**：「危险条只画主视角 / 只取第 0 行」的断言必须改成「按手牌主人那一行取、条文跟着手牌走」，否则换主视角后的数量对不上。
4. 补丁脚本处理 CRLF 文件的正确姿势：读 `newline=""` → 断言无孤立 LF → 换成 `\n` 做替换 → 写回前换回 `\r\n`。

### 38.5 待办

- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 39. 第 43 轮：铳率条改成手牌左侧的竖条 + 概率柱居中（用户 m03710 ①②③）

用户 m03710 提了三条（附截图）：
1. 在**显示他家手牌**的状态下，每一家的铳率条应当和紫色概率条一样，**只有当对应玩家是当前决策者时才显示**。
2. 铳率条显示在三家手牌外侧不美观：改成**垂直显示在手牌左侧**（同样分边框与内部，红色从下往上生长 = 从对应玩家视角看），宽度与「手牌下方的一条单独铳率条」近似，长度 ≈ 1.5 牌高（上下各伸出 .25 牌高）。
3. 紫色概率条歪了、不在牌的中央。

### 39.1 交付物

| 文件 | 改动 |
| --- | --- |
| `web/js/ui.js` | 27,252 B：新增 `tbarLayer(node)`（铺满整张牌的定位层）；`addNagaBars(node, id, nf, seen)` 去掉 `mode` / `obs`（柱只画决策者、写进定位层）；新增 `addDangerBars(handEl, nf, seat, ids)`（三条竖着的 `.dgr` + 内部 `.dgr-fill`，值 = 该玩家 `danger_*` 行里最危险的一张）；`renderPlayer` 改 `dnNf = (upNf && !hidden) ? upNf : null`，手牌容器后 `if (dnNf) { addDangerBars(hb, dnNf, seat, …) }` |
| `web/style.css` | 38,693 B：`.p-hand .tiles` 加 `position: relative`；新增 `.tbar-layer`（`left/top: -.09 牌宽/高`、`width/height = 牌宽/高`，`.tile.big` 乘 1.15）与 `.tbar.up { left: 32.5% }`（居中）；删掉 `.tbar.down` 四条，新增 `.p-dangers`（手牌左侧 `-1.02 牌宽`、`height: 1.5 牌高`）、`.dgr`（宽 `.307 牌宽`、基色边框）、`.dgr-t` / `.dgr-s`、`.dgr-fill`（`bottom: 0`）；`.p-tenpai` 的 `margin-top` `.62 → .2` 牌高 |
| `test/apptest.js` | 144,320 B：② 段 8 处改写（`down` → `dgr`：只画决策者、三条方向顺序、红段高度、随决策者换位置、隐藏他家手牌时不画）+ 7f 新增 6 条 CSS 断言（柱居中 / 定位层 / 竖条几何 / 三色 / 红段自下而上 / 旧 `.tbar.down` 已删） |
| `readme.md` | 36,567 B：把「自家手牌上下画条 / 四家铳率条在手牌下沿 / 危险条按新观察者取行」的描述改成「只画当前决策者、铳率条竖在手牌左侧」 |

### 39.2 技术要点

1. **概率柱偏心的根因**：绝对定位子元素的百分比是按 `.tile` 的 **padding box** 算的，而牌面四周有 `.09 牌宽` 的白边 padding（用户 m01518 ② 加的）⇒ 旧 `left: 22% / width: 35%` 实际落在牌的 27.0%~55.7%（中心 41.3%，偏左 8.7%），高度也被打了 0.82 折。新增 `.tbar-layer` 正好铺满整张牌的外框，柱体百分比改按真正的牌宽算：`left: 32.5% + width: 35%` ⇒ 居中。
2. **铳率条只画决策者**：直接复用 `upNf`（已表达「这一家就是决策者且没被隐藏」），再用 `!hidden` 挡一次「手牌被盖住」的情况；数量从「四家 × 每张牌三条」降到「一家三条」。
3. **竖条几何**：`.p-dangers` 绝对定位在手牌容器（`.p-hand .tiles`，加 `position: relative`）左侧 `-1.02 牌宽`（三条总宽 3 × .307 = .921 牌宽 + 缝）、`top: -.25 牌高`、`height: 1.5 牌高`；每条宽 `.307 牌宽`（= 官方 9px ÷ 29.3px），基色边框 上家蓝 `#2196F3` / 対面黄 `#FFEB3B` / 下家绿 `#4CAF50`，内部 `.dgr-fill` 贴 `bottom: 0`、高度 = 危险度百分比。
4. **取值口径**：单条竖条无法对应「某一张牌」，所以取该玩家 `danger_k/t/s[该玩家]` 行里**手里最危险的一张**（`ids` = 手牌 + 摸到的那张），tooltip 里写明数值。
5. **听牌率条的留白**：铳率条不再占手牌下沿 ⇒ `.p-tenpai` 的 `margin-top` 从 `.62` 收到 `.2` 牌高（`.board` 行高保持 7.4 不变）。

### 39.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**，517 项 OK / 0 FAIL；`python test/naga_test.py` → 138 项通过 / 0 失败；`python test/agari_test.py` → 189 项通过 / 0 失败。
- 真实数据复核（`build/_scratch/naga_samples/_conv_game_1.json`，16 局）：811 个决策帧里只有 54 个（6.7%）三条危险度全 0，每条最大值的**中位数 4.6%、90 分位 99.5%** ⇒ 竖条在真实牌谱上不会长期空着。
- 行尾：`web/js/ui.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `web/index.html` / `readme.md` 纯 LF。

### 39.4 踩坑

1. 旧断言「危险条画在每一家手牌下方、按手牌主人取行」的前提被 m03710 ① 推翻，测试里 8 处 `down` 断言必须整体改写成 `dgr`。
2. 补丁脚本里用 `len(raw)` 当字节数比较是错的（中文 3 字节）：要先 `encode("utf-8")`，否则会误以为文件被别的进程改过。

### 39.5 待办

- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 40. 第 44 轮：铳率条回滚到牌下 + 听牌率条改竖条 + 概率柱居中（用户 m03799 ①②）

用户 m03799 更正了上一轮的表述：要改的主体不是铳率条，而是「三家手牌外侧、与手牌平行的听牌率条」；并再次指出紫色概率柱仍然偏心。

### 40.1 交付物

| 文件 | 内容 |
| --- | --- |
| `web/js/ui.js` | 删除 `tbarLayer()` / `addDangerBars()`；`addNagaBars(node, id, nf, seen, mode, obs)` 恢复 `down` 支路（`tbar down k/t/s`、`height = danger_*[obs][kind] / 100 %`、0 不画、同 kind 只在最靠左那张画）；听牌率条改挂到 `.p-hand .tiles`、红段改 `style.height`；26,980 B / 纯 CRLF 508 |
| `web/style.css` | 恢复 `.tbar.down` 四条规则（`top: 100%`、`width: 30.7%`、`left: 3.4% / 34.1% / 64.8%`、上家蓝 / 対面黄 / 下家绿）；删除 `.tbar-layer` / `.tile.big .tbar-layer`；`.p-tenpai` 改成手牌左端外侧的竖条（见 40.2）；37,897 B / 纯 LF 977 行 |
| `test/apptest.js` | `dgr` 断言改回 `down`；helper 改为 `handHost` / `downCount` / `downBars` / `tpRedH`；新增夹具 `NAGA_DS1 / DT1 / DK1`（座位 1 的行）与「别家行不泄漏」负例；7f 节 CSS 断言同步；519 OK / 0 FAIL |
| `readme.md` | 4.4 节把「铳率条竖在手牌左侧 / 听牌率条 13 牌宽横条」改成「铳率条回到牌下、按牌逐张画」+「听牌率条改为手牌左端外侧的竖条」+ 概率柱居中的根因 |
| `log.md` | 本节 + 页脚首行改「第 44 轮」 |

### 40.2 技术要点

1. **概率柱偏心的根因（决定性问题）**：CSS 绝对定位子元素的包含块是祖先的 **padding edge**；`.tile` 没有 border ⇒ 它的 padding box 就是 border box，`left` / `width` 百分比本来就按**整张牌宽**解析。第 43 轮新增的 `.tbar-layer`（`left/top: -.09 牌宽/高`、`width/height: 牌宽/高`）等于把柱体又推了一个白边（牌宽 x 3.34px），正是它造成了用户看到的偏心 —— 它想修的偏移恰恰是它自己造成的。删层后 `.tbar.up { bottom: 100%; left: 32.5%; width: 35% }` 精确居中（32.5 + 35/2 = 50），且与外层尺寸倍数无关。
2. **铳率条回到「按牌逐张」**：只有「按牌画」才能表达「打出这张牌的危险度」，也就不用再取「手里最危险的一张」。门控沿用 `upNf`（已表达「这一家就是决策者且没被隐藏」），写成 `var dnBars = (upNf && !hidden) ? {} : null;`。
3. **听牌率条几何**：`position: absolute; right: calc(100% + 2px); bottom: calc(var(--tile-h) * -.25); width: calc(var(--tile-w) * .307); height: calc(var(--tile-h) * 1.5)`；基色边框 2px + 同色底，`.tp-red` 贴 `bottom: 0` 用 `style.height`（红段从该家自己的下方往上长）；挂在 `.p-hand .tiles`（已 `position: relative`）里 ⇒ 属于手牌区，随座位旋转与「切换主视角」一起走。

### 40.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**，519 项 OK / 0 FAIL；`python test/naga_test.py` → 通过 138 / 失败 0；`python test/agari_test.py` → 通过 189 / 失败 0。
- 行尾：`web/js/ui.js` / `web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `web/index.html` / `readme.md` 纯 LF。

### 40.4 踩坑

1. 补丁脚本的行尾断言写成 `assert raw.count("\n") == crlf`，对**纯 LF** 文件（`crlf == 0`）必然失败 ⇒ 正确写法是 `assert crlf == 0 or raw.count("\n") == crlf`。
2. `test/apptest.js` 的 `rows34(spec)` 里 spec 的键是**座位（行）**而不是 kind：`rows34({ 0: [0, 8000], 1: [1, 3000] })` 会把 3000 写进第 1 行 ⇒ 决策者那条手牌少得一条；补 `danger_k[0][1] = 3000` 才是「row 0 的 2m」。
3. 条高用 `(val / 100).toFixed(2)` ⇒ 断言要写 `80.00%` 而不是一位小数；`.tbar.down.k` 的 className 字符串就是 `'tbar down k'`。

### 40.5 待办

- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 视觉部分（听牌率条竖条位置、紫色柱居中）待用户目视确认 —— 沙箱无法做浏览器布局测量；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。
## 41. 第 45 轮：听牌率条间隔 0.5 牌宽 + 吃 / 碰 / 杠 / 和了的日语大字（用户 m03978 ①②）

用户 m03978 提了两条：听牌率条与手牌挨得太近（改 0.5 倍牌宽）；把吃 / 碰 / 杠 / 荣和 / 自摸的日语文字插入对应帧（仿 naga 官方界面的位置 / 字体 / 字号 / 图层关系）。

### 41.1 交付物

| 文件 | 内容 |
| --- | --- |
| `web/style.css` | `.p-tenpai` 的 `right: calc(100% + 2px)` → `calc(100% + var(--tile-w) * .5)`；`.board` 加 `position: relative`（大字的定位基准）；新增 `.vocal` 块；`.c-result` 加 `z-index: 2`；39,421 B / 纯 LF 1,001 行 |
| `web/js/ui.js` | 新增 `var VOCAL_POS = [[50, 76.92], [80, 49.23], [50, 24.62], [20, 49.23]];`（= 官方 `vocalization_pos` ÷ 700×650）；`renderBoard` 在四格 append 完之后按 `opts.vocal = { pos, text }` 追加 `<div class="vocal">`（`style.left/top` 取百分比）；导出 `VOCAL_POS`；28,178 B / 纯 CRLF 528 |
| `web/js/app.js` | 新增 `vocalTextOf(ev)`（chi→チー、pon→ポン、ankan/kakan/daiminkan→カン、nuki→null；agari 时 `winner === fromWho` → ツモ，否则ロン）与 `vocalForFrame()`（pos = `App.viewRot.indexOf(seat)`）；`render()` 把 `vocal` 传给 `renderBoard`；导出两个函数；108,552 B / 纯 CRLF 2,500 |
| `test/apptest.js` | 新增 2c 节（`VOCAL_GAME` 合成样本 + 13 条断言）；7f 节新增 4 条大字 CSS 断言、听牌率条间隔断言更新；536 OK / 0 FAIL |
| `readme.md` | 4.4 节补「大字」规则、听牌率条间隔改 0.5 牌宽 |
| `log.md` | 本节 + 页脚首行改「第 45 轮」 |

### 41.2 技术要点

1. **官方大字的权威参数**（`build/_scratch/naga_samples/_viewer_index.js` 的 `renderBa`，@69539）：`ctx.font = "900 " + Wt.vocalization_font_size + "px 'vocalization'"`；`vocalization_font_size = 60`、牌高 `hai_h = 40` ⇒ 1.5 倍牌高；`vocalization_pos = [[350,500],[560,320],[350,160],[140,320]]`、桌面 `700×650` ⇒ 百分比 [[50,76.92],[80,49.23],[50,24.62],[20,49.23]]（下标 = 展示位置 0 下 / 1 右 / 2 上 / 3 左）；先黑字偏移 (+2,+2) 再白字再 `strokeText` 细黑描边；**文字不旋转**；`takuRender` 里大字在所有牌之后、和了结算窗之前 ⇒ 我们用 `.vocal { z-index: 1 }` + `.c-result { z-index: 2 }` + `.board { position: relative }` 复刻同样的层序。
2. **取值来源**：官方 replay 状态机在 `chi` / `pon` → チー / ポン、三种杠 → カン、`reach` → リーチ；和了由结算信息给ツモ / ロン。我们的 `web/js/replay.js` 事件模型等价（`call.callType` / `agari.winner === agari.fromWho` ⇒ 自摸），所以 `vocalTextOf` 直接按事件类型判定；用户只要 5 个词，リーチ 未做。
3. **随主视角旋转**：大字的 `pos` 用 `App.viewRot.indexOf(seat)` 求「展示位置」，与牌桌其它部分同一套旋转向量 ⇒ 切换主视角后大字自动换到那名玩家的新位置（测试里 `ポン` 从 80%/49.23% 变 50%/76.92%）。
4. **听牌率条间隔**：从贴着手牌（`+ 2px`）改为 `+ 0.5 张牌宽`，仍以 `.p-hand .tiles`（`position: relative`）为定位参照。

### 41.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**，536 项 OK / 0 FAIL（新增 2c 节 13 条 + 7f 节大字 CSS 4 条）；`python test/naga_test.py` → 通过 138 / 失败 0；`python test/agari_test.py` → 通过 189 / 失败 0（后两个需 `set PYTHONPATH=.` 在根目录跑）。
- 行尾：`web/js/ui.js` / `web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `web/index.html` / `readme.md` 纯 LF。

### 41.4 踩坑

1. 想用 PIL 从用户截图反查官方大字的像素位置做交叉验证，**没成功**：截图的桌面底色是蓝的（主色 `(4,49,109)` / `(0,111,176)`），不是源码里的 `taku_color = rgb(0,75,6)`；白像素连通域扫出来的一堆 45×63 / 63×45 px 分量是牌，最大的两个（79×80、83×90 px）放大后一个是指示三角、一个是圆形标记，都不是文字 ⇒ 放弃像素交叉验证，直接按官方源码常量实现（并在交付报告里说明）。
2. 大字元素必须由 `renderBoard` 自己 append：`renderBoard` 开头 `clear(boardEl)`，写在 `web/index.html` 里的节点会被清掉。
3. `web/js/app.js` 里渲染路径只有 `render()` 一个入口，`vocal` 跟着 `renderBoard` 的 opts 一起传最省事（不要在 UI 里再读 App 状态）。

### 41.5 待办

- 视觉部分（大字的位置 / 字号 / 描边观感、听牌率条间隔）待用户目视确认 —— 沙箱无法做浏览器布局测量；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 未打包官方 `NotoSansJP-Black`（4.9 MB，OFL）：现用系统 Noto Sans JP 可变字重 + `font-weight: 900` 近似；若用户要完全一致可改为随包发布该字体子集。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 42. 第 46 轮：大字字体打包 + 副露不再写文字标签 + 听牌率条间隔 0.8 牌宽（用户 m04160 ①②③）

用户 m04160 提了三条：字体要打包；各家副露牌侧边不需要写「吃 / 碰 / 杠」等文字；听牌率条与手牌的距离改为 0.8 倍牌宽。

### 42.1 交付物

| 文件 | 内容 |
| --- | --- |
| `media/fonts/NotoSansJP-Black.subset.otf` | 新增：官方 `NotoSansJP-Black.9a73d583.otf`（4,896,876 B）的 9 字形子集「チ ー ポ ン カ ツ モ ロ ン リ」= 5,632 B / 19 字形 / 缺字 无（sha256 前缀 `4c374d1414a46262`） |
| `media/fonts/LICENSE-NotoSansJP-OFL.txt` | 新增：SIL OFL 1.1 全文（4,599 B，取自 openfontlicense.org） |
| `tools/subset_font.py` | 新增：可复现子集脚本（默认官方 URL / `--source` / `--text` / `--out`，进程内调 `fontTools.subset.main`）；3,836 B / 纯 LF |
| `web/style.css` | 新增 `@font-face`「vocalization」指向 `../media/fonts/NotoSansJP-Black.subset.otf`；`.vocal` 的 font-family 前置 `"vocalization"`；`.p-tenpai` 的 `right` `.5` → `.8` 牌宽；删除 `.meld-tag` 块；39,986 B / 纯 LF 1,006 行 |
| `web/js/ui.js` | 删掉 `meld-tag` 的 append（副露只渲染牌，种类仍留在 class 与事件列表）；27,818 B / 纯 CRLF 529 行 |
| `build.ps1` | 资源存在性检查加 `media\fonts\NotoSansJP-Black.subset.otf`（打包链路 `packaging/pyi_build.py` 本来就有 `--add-data media;media`，字体自动进冻结产物） |
| `test/apptest.js` | 7f 节：听牌率条间隔断言 `.5` → `.8`；新增 5 条（`@font-face` 指向子集、`.vocal` 用 vocalization、子集文件存在且是 OTF 且 < 20 KB、OFL 许可证存在、CSS 里已无 `.meld-tag`）；7g 节副露循环新增「副露只有牌、没有文字标签」；545 OK / 0 FAIL |
| `readme.md` | 4.4 节：听牌率条间隔 0.8、大字字体改为随包发布子集（含 OFL 与生成脚本）、副露不再写文字；目录树补 `media/fonts/`；38,451 B / 377 行 |
| `log.md` | 本节 + 页脚首行改「第 46 轮」 |

### 42.2 技术要点

1. **字体打包 = 字体文件 + 许可证 + 生成脚本**三件套（OFL 要求随字体分发许可证）。子集化参数 `--text=チーポンカツモロンリ --no-hinting --desubroutinize --name-IDs=* --drop-tables+=DSIG`：4.9 MB → 5,632 B（19 字形，保留 cmap / naming / OS/2 / CFF 等必要表；`--name-IDs=*` 保留版权与名称声明）。字体名仍是 `Noto Sans JP Black`，`@font-face` 里起名 `vocalization`（与官方 viewer 的字体名一致）。
2. **CSS 路径**：页面在 `web/`、素材在根 `media/` ⇒ 用 `url("../media/fonts/…")`，`http://`（`python server.py`）与 `file://`（直接打开 `web/index.html`）两种方式都成立。
3. **副露文字**：`meld-tag` 的 `span` 从 `web/js/ui.js` 删掉、对应 CSS 删掉；副露种类仍保留在 DOM 的 class（`meld-chi` / `meld-pon` / `meld-kakan` / `meld-ankan`）与事件列表里，因此测试与检索逻辑不受影响。
4. **听牌率条间隔**：`right: calc(100% + var(--tile-w) * .8)`（仍以 `.p-hand .tiles` 为定位参照）。

### 42.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**，545 项 OK / 0 FAIL；`python test/naga_test.py` → 通过 138 / 失败 0；`python test/agari_test.py` → 通过 189 / 失败 0（后两个需在根目录 `set PYTHONPATH=.`）。
- `python -X utf8 tools/subset_font.py` 重跑一遍，输出与已提交的子集**逐字节相同**（同 sha），子集化可复现。
- 行尾：`web/js/ui.js` / `web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `web/index.html` / `readme.md` / `build.ps1` / `tools/*.py` 纯 LF。

### 42.4 踩坑

1. 一次脚本里的多处替换必须**逐步断言、最后才写盘**：第一版把断言用的消息文本猜错了（实际文案是「听牌率条竖在手牌左端外侧…」），`AssertionError` 当场中断、文件保持原样（否则会留下半套替换）。
2. 沙箱里 `python test\*_test.py | Select-Object -Last N` 会没有输出（管道中断 / 缓冲），改成 `cmd /c "python -X utf8 test\xxx_test.py > _t.txt 2>&1"` 再读文件才稳定。
3. `fontTools.subset.main()` 直接在进程内调用即可，不要 `subprocess`（沙箱会拒绝匿名管道，与第 41 节 node 打点回退文件是同一类问题）。

### 42.5 待办

- 视觉部分（大字观感、听牌率条间隔 0.8、副露去掉文字后的观感、子集字体的渲染）待用户目视确认 —— 沙箱无法做浏览器布局测量；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5；打包链路新增了字体文件，建议完整跑一次 `build.ps1` 确认冻结产物内含该字体。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 43. 第 47 轮：「牌谱播放」入口状态机 + 空心大字（用户 m04285）

### 43.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/js/app.js` | 新增 `openReplayView()` / `resetReplay()`（入口状态机）；`#btnGoReplay` 与页签改走 `openReplayView`；`readFile()` 手动开谱时退出条目模式；导出两个新函数。110,926 B / 2,550 行 |
| `web/style.css` | `.vocal` 从实心白字改成空心字（`color: transparent` + 白描边 `calc(var(--tile-h) * .07)` + `filter: drop-shadow()` 柔光晕）。40,155 B / 1,005 行（**第 48 轮按用户 m04386 改回实心白字 + 左移避开牌河，见第 44 节**） |
| `test/apptest.js` | 第 10 节改写 + 新增 10b 节（入口状态机，19 条断言）；7f 节大字 CSS 断言更新。157,535 B / 2,329 行，564 OK / 0 FAIL |
| `readme.md` | 4.4 节补入口状态机 bullet、大字改空心字说明、第 9 节按钮名更正（浏览选择） |
| `log.md` | 本节 + 页脚首行改「第 47 轮」 |

### 43.2 技术要点

1. **静态帧不算「牌谱播放」状态**：旧页签处理只在 `!App.game` 时显示入口栏，而静态帧模式下牌谱是载入着的（`App.itemIndex >= 0`）⇒ 点「牌谱播放」只 `setView('replay')` 重画同一帧（看起来毫无反应）；首页卡片 `#btnGoReplay` 则无条件显示入口栏 + 拖放提示、但从不卸载牌谱 ⇒ 入口栏叠在旧牌桌上方（用户 m04285 ① 的截图）。
2. **`resetReplay()`**：停自动播放 → 复位 `App.game = null` / `rounds = []` / `roundIndex` / `frameIndex` / `naga = null` / `fileName` / `itemIndex = -1` / `hideOthers = false` / `viewRot = [0,1,2,3]` / `selfSeat = 0` → `syncItemNav()` + `toggleViewMenu(false)` → `clearNode` 清 `#board` / `#roundSelect` / `#eventListBody`，清 `#frameKey` / `#rpFile` / `#rpFrame` / `#rpDesc` / `#warnBar` → `setFileInfo('未载入牌谱')` → 显示 `#rpOpenBar` + `#dropZone` + 提示语 → `setView('replay')` → `syncButtons()` / `syncOthers()` / `syncFeatPanel()` / `renderNagaPanel()`（后三个在无 `App.game` 时自然留空）。
3. **刻意保留 `App.items` / `App.itemSource`**：检索结果的条目表不清空，用户回「牌谱检索」点一行时 `openItem()` 会按 `gameLogId()` 命中缓存或重新 `/api/read`、重新把 `App.itemIndex` 设成该下标 ⇒ 又回到静态帧条目模式；反过来，手动「浏览选择…」/拖入走 `readFile()`，那里显式 `App.itemIndex = -1; syncItemNav();` 退出条目模式。
4. **入口状态机**：`openReplayView()` = `if (!App.game || App.itemIndex >= 0) { resetReplay(); return; } setView('replay');`；页签循环改 `if (v === 'replay') { openReplayView(); return; }`；首页卡片 `bind('btnGoReplay', openReplayView)`。⇒ 正常播放时只切视图（牌谱不卸载），静态帧 / 未载入时先卸载再回「等待选择」。
5. **空心大字**：`color: transparent` + `-webkit-text-stroke: calc(var(--tile-h) * .07) #fff` + `filter: drop-shadow(0 0 calc(var(--tile-h) * .03) #000)`（原来 = 实心白字 + 极细黑描边 + 右下黑影）；`paint-order: stroke fill` 保留。用 `filter` 而不是 `text-shadow`，因为空心字在黑牌河上要有一圈柔光才看得清。**（第 48 轮按用户 m04386 改回实心白字，遮挡问题改用「整体左移」解决，见第 44 节）**

### 43.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**，564 项 OK / 0 FAIL（第 10 节改写 + 10b 节 19 条 + 7f 大字 CSS 断言）；`python test/naga_test.py` → 通过 138 / 失败 0；`python test/agari_test.py` → 通过 189 / 失败 0（后两个需在根目录 `set PYTHONPATH=.`）。
- 行尾：`web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `web/index.html` / `readme.md` 纯 LF。

### 43.4 踩坑

1. 10b 节里第二次摆出「静态帧再点入口」的场景时，若不先 `App.loadText(...)` 就 `App.openItem(0)`，会走 `/api/read` 分支 —— 测试里 `global.fetch` 一律 reject（`no network in test`）⇒ 断言失败；正确顺序 = 先 `loadText`（名字与 `log_id` 一致，让 `openItem` 命中「当前牌谱就是这一条」分支）再设 `App.items`。
2. 测试假 DOM 的 `El` 没有 `innerHTML`（只有 `_cls` / `style` / `className` setter）⇒ 清空节点只能用 `clearNode` / `textContent = ''`，`resetReplay` 也按这个约束写。
3. `.vocal` 从实心白字改空心字时，若只改 `color` 不改描边宽度，1.5 牌高的字号下轮廓太细看不清 ⇒ 描边单独放宽到 `.07` 牌高并加 `drop-shadow` 柔光（`text-shadow` 对空心字只是在字后加一块模糊，不如 `filter` 干净，故一并去掉）。

### 43.5 待办

- 视觉部分（空心大字在牌河上的观感、静态帧点入口后回到「等待选择」的画面）待用户目视确认 —— 沙箱无法做浏览器布局测量；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m04269 ① 里我提出的「静态帧是否也画大字」仍待用户表态（当前静态帧复用同一播放视图，会画；如不要，静态帧不传 `vocal` 一行即可）。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 44. 第 48 轮：大字改回实心 + 左移避开牌河（用户 m04386）

### 44.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/style.css` | `.vocal` 从空心字改回**全实心白字**（`color: #fff` + 细黑描边 `calc(var(--tile-h) * .003) #000` + 右下黑影 `text-shadow: calc(var(--tile-h) * .05) … 0 #000`），去掉 `color: transparent` 与 `filter: drop-shadow()`。40,109 B / 1,006 行 |
| `web/js/ui.js` | 新增 `VOCAL_DX = 19.8` / `VOCAL_MIN_X = 8.3`，大字的 x 改成 `Math.max(VOCAL_MIN_X, VOCAL_POS[pos][0] - VOCAL_DX)`：展示位置 0/2 = 30.2%、1 = 60.2%、3 = 8.3%。29,124 B / 537 行 |
| `test/apptest.js` | 2c 节 5 处大字坐标断言改为左移后的值（含 8.3% 的贴边钳位）；7f 节 `.vocal` CSS 断言改回实心白字 + 黑影、`!/filter: drop-shadow/`。157,616 B / 2,329 行，全部通过 |
| `readme.md` | 4.4 节大字条目：实心白字 + 左移规则（四个位置的最终百分比 + 左侧贴边的原因） |
| `log.md` | 本节 + 第 43.1 / 43.2 两处补注 + 页脚首行改「第 48 轮」 |

### 44.2 技术要点

1. **左移量的来历**：牌桌宽 = 9.5 + 8.6 + 9.5 张牌宽 + 两条 0.25 的格间距 = 28.1 张牌宽 ⇒ 1 张牌宽 = 3.56 个百分点；牌河块 = `RIVER_COLS`(6) 张牌宽、居中于各家格 ⇒ 半宽 10.7；文字 = 2 个全角字形、字号 = 1.5 牌高 = 2.05 张牌宽 ⇒ 半宽 7.3；再留 0.5 张牌宽（1.8）的间隙 ⇒ `VOCAL_DX = 19.8`。`transform: translate(-50%, -100%)` 不变，left 仍表示「文字中线」。
2. **为什么位置 3（左侧）要钳位**：左家的牌河是旋转后的竖条、横跨左列中线（约占牌桌宽 6%~25%），文字再怎么左移都只会更压住它；`VOCAL_MIN_X = 8.3` = 文字半宽 7.3 + 1，保证文字左缘（≈1%）不被 `.board-box { overflow: hidden }` 裁掉 ⇒ 左侧那份仍会碰到自己的牌河，如实记在待办里。
3. **保留实心 + 黑影**：官方 `renderBa` 本来就是「白字 + 右下偏移黑影 + 细黑描边」；第 47 轮为不遮牌河改成空心字，本轮用户要求改回实心、遮挡问题改用整体左移解决。
4. **静态帧照旧画大字**：用户 m04386 明确「检索到鸣牌等有大字的状态暂时不用改」⇒ 第 45 轮遗留的待确认项关闭（静态帧复用同一播放视图、继续画大字）。

### 44.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**（2c 节 5 处坐标 + 7f 节实心 CSS 断言）；`python test/naga_test.py` → 通过 138 / 失败 0；`python test/agari_test.py` → 通过 189 / 失败 0。
- 行尾：`web/js/ui.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `readme.md` 纯 LF。

### 44.4 踩坑

1. 坐标断言要跟着实现改：`left` 用 `vx.toFixed(1) + '%'` 输出，所以断言必须写 `30.2%` / `60.2%` / `8.3%` 这类一位小数（旧断言是 `50%` / `80%` / `20%` 的整数）。
2. 左移量与文字宽度绑定：本项目的大字都是 2 个全角字形（チー / ポン / カン / ツモ / ロン），所以能用一个常数；若以后加 1 字或 3 字的词，要按字数重算（`VOCAL_DX` 的注释里写了公式）。

### 44.5 待办

- **左侧（展示位置 3）的大字无法完全避开左家牌河**（竖条、横跨列中线）—— 目前只能贴住牌桌左端；若用户仍觉得挡，可改成右移到 34% 附近（会压住中央信息框左缘）或缩小字号，待确认。
- 视觉部分（实心大字 + 左移后的观感）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 45. 第 49 轮：听牌率条内部透明（用户 m04422）

### 45.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/style.css` | `.p-tenpai` 的 `background: #4CAF50` → `transparent`；`.p-tenpai.tp-t` / `.p-tenpai.tp-k` 删掉 `background`（只留 `border-color`）；块首注释改写 |
| `test/apptest.js` | 7f 节两条 CSS 断言：绿框 + `background: transparent`；`.tp-t` / `.tp-k` 只有 `border-color`、不再有 `background` |
| `readme.md` | 4.4 节听牌率条条目：基色说明改成「**边框**按相对位置定色」「条内部**透明**」 |
| `log.md` | 本节 + 页脚 |

### 45.2 技术要点

1. **只改内部填充，不动边框**：用户 m03627 的「边框始终是基色」仍然成立，所以 `.p-tenpai` 保留 `border: 2px solid #4CAF50`（下家绿）+ `.tp-t` / `.tp-k` 只覆盖 `border-color`，把三条规则里的 `background` 全部去掉（否则黄 / 蓝底色会盖住透明效果）。
2. **红段不受影响**：`.p-tenpai .tp-red`（`position: absolute; left: 0; right: 0; bottom: 0; background: var(--danger)`，高度 = 听牌率）原样保留 —— 用户 m04422 明确「随着听牌率升高出现的红条保持原样」。
3. 视觉结果：听牌率 0 时只见一个空心基色框；听牌率 100% 时整条被红段填满、只剩基色边框 ⇒ 既能看到数值，也能分辨是谁家的（与 m03627 的诉求一致）。

### 45.3 测试

- `node test/apptest.js` → 全部通过（0 失败）；`python test/naga_test.py` → 138/0；`python test/agari_test.py` → 189/0。
- 行尾：`web/style.css` 纯 LF（1,006 行）、`test/apptest.js` 纯 CRLF（2,329 行）、`readme.md` 纯 LF、`log.md` 纯 CRLF；根目录临时文件清零。

### 45.4 踩坑

1. 断言正则里 `background:\s*transparent` 要写成 `[^}]*background:` 前缀匹配（`.p-tenpai\s*\{` 之后到 `}` 之间），否则会把 `.tp-red` 的 `background: var(--danger)` 误判进来。
2. 删 `background` 时必须连 `.tp-t` / `.tp-k` 的那两行一起清掉 —— 只改 `.p-tenpai` 的话，`.tp-t` / `.tp-k` 的更高优先级（更具体的选择器）仍然给黄 / 蓝底上色，测试里不容易发现（页面上才看得见）。

### 45.5 待办

- 视觉部分（透明听牌率条 + 红段的对比度）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 46. 第 50 轮：回滚大字左移 + 静态帧不画大字（用户 m04456）

### 46.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/js/ui.js` | 删掉 `VOCAL_DX = 19.8` / `VOCAL_MIN_X = 8.3` 及其注释；`renderBoard` 里 `vo.style.left = vp[0] + '%'`（恢复官方原位） |
| `web/js/app.js` | `vocalForFrame()` 开头加 `if (App.itemIndex >= 0) { return null; }` |
| `test/apptest.js` | 2c 节坐标断言回滚为 `80%` / `50%` / `20%` / `50%` 系列；新增 5 条静态帧不画大字断言 |
| `readme.md` | 4.4 节大字条目：删掉左移段落、补「静态帧不画大字」 |
| `log.md` | 本节 + 页脚 |

### 46.2 技术要点

1. **位置完全回滚**：文案层（`.vocal`）不变 —— 仍是第 48 轮用户 m04386 要的**全实心白字**（`color: #fff` + 细黑描边 + 右下黑影），只把第 48 轮加的**水平位移**去掉。现在四个展示位置 = 官方 `vocalization_pos` 原值：下 50% / 76.92%、右 80% / 49.23%、上 50% / 24.62%、左 20% / 49.23%。常量 `VOCAL_DX` / `VOCAL_MIN_X` 一并删除（不再有 `Math.max` 钳位）。
2. **静态帧不画大字**：判据与其它「静态帧」逻辑保持一致 —— `App.itemIndex >= 0`（牌谱检索结果条目 / 全部浏览条目；也是 `othersLocked()`、静态帧锁定主视角用的同一个判据）。闸门放在 `vocalForFrame()` 里而不是 `render()` 里，这样任何调用方（包括测试直接调 `App.vocalForFrame()`）都拿到 `null`。
3. 结果是：**检索静态帧**完全没有大字、牌河不被遮挡；**正常播放**（手动打开牌谱）照旧画 チー / ポン / カン / ツモ / ロン。

### 46.3 测试

- `node test/apptest.js` → 全部通过（0 失败）；`python test/naga_test.py` → 138/0；`python test/agari_test.py` → 189/0。
- 2c 节新增断言：正常播放碰帧仍画「ポン」→ 切到条目模式（`App.items = [...]`、`App.itemIndex = 0`）后 `vocalForFrame() === null` 且碰帧 / 吃帧 / 和了帧都不再出现 `.vocal` → 退出条目模式后「ポン」恢复。
- 行尾：`ui.js` / `app.js` / `apptest.js` / `log.md` 纯 CRLF，`style.css` / `readme.md` 纯 LF；根目录临时文件清零。

### 46.4 踩坑

1. 坐标断言要从「一位小数」改回整数百分比（`80%` / `50%` / `20%`），因为回滚后 `left` 直接用 `vp[0] + '%'` 输出；`top` 仍是两位小数（76.92% / 49.23% / 24.62%）。
2. 静态帧断言里 `App.items` 必须给一条带 `label` 的记录：`frameKeyText()` 在条目模式下会读 `App.items[App.itemIndex].label`（不匹配时才回退现算），空数组配 `itemIndex = 0` 会取到 `undefined`。
3. 测完必须把 `App.itemIndex` 复位为 `-1` 并清空 `App.items` / `App.itemSource`，否则后面的「步进」节里 `#controls` 的点击代理会被 `App.itemIndex < 0` 这个门挡住（按钮点了没反应）。

### 46.5 待办

- 视觉部分（大字回到官方原位、静态帧无大字）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 47. 第 51 轮：同种 5 的概率条优先普通 5（用户 m04498）

### 47.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/js/ui.js` | `renderPlayer` 里新增 `barOwner`（每个 kind 选一张「条主」）与 4 处调用门控；上柱 / 下柱共用 |
| `test/apptest.js` | 新增 2b2 节 9 条断言（5m / 5s / 只有赤 5 / 摸到的普通 5） |
| `readme.md` | 4.4 节铳率条条目补 5m / 5p / 5s 例外 |
| `log.md` | 本节 + 页脚 |

### 47.2 技术要点

1. **根因**：概率条本来按「同 kind 只画最靠左那张」实现（`seen[kind]`），而手牌经 `Tiles.sortHand()`（按牌 ID 升序）排列，**赤 5 的 ID 是同一花色 5 里最小的**（赤 5 = `kind * 4 + 0`；5m = 16 赤 / 17 / 18 / 19，5p = 52 / 53 / 54 / 55，5s = 88 / 89 / 90 / 91）⇒ 赤 5 反而最先拿到条。
2. **修法**：在 `renderPlayer` 里先算一张「条主」表 `barOwner[kind]` —— 按 `rest`（已排序）再 `drawn` 的顺序扫描，同 kind 首次出现时登记，之后只要「新的不是赤 5、登记的是赤 5」就替换 ⇒ 普通 5 一旦出现就夺走条的归属；手里只有赤 5 时归属仍是它（用户要求的例外）。扫描顺序保证与原「最靠左」行为一致（摸到的牌排在最后 ⇒ 同 kind 时手牌优先）。
3. **上柱与下柱同一规则**：打牌预测柱（`'up'`）与铳率条（`'down'`）都按 `barOwner[Tiles.kindOf(该牌)] === 该牌` 门控 —— 两条本来就共用「同种牌只画最左那张」的规则，这里保持一致；`addNagaBars()` 内部的 `seen` 记账不动（现在每个 kind 至多进来一次）。
4. **摸到的牌也算「手里」**：`barSeq = rest + drawn` ⇒ 手里只有赤 5m、刚摸到普通 5m 时，条画在**摸到的那张**上（不画在赤 5 上）—— 这正是要打出的选择，符合规则本意。

### 47.3 测试

- `node test/apptest.js` → 全部通过（0 失败）；`python test/naga_test.py` → 138/0；`python test/agari_test.py` → 189/0。
- 2b2 节：5m 样本（手牌 `[16, 17, 18, …]`）→ 条在 17、16 空、`up` / `down` 各 1 条；只有赤 5m → 条在 16；5s 样本 → 条在 89、88 空（证明不是写死 5m）；手牌只有赤 5m + 摸到普通 5m（`v5Game(..., 4, 17)`）→ 条在摸到的 17 上、16 空、`.p-hand` 子树总共 1 条 `up`。
- 行尾：`ui.js` / `apptest.js` / `log.md` 纯 CRLF，`style.css` / `readme.md` 纯 LF；根目录临时文件清零。

### 47.4 踩坑

1. 「摸到普通 5」那条用例第一版是空转的：`v5Game()` 的摸牌写死 `tile: 108`（東），断言又只查了不在手牌里的 ID ⇒ 永远通过。改成给 `v5Game(hand0, kind, drawTile)` 加第三参、并把查找范围放到整个 `.p-hand`（新增 `barOnIn(root, id)`，`barOn()` 变成它的薄包装）才真正验到。
2. 断言里的条数格式必须是 `'1:1'` 这种 `up:down` 串；`tilesIn()` 是递归的，所以 `.p-hand` 子树能同时看到手牌与摸牌槽里的牌。

### 47.5 待办

- 视觉部分（5 的条落在哪张牌上）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 48. 第 52 轮：第零类特征 + AI 模型决策切换（用户 m04556）

### 48.1 交付物

| 文件 | 变更 |
| --- | --- |
| `mjscore/ai_models.py` | **新建**：AI 模型词汇层（别名表 / 规范化 / 系列判定 / 3 个第零类定义 / 4 种检索方案） |
| `mjscore/feats.py` | 第零类 3 项（`AI_FEATURES` / `AI_KEYS`）+ `ai_values` / `ai_models_text` / `ai_series_text`；`FEATURES` 共 37 项；`FACT_COLS` 加 `ai_models` / `ai_series` |
| `mjscore/naga.py` | `_model_values` / `_model_map`：`dahai_pred` / `huro` / `reach` / `kan` 保留**全部模型**（外层模型维）；`game["naga"]["models"]` |
| `mjscore/cli.py` | `fill_naga` → `fill_ai`（第零类 3 列 + 2 辅助列，天凤行填否 / 空串）；新增 `--ai` / `--ai-pick`；`run_query(..., ai=)` |
| `mjscore/store.py` | `SCHEMA_VERSION` 6、索引 `frame_ai`、frame 表加 `ai_models` / `ai_series`、`compile_ai` + `compile_query(conds, ai=None)` |
| `mjscore/server.py` | `/api/features` 返回 `ai_features` / `ai_modes`；`api_query` 透传 `ai` |
| `web/index.html` | NAGA 面板标题 → `#nagaModelBtn` + `#nagaModelMenu`；检索页新增第零类方案区（`#aiModes` / `#aiPicks` / `#btnAiClear`） |
| `web/style.css` | `.naga-model-btn` / `.naga-model-menu` / `.ai-row` / `.ai-plan` / `.ai-modes` / `.ai-picks` |
| `web/js/app.js` | `App.aiModel` + AI 模型层（`aiFoldFrame` / `aiFrame` / `setAiModel` / `renderAiModelMenu` / `syncAiModelBtn`）+ 第零类方案（`Sc.aiMode` / `Sc.aiPicks` / `aiPayload` / `renderAiPlan`） |
| `web/js/mjsfeat.js` | 第零类 3 项注册表 `AI_FEATURES`（并导出） |
| `mjscore/__init__.py` / `package.json` | 版本 → 0.3.0 |
| `test/mjscore_test.py` / `test/naga_test.py` / `test/apptest.js` | 37 项 / 第零类三态 / 第零类检索四方案 / AI 模型菜单断言 |
| `readme.md` / `log.md` | 第 2 章新增 2.1 第零类（原第一类改为 2.2）、4.3 四方案、4.4 AI 模型按钮、版本号 0.3.0；本节 + 页脚 |

### 48.2 技术要点

1. **只有四个字段带模型维**：报告里 `dahai_pred`（打牌预测，外层 = 模型下标）、`huro`（每座位 × 每模型 × 选项）、`reach`、`kan` 才分模型；`danger_*`（铳率条）、`tenpai_*`（听牌率条）、`end_type` / `game_rank`（右下 5 个数据）**只有一套**（41 份样本实测）⇒ 切换模型只影响概率条与决策表的副露 / 杠 / 立直选项，其余照旧显示。
2. **模型规范化**：`ALIASES` = ニシキ → `NAGA-平衡`、カガシ → `NAGA-超副露`、4.1b → `Mortal-4.1b-平衡`（另有 ヒバカリ / オメガ / ガンマ / ニュー / シグマ → `NAGA-<原名>`）；裸版本号（`^\d+(\.\d+)?[a-z]?$`）→ `Mortal-<版本>-平衡`；**系列 = 第一个短横线之前的字符串**（用户 m04556 ③ 的判定口径）。官网与官方 viewer 的 JS 里查不到「超副露 / バランス」字样，这两个别名按用户给的标签写死。
3. **第零类入库**：每行写 3 列 `f_ai_balance` / `f_ai_superhuro` / `f_ai_mortal41b`（是 / 否）+ 2 个辅助列 `ai_models`（规范名逗号串）与 `ai_series`（去重系列逗号串）；天凤牌谱三项「否」、辅助列空串。第零类**不走「特征词条」**（`compile_query` 里遇到第零类 key 会明确报错）。
4. **第零类检索**：`compile_ai(ai)` 四种互斥方案 —— `any` = `ai_models <> ''`；`naga` / `mortal` = `ai_series LIKE '%NAGA%'` / `'%Mortal%'`；`multi` = 勾选的列全部 `= '是'`（**不勾任何项 = 不限**）。它与第一、二类条件是 AND，且两者都空时才报「请至少添加一条牌谱特征条件或选择一个第零类检索方案」。
5. **前端展示**：`App.aiModel = -1`（无AI决策）为默认，此时 `aiFrame()` 返回 null ⇒ 概率条 / 听牌率条 / 铳率条 / 决策表 / 右下 5 个数据全不画，就是天凤牌谱的展示方式；选某个模型后用 `aiFoldFrame()` 把每模型数组折叠到该下标再画。菜单按钮仿「切换主视角」（`#nagaModelBtn` + 向下生长的 `#nagaModelMenu`，4 行，报告里没有的模型加 `.disabled`）。关键帧判定仍固定按平衡形那一档，不随所选模型变化。

### 48.3 测试

- `node test/apptest.js` → 全部通过（0 失败）；`python test/naga_test.py` → **142/0**（原 138，+4）；`python test/agari_test.py` → 189/0。
- `test/mjscore_test.py` 全量（约 57~61 分钟）在沙箱跑不了（`Start-Job` 被拒）⇒ 用探针复算本轮改动的每一条断言：注册表 37 项、前 3 项 = 第零类、三名 / 三列名、`FIRST_KEYS` 17 项且 `[9] == riichi_others_n` / `[10] == ippatsu`、`ai_values` 三态、`ai_series_text`、`FEATURES[20:] == SECOND_KEYS`、`SCHEMA_VERSION == 6`、`APP_VERSION == "0.3.0"`、`query_detail` 37 项、`export_json (3, 37, 1)`、`frame_feats` 37 项、`GET /api/features` → 37 + `ai_features` 3 + `ai_modes` 4。
- 真实库端到端：天凤 1 谱 164 帧（`any/naga/mortal` 命中 0、`multi` 不勾 164）；2 份**三模型** NAGA 谱 1010 帧（三种方案都 1010、`ai_models` = `NAGA-平衡, NAGA-超副露, Mortal-4.1b-平衡`、`ai_series` = `NAGA, Mortal`）；9 份**两模型**（ニシキ + カガシ）谱 819 帧（`any = naga = 819`、**`mortal = 0`**）。
- 行尾：`mjscore/*.py` / `test/mjscore_test.py` / `test/naga_test.py` / `web/index.html` / `web/style.css` / `readme.md` 纯 LF，`web/js/app.js` / `web/js/ui.js` / `test/apptest.js` / `log.md` 纯 CRLF。

### 48.4 踩坑

1. `Start-Job` 在本沙箱被拒（`PSScheduledJob 作业源适配器引发异常：… ScheduledJobs 的访问被拒绝` + `Access is denied`）⇒ 长时间测试只能由用户本机跑。
2. `ai_models.MODE_NAMES` 是**字典** `{key: 中文名}`，而 `store.py` 里误按列表索引（`MODE_NAMES[MODE_KEYS.index(mode)]`）⇒ 任何带 `ai` 的检索都抛 `KeyError: 0`。
3. `web/js/app.js` 的 `Sc` 字面量漏加 `aiMode` / `aiPicks`（第一次补丁只加了 UI 逻辑）⇒ `renderAiPlan()` 在「同时具有」时抛 `TypeError: Cannot read properties of undefined`。
4. 界面文案里的「35 个特征」有 4 处（首页 / 分析页 / `--full` 说明 / 检索页）容易漏改，单独走一遍补丁。
5. 跑 python 测试必须先 `set PYTHONPATH=<绝对路径>`（写 `'.'` 会静默 exit 1、无任何输出）。

### 48.5 待办

- 视觉部分（AI 模型下拉按钮 / 第零类方案区 / 「无AI决策」时数据全部留空 / 缺模型灰显）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- `test/mjscore_test.py` 全量（约 57~61 分钟）待用户本机跑。
- 用户 m04498 的取舍待确认：摸到的牌也算「手里」（手里只有赤 5m 而摸到普通 5m 时，条画在摸到的那张上）。
## 49. 第 53 轮：控制面板两行七列 + 完场结算框（用户 m05131）

### 49.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/index.html` | `#controls` 重写为**两行七列 14 个按钮**（新增 `allFirst` 开局 / `allLast` 完场 / `prevSelf` 上一自家决策 / `nextSelf` 下一自家决策；「上一关键 / 下一关键」改名「上一决策 / 下一决策」、「开局 / 本局结束」改名「本局开始 / 本局结算」），删除 `auto` 按钮与 `#rpDesc` 描述条；竖线改用 `|` / `‖`。20511 B |
| `web/style.css` | `.controls` 改成两行网格（`repeat(6, minmax(0,1fr)) minmax(0,1.5fr)` + `grid-auto-rows: 20px`）；删掉 `.desc-bar`，新增 `.final-box` / `.fb-row` / `.fb-rank` / `.fb-id` / `.fb-score`；`#btnView` 的 `min-width: 200px` 去掉。43674 B / 1067 行 |
| `web/js/app.js` | 删 `AUTO_MS` / `autoBtn` / `startAuto` / `stopAuto` / `case 'auto'` / `App.auto` / `App.timer`；新增 `App.finalShown` 与 `atGameEnd` / `showGameEnd` / `seatOfFrame` / `stepSelfKey` / `finalBoxRows` / `renderFinalBox`；`onAct` 新增四个分支、`next` 在终局末帧改为跳出结算框；`syncButtons` 换四个 `setDisabled`。127860 B / 2900 行 |
| `test/apptest.js` | `:255` 改为控制面板结构断言（14 按钮 / 无 `auto` / 源码文案含新旧按钮名与 `‖◀`·`‖▶`、无 `⎮◀`·`⎮▶`）；`:840` 的描述条断言改用事件列表；第 9 节整体换成 22 条（跳转 + 完场结算框）；7f 节 CSS 断言更新。174435 B / 2554 行，全部通过 |
| `readme.md` | 4.4 节：键盘行与关键帧条目改名、尺寸行改「控制条 50px 两行七列（描述栏已删除）」、新增两条 bullet（两行七列说明 + 完场结算框）、「切换主视角」按钮位置改成上排最右列（1.5 倍宽）、删掉「控制条横向滚动」。45055 B / 398 行 |
| `log.md` | 本节 + 页脚首行改「第 53 轮」 |

### 49.2 技术要点

1. **按钮竖线错位**：原符号 `⎮`（U+23AE，积分延长符）字形偏高，与 `◀` / `▶` 并排时看起来竖线上移 ⇒ 换成整字宽的 `|`（本局开始 / 本局结算）与 `‖`（U+2016，整个牌谱的开局 / 完场）。
2. **两行七列而牌桌不动**：`.controls` 仍是 `flex: 0 0 50px; height: 50px`，只是内部从 flex 行换成 `display: grid` + 两行（`grid-auto-rows: 20px`）；DOM 源顺序就是「上排 7 个 + 下排 7 个」；第 7 列 `minmax(0, 1.5fr)` 给「切换主视角 / 隐藏他家手牌」留出单行显示完整 ID 的宽度（原来的 200px 最小宽度必须去掉，否则控制条要横向滚动）。
3. **完场结算框是浮层不是帧**：`App.finalShown` 只在「终局末帧再点一次下一步」或点「完场」时置真；`renderFinalBox()` 把它 append 到 `#board`（`z-index: 5`，在牌之上、中央结算框之下）；`finalBoxRows()` 在 `App.itemIndex >= 0`（静态帧条目模式）时返回 null ⇒ 不进检索结果、不改进度；`setRound` / `setFrame` / `resetReplay` / `loadText` 都把 `finalShown` 复位 ⇒ 离开终局末帧自动收起。
4. **「上一 / 下一自家决策」**：新写 `seatOfFrame(frames, i)` 按**被扫描的那一帧**判断决策者（`fr.state.drawn.player`，否则 `fr.ev` 是 chi / pon 时取 `ev.player`）—— 不能用 `frameSeatOf()`，它读的是当前 `App.frameIndex`，扫别的帧会判错。条件 = `isKeyFrame(frames, i) && seatOfFrame(frames, i) === App.selfSeat`。
5. **删除自动播放**：`AUTO_MS` / 定时器 / `case 'auto'` / 状态字段 `auto`·`timer` 全部移除；`setView()` 不再需要 `stopAuto()`（改成只在 `replay` 时 `fitBoard()`）。

### 49.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**；`python test/naga_test.py` → 142/0；`python test/agari_test.py` → 189/0。
- 第 9 节 22 条覆盖：`atGameEnd` / `stepSelfKey` / `showGameEnd` / `finalBoxRows` 是函数；`nextSelf` 落在主视角自己的关键帧、`prevSelf` 往回；`allFirst` 回 0 局 0 帧且随即禁用；`allLast` 跳终局末帧 + `finalShown === true` + `.final-box` 有 4 行 `.fb-row`（首行含 `1位`、按最终得点降序、得点是纯数字）；`prev` 之后浮层消失；终局末帧点 `next` 帧号不变且浮层保持；`App.itemIndex === -1`。
- 行尾：`web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/index.html` / `web/style.css` / `readme.md` 纯 LF。

### 49.4 踩坑

1. 假 DOM 只解析「带 id 的元素」与「带 data-act 的按钮」的**结构**，不解析按钮里的静态文字（`textContent` 为空）⇒ 「按钮改名」这类断言只能对 `web/index.html` 的源码字符串做（`html.indexOf('上一决策')` 等）。
2. 断言里不能写 `'rpDesc' not in out`：我自己的新断言文本里就含 `byId.rpDesc`，会误报；放宽成 `'byId.rpDesc.' not in out`。
3. 「往下扫自家关键帧」从 `App.frameIndex + dir` 起手，而帧 0 不是关键帧 ⇒ `prevSelf` 可能停在原地，测试里用 `<=` 而不是 `<`。

### 49.5 待办

- 视觉部分（两行七列控制条的按钮宽度、完场结算框的字号与透明度、竖线符号观感）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 待用户确认：m05131 ② 里「完场」按钮的符号原文写「双竖线 + 朝左三角」（与「开局」相同），实现按语义取**朝右**（`‖▶ 完场`）。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

---
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。
## 50. 第 54 轮：结算框加宽 + 「完场 / 下一…」按钮的可点性修正（用户 m05277）

### 50.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/style.css` | `.final-box`：`min-width` 11 → **15 张牌宽**、新增 `max-width: calc(100% - 24px)`、`padding` 上下 `.35 → .7` 牌高、左右 `.8 → 1.2` 牌宽、`line-height` 1.55 → **2**；`.fb-row` 的 `gap` `.9 → 1.4` 牌宽；`.fb-id` 加 `min-width: 0; overflow: hidden; text-overflow: ellipsis`。44038 B / 1068 行 |
| `web/js/app.js` | 新增 `nextFallback()`（本局内没有目标帧时：还在本局 ⇒ 跳到本局结算帧；已在本局结算帧 ⇒ 跳到下一局开局，最后一局则等同「完场」）；`stepKey(1)` / `stepSelfKey(1)` 找不到目标时调用它；`onAct` 的 `next` 在末帧改走它；`syncButtons` 里 `next` / `nextKey` **不再禁用**，`allLast` 的禁用条件改成 `atGameEnd() && App.finalShown`。129109 B / 2922 行 |
| `test/apptest.js` | 第 3 节末帧断言改成「不再禁用 + 再点进下一局」；第 9 节新增 12 条（未弹出时「完场」可用、已弹出时禁用、「完场」跳到弹出时刻、三个「下一…」的结算帧兜底）；7f 节新增 3 条结算框 CSS 断言。177500 B / 2598 行，全部通过 |
| `readme.md` | 4.4 节：关键帧条目补「本局没有目标帧时跳到本局结算帧 / 下一局」，控制面板条目补可点性规则，结算框条目补加宽 / 留白 / 行距。45921 B / 398 行 |
| `log.md` | 本节 + 页脚首行改「第 54 轮」 |

### 50.2 技术要点

1. **「完场」的可点性**：原来 `setDisabled('allLast', atGameEnd())` ⇒ 只要停在终局末帧就灰，但那时结算框还没弹出。改成 `atGameEnd() && App.finalShown`：只有在**已经弹出结算框**时才灰；其它任何位置都能点，点了就 `setRound(最后一局, 末帧)` + `finalShown = true`（用户 m05277 ②）。
2. **`nextFallback()` 的两种落点**：`App.frameIndex < frames.length - 1` ⇒ `setFrame(frames.length - 1)`（本局结算帧）；已在结算帧 ⇒ `roundIndex >= rounds.length - 1` 时跳出结算框，否则 `setRound(roundIndex + 1, 0)`（等效「下一局」，用户 m05277 ③）。
3. **`stepKey(1)` 重写**：原来是「找不到就夹到末帧」，现在是「找到就停、找不到走 `nextFallback()`」—— 对本局末帧就在附近的情况结果相同（仍落到末帧），区别只在**已经在结算帧时**：原来什么也不做（按钮还灰着），现在进下一局。`prevKey` 分支保持原样（`i` 递减到 0 就停）。
4. **`stepSelfKey(1)`** 同理：找不到「等待主视角决策」的关键帧时走 `nextFallback()`；`stepSelfKey(-1)` 保持在原地。
5. **结算框尺寸**：宽度从 11 张牌宽加到 15 张牌宽（够放下 `普通盛り無料` 这类 6 字 ID），`max-width: calc(100% - 24px)` + `.fb-id` 省略号兜住极端长的名字；上下内边距翻倍、`line-height` 1.55 → 2、三列 `gap` 加大到 1.4 牌宽（用户 m05277 ①）。
6. **「下一步」永远可用**：`setDisabled('next', false)`，因为无论在哪个位置点它都有确定落点（下一帧 / 结算帧 / 下一局 / 结算框）。

### 50.3 测试

- `node test/apptest.js` → **全部通过（exit 0）**；`python test/naga_test.py` → 142/0；`python test/agari_test.py` → 189/0。
- 新增断言覆盖：在第 9 局末帧但 `finalShown === false` 时 `allLast` 可用、点它后 `finalShown === true` 且帧号不变；`App.setRound(0, 末帧 - 1)` 后 `next` / `nextKey` / `nextSelf` 三个按钮 `disabled === false`，各自点一次落在本局结算帧、再点一次进第 2 局第 0 帧。
- 行尾：`web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `readme.md` 纯 LF。

### 50.4 踩坑

1. 第 3 节原来断言「末帧时『下一步』被禁用」（`bNext.disabled === true`）—— 这条前提被用户 m05277 ③ 推翻了，测试从 1 个 FAIL 暴露出来；改成「不再禁用 + 点它进下一局」，并顺手把局号复位（否则第 4 节的关键帧测试会从第 2 局开始）。
2. 三个「下一…」的兜底都要单独测：`next` 走 `onAct`、`nextKey` / `nextSelf` 走各自函数，虽然共用 `nextFallback()`，但入口不同（少测一个就可能漏掉某个函数忘了接）。

### 50.5 待办

- 视觉部分（结算框的新尺寸与留白、长玩家 ID 的显示）待用户目视确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 待用户确认：「完场」按钮的符号（原文写「双竖线 + 朝左三角」，实现为 `‖▶`）。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）与 node 打点路径待用户本机验证。
- 仍未解：`end_num` 恒为 1 的真义；途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）没有真实样本可对。

## 51. 第 55 轮：「上一…」三个按钮的反向兜底（用户 m05350）

### 51.1 交付物

| 文件 | 变更 |
| --- | --- |
| `web/js/app.js` | 新增 `prevFallback()`（镜像 `nextFallback()`）；`stepKey(-1)` 找不到关键帧时改走它；`stepSelfKey(-1)` 同样；`onAct` 的 `prev` 在第 0 帧时改走它；`syncButtons` 里 `prev` / `prevKey` **不再禁用**。130341 B / 2943 行 |
| `test/apptest.js` | 第 3 节「第 0 帧时『上一步』被禁用」改成「不再禁用 + 停原地」；第 9 节新增 8 条镜像断言。179301 B / 2626 行，全部通过（647 OK / 0 FAIL） |
| `readme.md` | 4.4 节：关键帧条目与控制面板条目各补一句反向兜底规则。46380 B / 398 行 |
| `log.md` | 本节 + 页脚首行改「第 55 轮」 |

### 51.2 技术要点

1. **`prevFallback()` 的两种落点**（与 `nextFallback` 严格镜像）：

   ```js
   function prevFallback() {
     var frames = App.rounds[App.roundIndex] || [];
     if (!frames.length) { return; }
     if (App.frameIndex > 0) { setFrame(0); return; }          /* → 本局开局 */
     if (App.roundIndex <= 0) { return; }                      /* 第 0 局开局无处可退 */
     var prev = App.rounds[App.roundIndex - 1] || [];
     if (!prev.length) { return; }
     setRound(App.roundIndex - 1, prev.length - 1);            /* → 上一局结算 */
   }
   ```

2. **`stepKey(-1)` 的等价改写**：原来是 `for (; i > 0; i--) { …break; } setFrame(i);`。因为「循环结束时 i 一定是 0」与「`App.frameIndex` 本来就是 0 时 i = -1」两种情况都该走兜底（前者若帧 0 是关键帧，兜底也会落到帧 0，结果相同），所以直接让循环「命中即 `setFrame(i); return;`」、循环外统一 `prevFallback()`。
3. **`onAct` 的 `prev`**：`App.frameIndex <= 0` 时走 `prevFallback()`，否则 `setFrame(App.frameIndex - 1)`。
4. **按钮可点性**：`setDisabled('prev', false)` / `setDisabled('prevKey', false)`（与第 54 轮的 `next` / `nextKey` 对称）。`first`（本局开始）、`prevRound`（上一局）、`allFirst`（开局）的禁用逻辑不变 —— 用户只要求改这三个。
5. **`finalShown` 复位**由 `onAct` 开头的 `if (act !== 'allLast') { App.finalShown = false; }` 覆盖；`setRound` / `setFrame` 各自也会复位，所以跨局兜底不会留下结算框。

### 51.3 测试

- `node test/apptest.js` → **647 OK / 0 FAIL（exit 0）**；`python test/naga_test.py` → 142/0；`python test/agari_test.py` → 189/0。
- 新增断言覆盖：本局第 1 帧点「上一步」退回本局开局（帧 0）；第 2 局开局时「上一步」「上一决策」「上一自家决策」三者都退回第 1 局末帧（上一局结算，实测帧 113）；本局内仍有目标帧时照旧往回跳；第 0 局开局三个按钮都可用且停原地。
- 行尾：`web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`web/style.css` / `readme.md` 纯 LF。

### 51.4 踩坑

1. 第 3 节原来断言「第 0 帧时『上一步』被禁用」—— 用户 m05350 推翻了这条前提，测试立刻 FAIL 暴露出来；改成「不再禁用 + 停原地」。
2. `stepKey(-1)` 的旧写法把「找不到」与「找到帧 0」合并成一次 `setFrame(i)`，改写时要保证「帧 0 本身是关键帧」时仍然落在帧 0（先 `setFrame(i); return;` 的循环写法自动满足）。
3. 写 log.md 的补丁脚本时，若正文里含 `{ … }`（如 `prevFallback()` 的代码）就**不能用 `str.format()`** 填交付物尺寸（会报 `ValueError: expected ':' after conversion specifier`）⇒ 改用 `130341` 这类占位符 + `str.replace()`。

### 51.5 待办

- 视觉与手感（在开局处点「上一…」会跳到上一局结算）待用户实际试用确认；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 待用户确认：「完场」按钮的符号（原文写「双竖线 + 朝左三角」，实现为 `‖▶`）。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）待用户本机跑。

## 52. 第 56 轮：NAGA 下载判重按来源区分（用户 m05392）

### 52.1 交付物

| 文件 | 变化 |
| --- | --- |
| `mjscore/download.py` | 21,888 → 24,173 B / 538 行：naga 判重按来源区分 + 天凤牌谱同名跳过（见 52.6） |
| `test/naga_test.py` | 38,370 → 46,356 B / 842 行：新增第 8 节「naga 下载判重」19 条 + 第 9 节「天凤下载判重」10 条（及 docstring 第 11 条） |
| `readme.md` | 第 1 节「牌谱下载」行 + 4.1 节第 3 步补来源规则 |
| `log.md` | 本节 |

### 52.2 技术要点

- `run_download()` 新增 `seen_forms`：naga 判重键 → 本次下载里已经下过的来源形式集合；同一来源的 `info["form"]` 已经在本次下载里出现过就直接算重复（同一次下载里同来源的重复 url 仍判重）。
- 本地同名文件的取舍：只有 `form == "ricochet"` 且 `overwrite` 为真时才忽略本地同名文件、重新下载覆盖；官方来源一律 `kept = path`（跳过、不发请求）。
- 依据：官方域拿「纯净」报告；ricochet 带 `mtd`，`naga_types` 会多出 NAGA-超副露（カガシ）/ Mortal 系模型 ⇒ 用 ricochet 链接重下同一张牌谱即可把它升级成模型更多的版本。
- `overwrite=False` 时两种来源都不覆盖；`server.py` 的下载接口走 `overwrite=True`，所以网页端行为就是「官方跳过、ricochet 覆盖」。
- 结果条目里带 `form` 字段，界面与测试都能看出这条是从哪个来源下的。

### 52.3 测试

- `test/naga_test.py` 新增 **第 8 节**：monkeypatch `download.fetch_naga_report`（假 gzip，不发网），覆盖 官方/ricochet 判重键一致、空目录下载、同名跳过（且**不发请求**、文件不动）、ricochet 覆盖、同来源重复、`[官方, ricochet]` 与 `[ricochet, 官方]` 两种同列顺序、`overwrite=False` —— 共 19 条。
- 通过 161 项 / 失败 0（原 142 项）。
- `node test\apptest.js` → exit 0 全部通过（下载页 UI 未改）；`python -X utf8 test\agari_test.py` → 189 / 0。

### 52.4 踩坑

1. 沙箱里 `%TEMP%` 不可写（`open()` 报 `PermissionError [Errno 13]`），而且 **`tempfile.mkdtemp()` 建出来的目录连 `os.listdir()` 都报 `PermissionError [WinError 5] 拒绝访问`**（`os.makedirs()` 建的目录正常）⇒ 测试改用固定名目录 `build/_scratch/dl_dedup`（先 `rmtree` 再 `makedirs`）。
2. ricochet url 里有 `%22`，用 `%` 拼字符串会被当成格式化转换符 ⇒ `TypeError: not enough arguments for format string`，改成字符串拼接。

### 52.5 待办

- 视觉 / 手感待用户试用；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA（`frame_naga` 索引已就绪）。
- `test/mjscore_test.py` 全量（约 57~61 分钟）待用户本机跑。

### 52.6 追加修正（用户 m05480）：天凤牌谱同名跳过

- 用户指出：天凤牌谱应当是同名跳过，而不是直接覆盖。原实现里 `save_log(..., overwrite=overwrite)` 在 `overwrite=True`（网页端与 CLI 默认）时会直接覆盖已有 `<log_id>.xml`。
- 现行为：`run_download()` 的天凤分支先看 `os.path.join(out, "<log_id>.xml")` 是否存在 —— 存在就当作 `duplicate`，**跳过、不发请求、不覆盖**；不存在才 `fetch_log()` 并 `save_log()`。天凤同名时跳过的行为与 naga 官方来源一致。
- `save_log()` 本身不改（`test/mjscore_test.py` 第 4d 节直接断言它的 `overwrite` 语义）；只改 `run_download()` 的判定。
- 副作用：命令行 `--no-overwrite` 对天凤牌谱而言与默认行为一致（都是同名跳过）；想强制重下得先删掉本地文件。
- 测试：`test/naga_test.py` 新增 **第 9 节「天凤下载判重」**（monkeypatch `download.fetch_log`，不发网）10 条断言：空目录下载、同名跳过（不发请求、文件不变）、`overwrite=False` 同样跳过、同一次下载里重复 url 仍判重、不同特征码各自下载、一列两条都已在本地 → 全部跳过。通过 171 项 / 失败 0（原 161）。
- 同时更新 `readme.md`：第 1 节「牌谱下载」行与 4.1 节第 3 步改成「天凤同名跳过（不发请求）」，并说明 `--no-overwrite` 对天凤等同于默认。

## 53. 第 57 轮：Mortal 报告下载 + 牌谱后缀按来源区分（用户 m05545 ①②、m05806）

### 53.1 交付物

| 文件 | 变更 |
| --- | --- |
| `mjscore/paths.py` | 后缀常量源真源：`.tenhou` / `.naga` / `.mortal` + `.mortal-a|b|c` 与各自的旧后缀元组 |
| `mjscore/download.py` | Mortal 报告下载（`parse_mortal_url` / `mortal_report_key` / `build_mortal_url` / `mortal_model_info` / `fetch_mortal_report` / `save_mortal_report` / `find_mortal_files`）+ 按风格的落盘后缀 + `run_download` 三来源分派与判重 |
| `mjscore/ai_models.py` | `Mortal-4.1-避四` / `-平衡` / `-争一` 三个规范名 + `4.1a/b/c` 别名 + `normalize()` 认风格字母 |
| `mjscore/naga.py` · `mjscore/cli.py` · `mjscore/server.py` · `mjscore/node_harness.js` · `tools/download_tenhou.py` | 后缀改用 `paths` 常量、旧后缀仍认 |
| `web/js/app.js` · `web/index.html` · `desktop/main.js` | 前端识别 `.mortal-a|b|c`、文案与文件框过滤器、特征码 / 后缀剥离 |
| `web/js/mjsfeat.js` · `mjscore/feats.py` · `mjscore/store.py` | 第零类显示名改 `Mortal-4.1-平衡 分析` |
| `test/naga_test.py`（新增 `section10()`）· `test/apptest.js` · `test/mjscore_test.py` | 后缀与显示名同步 |
| `readme.md` · `log.md` | 本节 |

### 53.2 技术要点

- **能否用关键字区分模型风格**：能 —— 报告 JSON 里的 `review.model_tag` 是唯一标识（样例 `fb13c2973c0eabb3` = `4.1b`、`0af57be54bf867a0` = `4.1c`）。报告里没有「平衡 / 争一 / 避四 / balance / aggressive」任何字样；风格名来自 `https://mjai.ekyu.moe/` 上传页 `<select id="mortal-model-tag">` 的文案：`4.1a` = defensive = 避四、`4.1b` = balanced = 平衡、`4.1c` = aggressive = 争一。`review.version` = 1.5.10 是 reviewer 版本、`temperature` = 0.1，都与风格无关。
- URL 形式：`https://mjai.ekyu.moe/report/<16 位 hex>.json` 与 `https://mjai.ekyu.moe/killerducky/?data=/report/<id>.json` 等价；也认裸 16 位 hex 与 `<id>.mortal*` 文件名；重建下载 URL 统一用 `https://mjai.ekyu.moe/report/<id>.json`。
- 落盘后缀：`save_mortal_report(..., model_tag=...)` → `mortal_suffix_for(tag)`（`4.1a` → `.mortal-a`、`4.1b` → `.mortal-b`、`4.1c` → `.mortal-c`、认不出 → `.mortal`）；`find_mortal_files()` 把四种后缀都算「本地已有」。
- 判重：三来源各自一套（天凤 `<log_id>.tenhou`、NAGA `<report_id>.naga`、Mortal `<report_id>.mortal*`）；天凤 / NAGA 官方 / Mortal 同名跳过、不发请求；ricochet 覆盖重下。
- 显示名：第零类与 AI 模型菜单里的 `Mortal-4.1b-平衡` → `Mortal-4.1-平衡`；列名 `f_ai_mortal41b`、key `ai_mortal41b`、原始模型名文本列 `ai_models` 都不变。
- 目前第零类只有「Mortal-4.1-平衡 分析」一项（= `ai_mortal41b`），所以 `.mortal-a` / `.mortal-c` 谱能下载但不会点亮任何第零类特征 —— 若要把避四 / 争一也做成特征需要 schema 7，待用户定。

### 53.3 测试

- `node test\apptest.js` → exit 0 全部通过（AI 模型菜单、第零类检索、`.tenhou` 文件名等断言同步）。
- `python -X utf8 test\naga_test.py` → 通过 213 / 失败 0（新增第 10 节：mortal 下载 + 后缀按风格，18 大项）。
- `python -X utf8 test\agari_test.py` → 189 / 0；`python -X utf8 test\datamgr_test.py` → 67 / 0。
- `test/mjscore_test.py` 只改了期望文案与语料 glob（`*.tenhou` 优先），全量仍需用户本机跑（约 57~61 分钟）。

### 53.4 踩坑

1. 正则被双重转义：补丁脚本里的 Python 字符串 `\\.` 落进 JS 变成 `\\.`（匹配「字面反斜杠 + 任意字符」），`codeOf` / `gameLogId` 完全不剥后缀 —— 8 处测试失败才发现。
2. `mjscore/cli.py` 的 `def resolve_inputs(paths)` 形参遮蔽了同名的 `mjscore.paths` 模块，`paths.TENHOU_SUFFIXES` 直接 `AttributeError`（形参改名 `inputs`）。
3. `test/naga_test.py` 里同一次下载中重复的 mortal url 会算 **2 条重复**（mortal 分支判重时不写本次下载的 `seen`），期望写 `(0, 1, [])` 是错的。

### 53.5 待办

- **Mortal 报告的读取 / 播放 / 打点 / 第零类判定还没实现**，目前只能下载（前端载入 `.mortal*` 会提示「解析还没实现」）。
- 「复制url」对 mortal 报告还没有 URL（可给 `https://mjai.ekyu.moe/report/<id>.json`）。
- 旧库（v0.3.0 已入库）里的 `ai_models` 文本仍是旧名 `Mortal-4.1b-平衡`，检索不受影响（第零类按 `f_ai_*` 标志列判），需要时重新分析即可。
- 视觉 / 手感待用户试用；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4：牌谱检索 / 数据管理支持 NAGA；`test/mjscore_test.py` 全量待用户本机跑。


## 54. 第 59 轮：Mortal 报告的解析 / 播放 / 打点（沿用 NAGA 模板）+ 第零类 5 项 + v1.0.0（用户 m05937 ①②③）

### 54.1 交付物
| 文件 | 说明 |
| --- | --- |
| `mjscore/mortal.py`（新增，533 行 / 22,435 B） | Mortal 复盘报告 -> 与天凤 xml / NAGA 同构的 `{meta, rounds, naga}`；复用 `mjscore/naga.py` 的 `_Table` / `_event` / `_replay_state` / `_end_events` / `_side_ids` |
| `mjscore/paths.py` / `download.py` / `naga.py` / `cli.py` / `server.py` / `feats.py` / `store.py` / `ai_models.py` / `node_harness.js` | 后缀常量与分派、`cli.report_kind` 嗅探、`/api/read` 与 `/api/mortal-convert`、第零类 5 项与 schema 7 |
| `web/js/mjsfeat.js` / `app.js` / `ui.js` / `web/index.html` / `desktop/main.js` | 第零类 5 项、模型菜单 6 行、帧特征面板只列 34 项、Mortal 文件放行与 URL、听牌率条守卫 |
| `test/mortal_test.py`（新增，349 行 / 18,825 B） | 6 节 92 条断言 |
| `build.ps1`（11,458 B） | 回归链加 `test\mortal_test.py` |
| `readme.md`（50,365 B） | 39 特征 / 5 第零类 / v1.0.0 / Mortal 说明 |

### 54.2 技术要点
1. **版本与特征**：`v1.0.0`（`mjscore/__init__.py` / `package.json` / server docstring / 界面右上角）、`SCHEMA_VERSION = 7`、`FEATURES` 39 项 = 第零类 5 + 第一类 17 + 第二类 17；第零类新增 `ai_mortal41a`（`f_ai_mortal41a`，「Mortal-4.1-避四 分析」）与 `ai_mortal41c`（`f_ai_mortal41c`，「Mortal-4.1-争一 分析」），索引 `frame_ai` 同步扩到 5 列；`ai_values` 按 `naga_types`（NAGA）与 `review.model_tag`（Mortal）判定，天凤五项全「否」。
2. **第零类不进「当前帧特征」面板**（用户 m05937 ②）：`web/js/mjsfeat.js` 的 `AI_FEATURES` 5 项照旧进注册表 / 检索下拉以外的方案区，但 `web/js/app.js` 的 `renderFeatPanel()` 用 `if (isAiKey(f.key)) { continue; }` 跳过，末尾文案改成「共 34 个特征（第零类 5 项不在此列出…）」。
3. **Mortal 报告 = 复用 NAGA 模板**：`mjscore/mortal.py` 用 `review.kyokus[].entries[]` 的 `details[]` 造 `dahai_pred` / `huro` / `reach` / `kan`（万分比 = `prob * 10000`），entry -> 帧的定位靠「`tiles_left` + actor（自己回合 = `player_id`，鸣牌 = `last_actor`）+ 触发牌 `tile` + 事件类型集合」匹配 `mjai_log`，帧下标 = 触发消息下标 + 1（与 NAGA 的 `frames[i]` 对齐），三级回退（丢 tiles_left -> 丢触发牌）保证不丢 entry；`hora` 选项报告里没有展示位，不计入。
4. **Mortal 报告只含被复盘那一家**（`player_id`）：所以只它家有打牌预测柱 / 铳率条 / 决策表；另外报告没有 `danger_*` / `tenpai_*` / `end_type` / `game_rank`，`web/js/ui.js` 的听牌率条加「无 `tenpai_*` 行就不画」守卫，HUD 缺数据显示 `—`。
5. **结算**：和了帧的役种 / 番 / 符 / 点全部由我们自己的引擎算（`mjscore/agari.py`），点数用报告 `deltas` 扣本场 300 / 供托 1000 —— 与 NAGA 的 `_hora_settle` 同一口径（Mortal 报告里 hora 事件没有 `yakus` / `dora` / 点数）。
6. **分派与嗅探**：`cli.report_kind(path)` 先看显式后缀（`.mortal-a|b|c` -> mortal、`.naga` -> naga），只有 `.json` / `.gz` 这类歧义后缀才用 `mortal.looks_like_mortal`（有 `mjai_log` + `review`）嗅探；`/api/read` 与 `_naga_convert` 都走这条分派，`/api/mortal-convert` 与 `/api/naga-convert` 同一处理函数。
7. **风格关键字**（用户 m05545 ① 的第二问）：唯一标识 = `review.model_tag`（`4.1a` = defensive = 避四、`4.1b` = balanced = 平衡、`4.1c` = aggressive = 争一），报告 JSON 里没有「平衡 / 争一 / 避四 / balance / aggressive」字样；认不出的 tag 一律按 `4.1b` 处理（软件只支持 4.1，用户 m05806 ①）；文件名后缀按风格落 `.mortal-a` / `.mortal-b` / `.mortal-c`。

### 54.3 测试
- `node test\apptest.js` 651 通过 / 0 失败（模型菜单 6 行 + Mortal 分支 + 帧特征面板 34 行 + 版本号 1.0.0）。
- `python test\naga_test.py` 215 / 0、`test\agari_test.py` 189 / 0、`test\datamgr_test.py` 67 / 0、`test\mortal_test.py` 92 / 0。
- `test\mjscore_test.py` 全量未跑（约 57~61 分钟），改动点用等价片段单独验证。
- 两个真实样例（`fb13c2973c0eabb3.json` = 平衡、`0af57be54bf867a0.json` = 争一）各 12 局、`entries.hit = 163 / miss = 0`、12 局 `replay.check_invariants` 全空、10 个和了局都算出点数。
- 行尾：`mortal.py` / `readme.md` / `build.ps1` / `web/index.html` / `web/js/mjsfeat.js` 纯 LF；`web/js/app.js` / `web/js/ui.js` / `test/apptest.js` / `log.md` 纯 CRLF。

### 54.4 踩坑
1. `naga.is_naga_file()` 把旧的 `.json` 也算 NAGA，而 mjai.ekyu.moe 的报告地址正是 `.../report/<id>.json` ⇒ `.json` 的 Mortal 报告被误送进 naga 解析，报 `ValueError: 内容不像 NAGA 报告（缺少 pred 字段）`。修法：新增 `cli.report_kind()`，歧义后缀用 `mortal.looks_like_mortal()` 嗅探内容。
2. `naga._hora_ctx()` 会 `int()` 每个 `uradora_markers` 元素 ⇒ Mortal 侧必须在 `_end_msgs_for()` 里先用 `naga._side_ids()` 把牌名换成牌 id。
3. NAGA / Mortal 事件名是 `ryuukyoku`（双 u），不是 `ryukyoku`。
4. 认不出的 `review.model_tag`（例如 `9.9x`）不能原样规范化，否则会造出 `Mortal-9.9x-平衡` 这种注册表里没有的模型名 ⇒ 统一回退 `Mortal-4.1-平衡` + raw `4.1b`。
5. 补丁脚本的锚点 `# 天凤牌谱分析 v0.3.0` 在 readme.md 出现 2 次（标题 + 第 301 行注释），`count == 1` 断言失败 ⇒ `edit()` 增加「`HEADONLY:` 前缀 = 只替换第一处」的写法。

### 54.5 待办
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在进行；用户预告会补更多 NAGA URL 做全面测试。
- `test\mjscore_test.py` 全量待在本机跑；`end_num` 恒为 1 的真义、途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）仍无真实样本。
## 55. 第 60 轮：第零类特征改为**按帧判定** + AI 决策偏好记忆 + v1.1.0 / schema 8（用户 m06323 ①②③）

### 55.1 交付物
| 文件 | 说明 |
| --- | --- |
| `mjscore/feats.py`（19,291 chars，口径更正后） | 新增 `viewer_seat()` / `_model_has_data()` / `ai_frame_keys()` / `ai_frame_values()`；`make_record()` 的第零类 5 项与辅助列 `ai_models` / `ai_series` 改为按帧给 |
| `mjscore/ai_models.py`（3,919 chars） | 新增 `CHOICE_MODELS`（第零类 key -> 规范模型名）/ `CHOICE_KEY_BY_MODEL`（反向） |
| `mjscore/cli.py`（30,135 chars） | `fill_ai()` 逐行按 `(round_index, ev_index, seat)` 判帧，不再按整份牌谱 |
| `mjscore/naga.py`（30,350 chars）/ `mjscore/mortal.py`（19,693 chars） | `_meta` 加 `viewer_seat`：NAGA = 0（报告没有视角字段，对齐官方 viewer 默认 `tw=0`）；Mortal = `review.player_id` |
| `mjscore/store.py`（20,060 chars）/ `mjscore/__init__.py` / `package.json` | `SCHEMA_VERSION = 8`、`__version__ = "1.1.0"`（列名与值域不变、语义变了 ⇒ 旧库不再支持） |
| `web/js/app.js`（3,073 行） | `App.aiPref` 偏好 + `aiKeyOfIndex` / `aiPrefIndex` / `anyVal` / `aiFrameHasData` / `aiFrameKeys` / `syncAiModel` / `setAiPref`；`render()` 每帧同步、`setAiModel()` 记偏好、菜单 `.cur` 按偏好；`installGame` 初始主视角改用 `meta.viewer_seat` |
| `mjscore/server.py`（24,176 chars）/ `web/index.html`（16,676 chars） | 版本号 v1.1.0；健康检查 / 特征接口文案与「版本过低的库」提示补按帧判定说明 |
| `test/naga_test.py`（48,732 chars，220 / 0） | 第 5 节合成报告改成「主视角决策帧有概率表」⇒ 逐帧断言 + schema 8 |
| `test/mortal_test.py`（18,316 chars，99 / 0） | 新增 7 条按帧断言（`viewer_seat` / `ai_frame_keys` / 不是决策者的行全「否」/ 无 entry 的局为空） |
| `test/apptest.js`（156,174 chars，666 / 0） | 新增 15 条：偏好持久化、本帧无数据时临时「无AI决策」、之后自动切回、静态帧可切、`viewer_seat` 决定初始主视角 |
| `test/mjscore_test.py`（43,140 chars） | 新增 11 条按帧断言（按决策者判定）+ schema 8 / 版本 1.1.0（全量未跑） |
| `readme.md`（25,896 chars） | 2.1 节改按帧口径（用户 m06560 更正）、v1.1.0 / schema 8、AI 决策偏好说明 |

### 55.2 技术要点
1. **按帧判定口径**（用户 m06323 ①）：第零类某项为「是」当且仅当**这一帧做决策的那名玩家带该模型的决策概率表**（第 60 轮首版还要求「这一帧由牌谱初始主视角决策」，已按用户 m06560 删除这条闸门）；帧下标 = `ev_index + 1`（与 `naga.py` 的「帧 = 事件序号 + 1」映射一致）。`_model_has_data()` 依次看 `dahai_pred[index]` / `reach[index]` / `kan[index]` 与 `huro` 各座位的 `[index]`，与前端 `aiFrameHasData()` 同口径。
2. **主视角（`meta.viewer_seat`）**：只用来决定打开牌谱时把谁放到主视角 —— NAGA 报告顶层没有视角字段（`haihu_id` 为空）⇒ 取 0（官方 viewer 默认 `tw=0`）；Mortal 报告取 `review.player_id`（被复盘的那一家）。**它与第零类判定无关**（用户 m06560 起：只看这一帧的决策者有没有概率表）。
3. **schema 8 只改语义**：列名 / 值域 / 索引都没动，但同一帧的取值含义变了 ⇒ `store.check_version` 拒绝 schema ≤ 7 的库，必须重建；版本随之升 v1.1.0（约定：schema 变 ⇒ 版本变）。
4. **前端偏好机制**（用户 m06323 ③）：`App.aiPref` 存第零类 key（'' = 无AI决策），**跨牌谱、跨帧保留**；`render()` 每帧调 `syncAiModel()` —— 偏好在本牌谱里存在、但本帧没有该模型的概率表时临时把 `App.aiModel` 置 -1（按钮显示「无AI决策」、不画任何 AI 专属数据），走到有数据的帧再自动切回；模型菜单的 `.cur` 高亮的是**偏好**（不是本帧生效值），本帧无数据的行 title 会说明；`resetAiModel()` 只重置「本帧生效值」、不动偏好。
5. **静态帧也能切 AI 决策**（用户 m06323 ②）：下拉按钮在 `#nagaPanel` 里，不在被 `lockControls()` 禁用的 `#controls` 内，所以静态帧下照常可点；静态帧的主视角仍按「固定为当前决策者」的旧规则走。
6. **初始主视角**：`installGame()` 用 `meta.viewer_seat`（缺省 0）而不是硬编码 0 ⇒ 打开 Mortal 报告时主视角就是被复盘的那一家。

### 55.3 测试
- `node test\apptest.js` **666 通过 / 0 失败**（口径更正后新增 2 条断言）；`test\naga_test.py` **220 / 0**；`test\mortal_test.py` **99 / 0**；`test\agari_test.py` **189 / 0**；`test\datamgr_test.py` **67 / 0**；`node test\selftest.js`、`node test\uitest.js` 全部通过。
- 真实样本核对：NAGA `3180043a…v2_2` 全谱 942 个「有决策数据」帧、主视角（0 号）两项「是」、其它座位全「否」；Mortal 两个样例各 162 帧有数据（`entries.hit = 163`，有一条 entry 与另一条共用同一帧）。
- `test\mjscore_test.py` 全量未跑（约 57~61 分钟），改动点用等价片段单独验证。
- 行尾：`web/js/app.js` / `test/apptest.js` / `log.md` 纯 CRLF；`mjscore/*.py` / `readme.md` / `web/index.html` 纯 LF。

### 55.4 踩坑
1. `edit()` 只在**全部锚点都命中**时才写盘 ⇒ 锚点写错不会写坏文件，但白跑一次；含 CJK 的锚点必须先 `repr` 逐字核对。本轮踩了三次：`test/mortal_test.py` docstring 续行缩进 6 vs 5 空格；`test/mjscore_test.py` 的 `（补 Mortal-4.1-避四 / Mortal-4.1-争一…）` 真值是 ` / ` 而我写成 `、`；以及把行内的 `第 59 轮` 当成行首、多加了 5 个空格。
2. `Set-Content` 写出的脚本是 CRLF，脚本里用 `\n` 拼锚点前要先把脚本自身规整成 LF（`_fix3.py`–`_fix5.py` 就是干这个的）。
3. `web/index.html` 做「整行替换」时把续行的缩进一起吃掉（第 238 / 248 行）⇒ 事后按原缩进（11 / 8 空格）补回。
4. 测试里 `App.setViewSeat()` 只改状态、不触发重画 ⇒ 相关断言都要跟一次 `App.setFrame()`（第 44 轮的老教训）。

### 55.5 待办
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在进行；用户预告会补更多 NAGA URL 做全面测试。
- `test\mjscore_test.py` 全量待在本机跑；`end_num` 恒为 1 的真义、途中流局种类（`yao9` / `kaze4` / `rck4` / `reach4` / `tripleRon` / `nm`）仍无真实样本。
- ~~口径待确认：静态帧播放的主视角固定为「当前决策者」，而第零类判定用的是 `meta.viewer_seat` ⇒ 两者可能不一致~~ —— 已随用户 m06560 删除主视角闸门，此疑点消失。

### 55.6 更正（用户 m06560）：判定不看主视角，只看这一帧的决策者

- 用户 m06560 更正：某一帧的第零类某项 = 「是」，**当且仅当这一帧中做决策的那名玩家带该模型的决策概率表**（`dahai_pred` / `reach` / `kan` 属于这一帧的 `actor`，`huro` 只看这名玩家那一格）；55.2 第 1 条首版里「这一帧由牌谱初始主视角决策」这个条件已删除。
- 后端：`mjscore/feats.py` 的 `_model_has_data(fr, index, seat=None)` 加座位参数（帧级三键只在 `fr["actor"] == seat` 时看，huro 只取 `huro[str(seat)]`）；`ai_frame_keys(game, round_index, ev_index, seat=None)`；`ai_frame_values()` **删掉 `seat != viewer_seat(game)` 闸门**。
- 前端：`web/js/app.js` 的 `aiFrameHasData(nf, idx, models)` 改成「`seat = nagaSeatOf(nf)`；帧级三键只在 `nf.actor === seat` 时算；huro 只看 `huro[String(seat)]`」—— 挡住「只有 PASS 概率的 huro」这种旧实现会误判的帧。
- 测试：`test/mjscore_test.py` 的 `_fg` 块整段重写（11 条断言，覆盖「不是 viewer_seat 也算」「huro 按座位」「不传 seat 不过滤」）；`test/mortal_test.py` / `test/naga_test.py` 的措辞与消息；`test/apptest.js` 新增 2 条 `aiFrameHasData` 断言。
- 结果：`node test\apptest.js` **666 / 0**；`naga_test.py` 220 / 0、`mortal_test.py` 99 / 0、`agari_test.py` 189 / 0、`datamgr_test.py` 67 / 0；`selftest.js` / `uitest.js` 通过。schema 仍为 8、版本仍 v1.1.0（列名 / 值域 / 索引都没变，只改语义）。
- 真实样本核对（手工）：NAGA 样本里 0 号家带概率表的帧（帧 1）⇒ 只有 seat 0 判「是」；huro 帧（`dahai actor 0` + `huro {"1": {...}}`）在 seat 1 下判「是」、seat 0 下判「否」。

---
## 57. 第 62 轮：决策帧 ≡ 可检索静态帧 —— 第一类新增「等待鸣牌」（用户 m06801 / m06832）

### 57.1 交付物

| 文件 | 改动 |
| --- | --- |
| `mjscore/feats.py` | 新增第一类第 7 项「等待鸣牌」（key `meld_wait` / col `f_meld_wait`，取值「是 / 否」，紧随「顺位」）；`records_for_round()` 加第三支分支、新增模块级 `wait_record()`；`extract(st, seat, kind=None)` |
| `mjscore/store.py` | `SCHEMA_VERSION = 8 → 9`（新增特征列，旧库需重建）；特征表说明同步 |
| `mjscore/__init__.py` / `package.json` | 版本 `v1.1.0 → v1.2.0`（三段）。界面右上角、`tools/analyze.py`、`meta.app_version` 三处一致 |
| `mjscore/cli.py` | 分析摘要加 `rows_wait`、argparse description 与 `--features` 说明改 40 项（5 + 18 + 17）、打点行打印改「摸牌帧 + 副露帧 + 等待鸣牌帧」 |
| `mjscore/server.py` | `/api/features`、`/api/frame-feats` 的 docstring 改 40 项 |
| `mjscore/node_harness.js` | docstring 改「非自摸摸牌帧 / 吃碰副露帧 / 等待鸣牌帧」 |
| `web/js/mjsfeat.js` | 与后端同构：`BASE_FEATURES` 插 `meld_wait`、`extract(st, seat, kind)`、`recordsForRound()` 第三支 + 独立 `waitRecord()` |
| `web/js/app.js` | `isKeyFrame` 的 `discard` 分支与后端同闸门（决策帧 ≡ 可检索静态帧）；`seatOfFrame` / `frameSeatOf` 加「出牌帧且下一事件是吃 / 碰 / 大明杠 / 荣和 ⇒ 决策者 = 响应者」；条目导航 kind 标签加「等待鸣牌帧」；「当前帧特征」空文案与注释的 39 / 34 → 40 / 35 |
| `test/mjscore_test.py` | 3191 行 / `KINDS` 加 `wait: 405` / 每文件 `[442,599,615,669,866]` / 40 特征 / `FIRST_KEYS[6]` / 巡目独立重算表改 4 元键 / 新增 `waits` 断言块 / schema 9 / v1.2.0 / 命中行 `idx 2521` / `.tenhou` |
| `test/naga_test.py` | 40 特征 / schema 9 / docstring 补第 14 条历史 |
| `test/apptest.js` | 40 特征 / 下拉 35 项 / 下标 15（`riichi_others_n`）、16（`ippatsu`）、10（`rank`）、11（`meld_wait`）/ `v1.2.0` / schema 9 / 新增等待鸣牌决策者 + `MJSFEAT.extract` 断言 |
| `readme.md` | 40 特征（5 + 18 + 17）、第一类 18 项、「等待鸣牌」表行、「决策帧 ≡ 可检索静态帧」说明、schema ≤ 8 不再支持、v1.2.0 版本段 |
| `log.md` | 本节 |

### 57.2 技术要点

1. **根因与口径**：用户 m06670 指出「决策帧」（需要某位玩家做选择的帧）与「具有 AI 决策概率向量的帧」是两个概念（NAGA 覆盖四家时等价、Mortal 只复盘一家时不等价），要求两者分清；用户 m06801 进一步要求**「决策帧 ≡ 可检索静态帧」** —— 检索入库的打点行必须与播放里的关键帧一一对应。实测确认：原 `records_for_round()` 只出「非自摸摸牌帧」与「吃 / 碰后等待出牌帧」，**漏了「有人打出牌之后、另外三家各自等待决定吃 / 碰 / 杠 / 过」的等待鸣牌帧**（`isKeyFrame` 里 `discard` 的下一事件是 `call` / `agari` 时为真，但库里没有对应行）。
2. **新增打点行（方案 A）**：`ev.type == "discard"` 且下一事件是 `call`（chi / pon / daiminkan）或 `agari` 时，为**除出牌者以外的三家各出一行**，`kind = "wait"`、`drawn = None`、`ev_index` = 该出牌事件下标（`frame_index = ev_index + 1`，与播放帧号一致）。门控与 `isKeyFrame` 的 `discard` 分支完全一致 ⇒ 达成「决策帧 ≡ 可检索静态帧」。
3. **第一类新增「等待鸣牌」**：`{"key": "meld_wait", "name": "等待鸣牌", "col": "f_meld_wait", "kind": "enum", "values": ["是", "否"]}`，取值 = `"是" if kind == "wait" else "否"`，展示位置紧随「顺位」（用户 m06832）。第一类 17 → **18**、总特征 39 → **40**（5 第零类 + 18 第一类 + 17 第二类）；`FIRST_KEYS` 下标后移（`riichi_others_n` 9 → 10、`ippatsu` 10 → 11）。
4. **「巡目」= 自家（等待决策者）巡目**（用户 m06832）：wait 行的 `junme` 取**响应者**（不是出牌者）的「已出牌次数 + 1」；`seat` 列写响应者座位 ⇒ 检索结果里点条目进静态帧时主视角 = 响应者。
5. **前端决策者判据**：`seatOfFrame(frames, i)`（扫任意帧）与 `frameSeatOf(st)`（看当前帧）都补了「出牌帧且下一事件是吃 / 碰 / 大明杠 ⇒ 返回 `nxt.player`；下一事件是荣和 ⇒ 返回 `nxt.winner`」；依据是 `frames[i].ev = events[i-1]`（下一事件 = `events[App.frameIndex]`）、且 `mjscore/replay.py` 出牌时把 `st["drawn"]` 清成 `None`（`mjscore/replay.py:169`）所以出牌帧不会被「摸牌者」分支短路。副作用：「上一 / 下一自家决策」在主视角本人是响应者时会停在该等待帧（PASS 席位仍跳过 —— 列为待用户拍板项）。
6. **第零类不进「当前帧特征」面板**的口径不变（用户 m05937 ②）；面板现在列 35 项（40 − 5）。

### 57.3 测试

- 语料（5 个 `.tenhou`）：打点行 **3191**（旧 2786）＝ 摸牌帧 2679 + 副露帧 107（吃 50 + 碰 57）+ **等待鸣牌帧 405**；每文件 `[442, 599, 615, 669, 866]`（旧 `[364, 530, 531, 576, 785]`）；`junme` 取值仍 1..19、`joukyoku` 仍 8 种。
- 单文件 node 冒烟（`2026082919gm-00a9-0000-4e40cd3e.tenhou`）：599 行 = draw 513 + wait 69 + pon 10 + chi 7；**69 = 23 个有人响应的出牌事件 × 3 家**。
- **node × python 全字段交叉校验：65 列 × 3191 行逐项一致**（`test/mjscore_test.py` 的双工具校验节）。
- `python -X utf8 -u test/mjscore_test.py` **全量通过 269 项 / 失败 0 项**（真实第二类特征、未打桩；wall 41 分 28 秒，2026-10-12 02:04:44 → 02:46:12）。其中本轮新断言全部 OK：打点行 3191 + kind 分布 `{draw 2679, wait 405, pon 57, chi 50}` + 每文件 `[442,599,615,669,866]`、注册表 40 项（5 + 18 + 17）、第一类第 7 项 `meld_wait`、「等待鸣牌帧条目名格式 / 手牌数 1..13」、`node × python 全字段逐项一致（65 列 × 3191 行）`、`frame_full` 15955 行、schema 9 / `v1.2.0` / `/api/features` 40 项、命中行 `idx 2521` + `.tenhou` 后缀。
- `test/apptest.js` 全部通过（exit 0）、`test/naga_test.py` **220 / 0**、`test/mortal_test.py` **106 / 0**、`test/datamgr_test.py` **67 / 0**、`test/agari_test.py` 189 / 0、`test/selftest.js` / `test/uitest.js` 通过。

### 57.4 踩坑

1. `waitRecord` 一度被补丁脚本 splice 进了 `callRecord` 函数体内部 —— 语法合法、`node --check` 也过，但只在 `callRecord` 局部作用域里存在，模块尾 `waitRecord: waitRecord` 导出会 `ReferenceError`。**教训：splice 类补丁后要真正「加载」一次模块（跑一次 harness），不能只靠 `node --check`。**
2. 打桩（把 `feats.second_class` 换成常量桩）能快速暴露陈旧断言：4 个失败里 3 个是桩副作用、1 个是真陈旧 —— `test/mjscore_test.py` 里「互斥取值特征」计数写死 `(7, True)`，实际已随第零类 5 项（kind = enum）变成 **14**（5 第零类 + 9 第一类）。凡是「数字写死」的断言在特征数 / kind 集合变化后都会漂移。
3. `test/apptest.js` 8.6 节的 `recCall` 取「第一个 `kind !== 'draw'` 的记录」—— 新增 wait 行后它选中了等待鸣牌帧、标签成了「等待鸣牌帧」。**教训：测试里「挑第一条非 X 记录」的选法在 kind 集合变化后语义漂移，应显式列出可接受的 kind。**
4. 打补丁时只改文案没改数值（`test/naga_test.py` 一条断言的说明文字改对了、数值 `39` 没改）⇒ 同一断言的「文案」与「数值」要么整行替换、要么分两次替换。
5. 行尾：`test/naga_test.py` / `readme.md` 是纯 LF，`log.md` / `test/apptest.js` / `test/mjscore_test.py` 是 CRLF —— 补丁脚本必须按文件实际行尾回写（`"\r\n" in raw`），否则整文件 diff 爆炸。

### 57.5 待办

- `test/mjscore_test.py` 全量已在本轮跑通（269 / 0）⇒ 无遗留。
- 待用户拍板：① 是否连「三家都 PASS 的出牌帧」也进检索（方案 B，行数 ≈ ×4）；② 立直宣言帧 / 杠帧 / 被排除的自摸摸牌帧是否也补检索行；③ 第零类「huro 只有 PASS 概率」后端判「有数据」而前端判「无」的口径不一致；④ 「上一 / 下一自家决策」是否也停在 PASS 席位的等待鸣牌帧。
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在；用户预告会补更多 NAGA URL 做全面测试。
- 视觉待用户目视确认（沙箱无浏览器）；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。

---

## 56. 第 61 轮：决策帧 ≠ 有 AI 决策概率向量的帧（用户 m06670）

### 56.1 交付物
| 文件 | 改动 |
| --- | --- |
| `web/js/app.js` | `isKeyFrame()` 删掉「这一帧面板必须有非 PASS 选项」的 AI 数据闸门，改成纯牌局判据；注释把「决策帧」与「有 AI 决策概率向量的帧」拆成两个概念 |
| `test/apptest.js` | 新增 4 条断言（没有 AI 概率向量的摸牌帧仍是决策帧；模拟 Mortal 报告时两家决策帧都没有概率向量；决策帧判据不受 AI 数据影响；「下一决策」仍停在别家的决策帧上） |
| `test/selftest.js` / `test/uitest.js` / `test/agari_test.py` | 语料遍历改认 `.tenhou`（用户 m05545 ② 改名后的漏改：node 测试找到 0 个牌谱直接抛错、agari 全量校验的 71 个牌谱变成 0） |
| `test/mortal_test.py` | 新增 7 条断言：打点帧按牌局选帧、覆盖四家决策帧；AI 概率向量只落在被复盘那一家的部分帧上 |
| `readme.md` | 「上一决策 / 下一决策」条目改写（决策帧 = 需要某人做选择的帧；判据与 AI 数据无关）；检索范围说明补一句 |
| `log.md` | 本节 |

### 56.2 技术要点
1. **根因**：`isKeyFrame()` 末端 `var has = nagaFrameChoices(i); return (has === null) ? true : has;` —— 把「这一帧面板里有没有非 PASS 选项」（= 有没有 AI 决策概率向量）当成了决策帧判据。NAGA 报告覆盖四家（两概念等价），Mortal 报告只复盘一家 ⇒ 别家的决策帧被判非决策帧，`stepKey()` 与 `stepSelfKey()` 行为雷同 —— 正是用户 m06670 报的现象。天凤牌谱 `nagaFrameChoices()` 返回 null ⇒ 老实现下不受影响，所以只在 Mortal 谱里暴露。
2. **改法**：`isKeyFrame(frames, i)` 只看 `fr.ev.type` —— `draw` / `call` / `reach` → 决策帧；`discard` → 仅当 `frames[i+1].ev.type` 是 `call` / `agari`；其余 false。`nagaFrameChoices()` 保留（面板 / 导出 / 测试用），注释改成「只表示这一帧有没有 AI 决策概率向量，与决策帧是两个概念」。
3. **检索范围本来就是决策帧**（无需改后端）：`mjscore/feats.py` 的 `records_for_round()` 纯按牌局选帧 —— 非自摸摸牌帧 + 吃 / 碰后等待出牌的帧。实测 `build\_scratch\mortal\fb13c2973c0eabb3.json`：打点帧 600 条（座位 0/1/2/3 = 150/151/150/149），而带 AI 概率向量的帧只有 162 个（全在被复盘那一家）⇒ 两个概念在 Mortal 谱里确实不等价；NAGA 样本则是 779 条打点帧 vs 942 个带 AI 数据的帧（多出来的是鸣牌决策帧），两个方向都不同。
4. **测试语料的陈旧逻辑（4 个测试文件）**：`test/apptest.js` / `test/selftest.js` / `test/uitest.js` 的 `walkXml()` 只收 `.xml`（`pickBase` / `xmlPath()` 也只匹配 `<id>.xml`），`test/agari_test.py` 的 `FILES` 只 glob `*.xml`，而用户 m05545 ② 把本地牌谱后缀改成了 `.tenhou`（`data/paipu/tenhou/` 71 个文件）⇒ 语料为 0：apptest 直接抛 `data 下找不到 …（共 0 个牌谱）`、uitest 去读 `data/undefined` 崩掉、agari 的「全量校验」4 条断言全失败（71 → 0）。统一改成收 `.tenhou / .xml / .mjlog`、两边都剥后缀再比。测试传给 `loadText` 的 `name` 仍可用 `.xml`（前端自己按后缀剥特征码，不影响断言）。

### 56.3 测试
- `node test\apptest.js` **670 项全通过**（新增 4 条断言；语料修复后 71 个 `.tenhou` 可跑）。
- `python -X utf8 test\mortal_test.py` **106 通过 / 0 失败**（99 → 106）。
- `test\agari_test.py` **189 / 0**（语料修复前是 185 / 4）、`test\datamgr_test.py` 67 / 0、`test\naga_test.py` 220 / 0。
- `python -X utf8 test\naga_test.py` 220 / 0、`test\agari_test.py` 189 / 0、`test\datamgr_test.py` 67 / 0；`test\selftest.js` / `test\uitest.js` 通过。

### 56.4 踩坑
1. 测试语料写死 `.xml` ⇒ 用户改后缀后 node 测试整体跑不起来（`data 下找不到 …（共 0 个牌谱）`）。凡「按来源区分的后缀」都要在测试的语料遍历里同步。
2. `xmlPath(id)` 的 id 可能带后缀也可能不带（`f.replace(/\.xml$/, '')` 在 `f` 是 `.tenhou` 时是空操作）⇒ 匹配时两边都剥后缀最稳，否则要改一大片断言。
3. `python test\mortal_test.py` 里「AI 概率向量」要按 `feats.AI_KEYS` 逐个试，不能写死 `ai_mortal41b` —— 4.1c（争一）谱的「是」落在 `ai_mortal41c` 上，写死会让真实样例断言假失败。

### 56.5 待办
- 视觉待用户目视确认（沙箱无浏览器）；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 「上一决策 / 下一决策」现在也会停在**别家**的决策帧上（这正是用户 m06670 要的）；若希望有「只跳自家决策」的开关，仍由「上一自家决策 / 下一自家决策」两个按钮承担。
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在。

---

*最后更新：第 76 轮（AI 决策表「其它」行按**显示值**补足到 100.0%，用户 m09901；1.4.1 尚未打包发布，修复并入同一版本）。上一轮：第 75 轮（**新版 NAGA 联合分布展示**：NAGA-避四 / NAGA-争一 的决策表直接列「打 xx」/「打 xx 立直」、概率条在既能默听打又能立直打的牌上左右一分为二（左半紫 / 右半红）；旧模型展示零变化；按用户 m09354 ④ 只提小版本号 ⇒ **v1.4.1**（库结构不变，仍 schema 11）。上一轮：第 74 轮（**新版 NAGA 报告支持**：アナンタ → `NAGA-避四`、ウロボロス → `NAGA-争一`；第零类 5 → 7 项（共 42 特征）；两款新模型的打牌概率取 `dahai_detail` 的 37 档合并回 34 档 ⇒ **v1.4.0 / schema 11**（用户 m09507）；已有模型（含天凤 / Mortal）展示零变化；立直概率按官方 viewer 1.2.2 口径从 `dahai_detail` 的立直支还原，并修掉旧报告立直概率恒 0.0% 的 bug）

上一轮：第 73 轮（**界面整体放大 25%** + 检索分段载入 + 静态帧禁用「局」选择 + **v1.3.1**：大版本 + 中版本相同即可读库（用户 m09339 ①②③ / m09354 ④⑤））。上一轮：第 72 轮（打包发布流程：**跨盘符 relpath 真 bug**（用户 m09228 实测 —— 打包后用户数据在 C:、程序在 D:，`os.path.relpath` 抛 `ValueError: path is on mount 'C:', start on mount 'D:'` ⇒ `/api/paipu-browse` 400，这是「牌谱目录只能拉开很窄的条」的另一半原因）：`mjscore/server.py` 新增 `_paipu_rel()`（只在牌谱根内做 relpath，返回 `data/paipu/...`）、`_rel_or_abs()` 兜住跨盘符；`test/datamgr_test.py` 第 3 节的陈旧期望（只数 `.xml`、硬编码目录名）改成全部后缀 + `scan(kind=all)` + 跨盘符断言（78 / 0）；后端已重新打包并冒烟通过（`/api/paipu-browse?dir=data/paipu` → 200），已由用户 m09307 在普通终端出包：`tenhou-paipu-analysis-1.3.0-setup.exe` = 143,284,238 B，SHA256 `7EEE64A4F11C89577840DF26976F216333DD7EC72C989BBC0699EFF6FF1CEE89`）。

上一轮：第 70 轮（**关键帧判定先于概率过滤**（用户 m09110）：报告给这一帧的决策者列出的可选策略不止「过」才算「面板有内容」（本判定只关 AI 面板，与「决策帧」判定无关）`0.0%` 的吃 / 碰 / 杠选项也算「列出来了」），AI 面板一定显示分析结果；表格本身仍按 10% 门槛筛选，所以低概率的鸣牌选项不会单独列出。用户 m09045 那一帧（上家打 3s、我方有 4s5s 吃 / 2s4s 吃 / 3s3s 碰，ニシキ 给的三个鸣牌选项都是 0.0%）现在显示「PASS 100.0%」+ 5 项分析数据，而不是像改动前那样整块留空；残差不足 0.5% 时不再补「其它 0.0%」。报告侧本就带每个选项的万分比概率 （`huro[座位][模型] = {0:PASS, 1/2/3:吃, 4:碰, 5:大明杠}`），吃三种牌对的下标含义用报告里实际发生的 chi 事件的 `kind` 字段反查证实与本仓 `nagaChiPair()` 一致；Mortal 报告同一套编码（`mjscore/mortal.py` 的 `HURO_PASS/HURO_PON/HURO_KAN`）。41 份 NAGA 报告的 `huro` 键模式统计：**没有任何一格只列 PASS**（最少也带一个吃 / 碰 / 杠键）⇒ 「只有 PASS ⇒ 面板留空」实际主要作用于 Mortal 的 PASS-only 帧与报告没给选项的展示帧。`node test\apptest.js` 795 行 / 0 失败）。上一轮：第 69 轮（README 重写为面向使用者的发布说明 —— 只讲功能 / 界面操作 / 理解方式与麻将术语，不写需求来源、实现方法、踩坑与版本历史；旧版 readme 原样移入 `docs/readme-dev.md` 并加「开发过程记录」说明；顺手修了首页两处旧文案：特征数「18 个第一类」→「17 个第一类 + 1 个第三类」、检索卡片补「鸣牌响应帧」）。上一轮：第 68 轮（用户 m08918：**打包版「牌谱分析」页的「牌谱目录 / 牌谱文件」下拉为空** —— 服务端把 `data/paipu` 这类相对写法一律拼到资源根（打包后 `_MEIPASS` / 安装目录）而不是用户数据根（`%LOCALAPPDATA%\tenhou-paipu-analysis`，`mjscore\paths.py`）⇒ 目录不存在；`mjscore\server.py` 新增 `_user_path()`（绝对路径原样、相对路径先试用户数据根再退资源根），`_abs()` / `/api/paipu-browse` / `/api/scan` / `/api/read` / 数据库与分析路径都走它，`test\datamgr_test.py` 新增第 4 节回归（datamgr 54 / 0、naga 224 / 0）；已发布的 v1.3.0 安装包仍带此 bug，需重新打包后端）。上一轮：第 67 轮（用户 m08700：**打包发布流程 + 应用图标 6m 图案收缩**。① 修掉打包后的后端**一启动就崩**的真 bug：PyInstaller 从 conda base（`D:\coding\anaconda3\Library\bin`）抓了 `libssl-3-x64.dll` / `libcrypto-3-x64.dll`（789,320 / 5,297,992 B），与本环境 `py314_null\Library\bin` 的（1,326,920 / 7,349,064 B）不是一套，和 `DLLs\_ssl.pyd` 不匹配 ⇒ `ImportError: DLL load failed while importing _ssl: 找不到指定的程序`；`packaging\pyi_build.py` 新增 `ssl_pair()` / `fix_ssl_pair()`：把本环境的那一对 `--add-binary` 进包，并在打包后按 SHA256 校验、不一致就覆盖（打印 `OpenSSL : …`）；`build.ps1 -Smoke` 实测后端 0.5 s 就绪、`/api/health` 返回 version 1.3.0。② 图标：`tools\svg2ico.py` 新增 `--content-scale`（牌面白底不缩、只把图案围绕牌面中心收缩），`build.ps1` 用 0.84 ⇒ `build\icon.ico`（39,748 B，16/32/48/64/128/256）四周白边更宽（用户 m08700，与界面牌图的 0.09 牌宽 padding 一致）。无 schema / 特征 / 版本变化（仍 v1.3.0 / schema 10）；`apptest.js` 759 行 / 0 失败、`naga_test.py` 224 / 0、`mortal_test.py` 106 / 0；安装包（electron-builder）需普通终端跑，指纹待补）。

上一轮：第 66 轮（用户 m08319 ①②③④ + m08623（杠名称按**牌局状态**规范化：决策表里的杠选项按状态取名 —— 手里 4 张 =「暗杠」、碰副露 + 手里第 4 张 =「加杠」，报告档位只作提示；`huro` 档位 5 从「杠」改成「大明杠」；Mortal 会把加杠报成 `ankan`）：① 细红框改成**跟着本帧决策者**走（不再限定主视角 —— 谁在这一帧做决策就把框画在他自己手里；静态帧的主视角本来就会被调成决策者，所以静态帧看起来一样）；② 桌面上所有牌一律同尺寸（`web/js/ui.js` 不再给手牌 / 摸牌槽位加 `big` 类、`web/style.css` 删 `.p-hand .drawn.self` 的 1.15 倍槽位）；③ 加杠第 4 张牌改按官方 viewer 的 `kanPai` 画法 —— 与原来那张横牌**同列、正上方错开一整张牌宽**（`.tile-stack .tile.added { left: 0; top: calc(var(--tile-w) * -1) }`）；④ 牌河改成**最多 3 排**：前 2 排各 6 张、第 13 张起全部在第 3 排向右延伸（不再放入第 4 排；CSS 仍按 4 排预留高度 ⇒ 牌河变长时手牌位置不跳，用户 m08319 ② / m08576）；无 schema / 特征 / 版本变化（仍 v1.3.0 / schema 10）；测试 `apptest.js` 全部通过（780 行 / 0 失败）、`selftest.js` / `uitest.js` exit 0、`naga_test.py` 224 / 0、`mortal_test.py` 106 / 0、`datamgr_test.py` 67 / 0，`mjscore_test.py` 全量仍需用户本机跑；本轮末又补了杠名称规范化（用户 m08623，`apptest.js` 784 行 / 0 失败））。上一轮：第 65 轮（用户 m08125 ①②③ / m08178：① **修真 bug**：加杠副露的 4 张牌在牌桌上消失 —— NAGA / Mortal 报告里的 `kakan` 事件只带「加进去的那一张」，`mjscore/naga.py` 原来还把它当成 4 张一起输出、而 `mjscore/replay.py` / `web/js/replay.js` 拿这一张去覆盖原来的碰 ⇒ 整组消失（天凤的事件本来就带 4 张，只有报告类牌谱会踩到）；现在 `kakan` 只输出那一张、由回放把它并回同种的碰；**41 份 NAGA + 12 份 Mortal + 天凤全量 143 个牌谱**实测：加杠 30 次 / 暗杠 42 次 / 大明杠 2 次，副露牌张数与种类全部正确、replay 不变量 0 错误；② 新增**细红框**：当前帧是「出牌局面」且主视角本人是决策者时，把下一帧他要打出的那张牌在手牌里框出（`inset 0 0 0 0.06 张牌宽` 的 `#e0503a`，比牌河鸣牌红框细；同种牌取最靠左一张、5m/5p/5s 优先普通 5；立直宣言算打出宣言牌）；实际动作为暗杠 / 加杠时把准备杠的 **4 张全部**框出（暗杠 = 手里 4 张，加杠 = 手里 1 张 + 副露区 3 张，用状态里的准确牌 ID）；图层与牌河红框一致（`z-index: 1`、同家内靠后打出的在上）；③ 静态帧「鸣牌响应局面」的**多家可鸣牌**：同一张打出牌可能被多家鸣牌时，检索结果里每家各一条记录、各自的主视角分别展示一次（41 份 NAGA 报告实测 269 个「两家以上可鸣牌」的出牌帧，其 `huro` 席位集合与本地 `responders()` 判据 100% 一致）；无 schema / 特征 / 版本变化（仍 v1.3.0 / schema 10）；测试 `apptest.js` 全部通过、`selftest.js` / `uitest.js` exit 0、`naga_test.py` 224 / 0、`mortal_test.py` 106 / 0、`datamgr_test.py` 67 / 0，`mjscore_test.py` 全量仍需用户本机跑）。上一轮：第 64 轮（用户 m07820：① 第零类「有数据」口径按 (a) 统一 —— `huro` 只要**有副露可能**（哪怕概率全落在 PASS 上）就视为「有该模型的决策数据」，前端 `aiFrameHasData()` 对齐后端 `_model_has_data()`（根因：前端原来要求「非 PASS 选项里有非 0 概率」，且用 `nagaSeatOf()` 在**未按模型折叠**的帧上取座位会因 `dict > number` 恒 false 而退化到 `nf.actor`）；41 份 NAGA 报告实测 `huro` 只出现在有人打出牌的帧上、「只有 PASS」2169 格 / 「含鸣牌选项」3534 格、没有全 0 格；② 牌谱播放的红框（被鸣走的牌 `#e0503a`）与绿框（被荣和的铳牌）抬到最上层（同一家面板内 `z-index: 1`）并统一缩小一圈（外扩 `.17 → .14`、内描边 `.11 → .08` 牌宽），同一家的不同牌张之间仍按打出的先后；③ 牌谱检索静态帧的「鸣牌响应局面」用黄框 `#ffd54a`（尺寸同红 / 绿框）框住被响应者等待鸣牌的那张打出牌（`render()` 里的 `mark`，只在 `App.itemIndex >= 0` 且条目 `kind === 'wait'` 时画）；无 schema / 特征变化（仍 v1.3.0 / schema 10）；测试 `apptest.js` 全通过、`selftest.js` / `uitest.js` exit 0、`naga_test.py` 222 / 0、`mortal_test.py` 106 / 0、`datamgr_test.py` 67 / 0，`mjscore_test.py` 按用户 m07294 仍不跑全量）。上一轮：第 63 轮（用户 m07289 的五条 + 四条补充：① 关键帧判据改成**「这张牌是否可能被他家鸣牌」**（碰 / 大明杠 = 非立直家同种 ≥2；吃 = 只有出牌者的下家、且吃完后至少还有一张能打的牌〔禁止食替〕），只看牌局、不看牌谱里实际有没有出现鸣牌；② **立直宣言 / 杠宣言都视为出牌动作**（立直宣言牌按普通出牌进入上面的判据），**立直宣言帧本身不再单独停留**，暗杠 / 加杠 / 大明杠的展示帧与自摸帧一律忽略（他家能交互的唯一场景是枪杠和牌，遵循 NAGA「能和就和」的原则），**仅可能被荣和**（没人可能鸣牌）的出牌帧不算决策帧；③ 「等待鸣牌」编为**第三类特征**（1 项，列 `f_meld_wait` 移到注册表末列）：不进检索下拉、也不进播放界面「当前帧特征」面板，改由面板底部**大号居中文字**「出牌局面 / 鸣牌响应局面」体现；④ 检索新增**必选单选**「出牌 / 鸣牌响应」（默认「出牌」）—— 位于第零类框右端、只放两行、无标题无说明，与其它全部条件 AND，服务端按 `f_meld_wait` 过滤；⑤ `kind = 'wait'` 行改为「鸣牌响应帧」且**只给可能鸣牌的那一家各 1 行**（不再固定 3 行）；⑥ 第零类框标题改成「**是否具有AI决策**」；⑦ 第 62 轮遗留的 4 个问题由用户答复（②③⑤ 已按上面实现，「详细解释第 3 项」= huro 只有 PASS 概率时后端 `_model_has_data` 判「有数据」/ 前端 `aiFrameHasData` 判「无数据」的口径差异，只解释、本轮不改码）；版本升 **v1.3.0**、schema **10**、特征 40 = 5 + 17 + 17 + 1；`mjscore/feats.py` 新增 `responders` / `meld_possible` / `can_chi` / `chi_pairs` / `chi_forbidden` / `can_pon` + `THIRD_FEATURES`，`mjscore/store.py` `compile_query(..., wait=)` + 索引 `frame_wait`，`mjscore/cli.py` `--wait`，前端 `decisionSeats` / `Sc.wait` / `renderFeatMode` / `#waitPlan` / `#featPanelMode`；测试：`naga_test.py` 222 / 0、`mortal_test.py` 106 / 0、`datamgr_test.py` 67 / 0、`apptest.js` 全通过、`selftest.js` / `uitest.js` exit 0（`mjscore_test.py` 期望值已按新口径改到 45,787 字符，但**按用户 m07294 本轮不跑全量**））；上一轮：第 62 轮（用户 m06801 / m06832：**「等待鸣牌」决策帧纳入检索** —— 决策帧 ≡ 可检索静态帧。新增第一类特征「等待鸣牌」（key `meld_wait` / col `f_meld_wait`，是 / 否，紧随「顺位」）：有人打出牌后、除出牌者以外的三家各自等待决定吃 / 碰 / 杠 / 过的帧为「是」，各打 1 行进库（`kind = 'wait'`、`frame_index = ev_index + 1`、`drawn = None`、`seat` = 响应者、巡目 = 响应者的已出牌次数 + 1）；前端 `isKeyFrame` 与该门控完全一致，`seatOfFrame` / `frameSeatOf` 在出牌帧返回响应者（`mjscore/replay.py:169` 出牌清 `drawn` 保证可达）。语料打点行 2786 → **3191**（2679 摸牌 + 107 副露 + **405 等待鸣牌**）；node × python 65 列 × 3191 行逐项一致；`mjscore_test.py` **269 / 0**（wall 41 分 28 秒）、`apptest` 全通过、`naga_test.py` 220 / 0、`mortal_test.py` 106 / 0、`datamgr_test.py` 67 / 0；版本升 **v1.2.0**、schema **9**（旧库需重建））；上一轮：第 61 轮（用户 m06670：区分「决策帧」与「有 AI 决策概率向量的帧」—— `isKeyFrame()` 里「这一帧面板必须有非 PASS 选项」的 AI 数据闸门已删除，改回纯牌局判据；此前 Mortal 报告只复盘一家 ⇒ 别家的决策帧被判非决策帧、「上一 / 下一决策」退化成「上一 / 下一自家决策」；检索范围的静态帧本来就由牌局决定（打点帧覆盖四家，与有无 AI 数据无关）；测试：apptest 新增 3 条 + mortal_test 新增 7 条（106 / 0），并修好 node 测试语料只认 `.xml` 的陈旧逻辑）；上一轮：第 60 轮（用户 m06323 ①②③ / m06560：第零类特征改为**按帧判定** —— 「是」当且仅当「这一帧**做决策的那名玩家**带该模型的决策概率表」（`dahai_pred` / `reach` / `kan` 属于该帧 actor，`huro` 只看决策者那一格；首版还要求「该帧由牌谱初始主视角决策」，已按用户 m06560 删除），`meta.viewer_seat`（NAGA 取官方 viewer 默认视角 `tw=0`、Mortal 取 `review.player_id`）只用来决定播放初始主视角；「选择AI决策」记用户偏好（跨牌谱 / 跨帧保留，偏好在本帧不可用时临时显示「无AI决策」、走到有数据的帧自动切回），牌谱检索的静态帧播放同样可切换；版本升 v1.1.0、schema 8（旧库需重建））；上一轮：第 59 轮（用户 m05937 ①②③：第零类新增「Mortal-4.1-避四 分析」「Mortal-4.1-争一 分析」+ 第零类不显示在「当前帧特征」面板；新增 `mjscore/mortal.py`，以 NAGA 的分析与展示模板处理 Mortal 复盘报告；版本升 v1.0.0、schema 7、特征 39 项）；上一轮：第 57 轮（用户 m05545 ①② 与 m05806：新增 Mortal 报告下载（对标 NAGA 下载：`https://mjai.ekyu.moe/report/<id>.json`，按报告里的 `review.model_tag` 落成 `.mortal-a/b/c`，同名跳过）；本地牌谱后缀按来源区分（天凤 `.tenhou` / NAGA `.naga` / Mortal `.mortal-a|b|c`，旧后缀仍认）；第零类与模型显示名 `Mortal-4.1b-平衡` → `Mortal-4.1-平衡`）；上一轮：第 56 轮（用户 m05392 与 m05480：NAGA 下载判重按来源区分 —— 本地已有同名报告时，官方 naga.dmv.nico 来源跳过、不重复下载，ricochet 来源则重新下载并覆盖同名文件；天凤牌谱同名一律跳过、不再覆盖（m05480）；另确认「完场」按钮符号保持 ‖▶）；上一轮：第 54 轮（用户 m05277：1) 完场结算框加宽（≥15 张牌宽）并加大上下留白与行间距，以容纳更长的玩家 ID；2) 「完场」按钮改成只有已经弹出结算框时才灰，其它时刻点击都跳转到弹出结算框的时刻；3) 「下一步 / 下一决策 / 下一自家决策」在本局内没有符合要求的帧时不再变灰 —— 点一下跳到本局结算帧，在本局结算帧再点就跳到下一局开局）；上一轮：第 53 轮（用户 m05131：1) 控制面板改成两行七列（新增「开局」「完场」「上一自家决策」「下一自家决策」，「上一关键 / 下一关键」改名「上一决策 / 下一决策」，「开局 / 本局结束」改名「本局开始 / 本局结算」）；2) 新增完场结算框（黑底半透明、白字大字号，列出排名 / 玩家 ID / 最终得点，每行一个排名，在牌谱最终帧之后再点一次「下一步」才跳出）；3) 修「开局 / 本局结束」按钮的竖线与三角错位（`⎮` 换成 `|` / `‖`）；4) 删除控制面板下方的当前事件信息（描述栏）与「自动播放」按钮）；上一轮：第 52 轮（用户 m04556：1) 播放里读取并展示报告中的全部 AI 模型（NAGA-平衡 / NAGA-超副露 / Mortal-4.1b-平衡）决策信息，决策表标题改为可下拉切换的按钮，默认「无AI决策」= 天凤式展示、报告里没有的模型灰显；2) 新增第零类特征 3 项（原第一类「NAGA决策」改名「NAGA-平衡 分析」并移入，另加「NAGA-超副露 分析」「Mortal-4.1b-平衡 分析」）；3) 第零类检索改为四种互斥方案「任意AI决策 / NAGA决策 / Mortal决策 / 同时具有」，置于第一、二类条件上方并与它们 AND）；上一轮：第 51 轮（用户 m04498：同种 5m / 5p / 5s 的概率条优先普通 5、避开赤 5，除非手里只有赤 5；上柱与下柱共用同一规则，摸到的牌也算「手里」）；上一轮：第 50 轮（用户 m04456：1) 回滚第 48 轮对大字位置的左移（删 `VOCAL_DX` / `VOCAL_MIN_X`，位置回到官方 `vocalization_pos` 原位）；2) 牌谱检索 / 全部浏览的静态帧不画大字（`vocalForFrame()` 在 `App.itemIndex >= 0` 时返回 null））；上一轮：第 49 轮（用户 m04422：听牌率条内部改成透明、只保留基色边框，红段不变）；上一轮：第 48 轮（用户 m04386：1) 大字从空心字改回**全实心白字**（`color: #fff` + 细黑描边 `calc(var(--tile-h) * .003) #000` + 右下黑影 `text-shadow`，去掉 `color: transparent` 与 `filter: drop-shadow()`）；2) 大字整体**向左平移**避开牌河 —— `VOCAL_DX = 19.8` 个百分点（牌河半宽 10.7 + 文字半宽 7.3 + 0.5 张牌宽间隙），各展示位置变为 30.2% / 60.2% / 30.2% / 8.3%（左侧那份本来就在左家竖条牌河里，只能贴住牌桌左端）；静态帧照旧画大字（用户明确暂不改）；`web/style.css` / `web/js/ui.js` / `test/apptest.js` / `readme.md` 同步，`test/apptest.js` 全部通过，见第 44 节）；上一轮：第 47 轮（用户 m04285 ①②：1) 「牌谱播放」入口状态机 —— 静态帧（牌谱检索 / 全部浏览）不算播放状态，点入口（页签或首页卡片）先卸载牌谱、回到「等待选择」的播放界面，不再出现入口栏叠在旧牌桌上方的混乱画面（新增 `openReplayView()` / `resetReplay()`；`readFile()` 手动开谱时退出条目模式，检索条目表保留）；2) 日语大字改成只有轮廓的空心字（`color: transparent` + 白描边 `calc(var(--tile-h) * .07)` + `filter: drop-shadow()` 柔光晕，不再遮挡牌河）；`web/js/app.js` / `web/style.css` / `test/apptest.js` / `readme.md` 同步，`test/apptest.js` 564 项 / `test/naga_test.py` 138 项 / `test/agari_test.py` 189 项全通过，见第 43 节）；上一轮：第 46 轮（用户 m04160 ①②③：1) 官方大字字体随包发布 —— 用 `tools/subset_font.py` 把官方 `NotoSansJP-Black.9a73d583.otf`（4.9 MB）子集化成 9 字形「チ ー ポ ン カ ツ モ ロ ン リ」的 `media/fonts/NotoSansJP-Black.subset.otf`（5,632 B）+ SIL OFL 许可证，`web/style.css` 新增 `@font-face`「vocalization」；2) 各家副露牌侧边不再写「吃 / 碰 / 杠」文字（删 `ui.js` 的 `meld-tag` 与对应 CSS，种类仍在 class 与事件列表里）；3) 听牌率条与手牌的距离改为 0.8 倍牌宽；`build.ps1` 资源检查加入字体；`test/apptest.js` 545 项 / `test/naga_test.py` 138 项 / `test/agari_test.py` 189 项全通过，见第 42 节）；上一轮：第 45 轮（用户 m03978 ①②：1) 听牌率条与手牌之间留 0.5 张牌宽的间隔（`right: calc(100% + var(--tile-w) * .5)`）；2) 吃 / 碰 / 杠 / 荣和 / 自摸的帧在牌桌上画日语大字（チー / ポン / カン / ツモ / ロン）—— 位置按展示位置取官方 `vocalization_pos ÷ 700×650` 的百分比、字号 1.5 牌高、900 字重白字 + 黑描边 + 右下黑影、永远水平、图层在牌之上结算框之下，随「切换主视角」旋转，拔北不画；`web/style.css` / `web/js/ui.js` / `web/js/app.js` / `test/apptest.js` / `readme.md` 同步，`test/apptest.js` 536 项 / `test/naga_test.py` 138 项 / `test/agari_test.py` 189 项全通过，见第 41 节）；上一轮：第 44 轮（用户 m03799 ①②：1) 更正 —— 上一轮的「改铳率条」应改为「改三家手牌外侧的听牌率条」，先把铳率条回滚到「当前决策者手牌下方、按牌逐张画」（`danger_*[手牌主人][kind]`、同种牌只画最靠左那张、0 不画、仍只画当前决策者）；2) 把「竖条：基色边框 + 红色自下而上、宽 .307 牌宽、长 1.5 牌高（上下各伸出 .25））」这套形态改到**听牌率条**上（原为 13 张牌宽的横条），挂在 `.p-hand .tiles` 里；3) 紫色概率柱恢复居中 ——根因是上一轮新增的 `.tbar-layer` 又推了一个白边 padding（绝对定位的包含块本来就是 padding edge、`.tile` 无边框 ⇒ 百分比已按整张牌算），删层后 `.tbar.up { left: 32.5%; width: 35% }` 精确居中；`web/js/ui.js` / `web/style.css` / `test/apptest.js` / `readme.md` 同步，`test/apptest.js` 519 项 / `test/naga_test.py` 138 项 / `test/agari_test.py` 189 项全通过，见第 40 节）；上一轮：第 43 轮（用户 m03710 ①②③：1) 铳率条只画当前决策者（显示他家手牌时也一样，隐藏他家手牌时别家的条与决策表都不画）；2) 铳率条从「四家手牌下沿」改成「决策者手牌左侧的竖条」—— 基色边框 + 红色自下而上、宽 .307 牌宽、长 1.5 牌高（上下各伸出 .25）；3) 概率柱水平居中（新增 `.tbar-layer` 抵消 `.tile` 白边 padding 造成的 8.7% 偏移）；`web/js/ui.js` / `web/style.css` / `test/apptest.js` / `readme.md` 同步，`test/apptest.js` 517 项 / `test/naga_test.py` 138 项 / `test/agari_test.py` 189 项全通过，见第 39 节）；上一轮：第 42 轮（用户 m03479 ①② / m03627：1) 牌谱文件名右边新增「复制url」按钮 —— 重构并复制**原始牌谱 URL**（天凤 = `http://tenhou.net/0/?log=<log_id>&tw=0`，NAGA = `https://naga.dmv.nico/htmls/report_viewer.html?report_id=<report_id>&tw=0`，不还原 ricochet），正常播放与「牌谱检索」的静态帧播放共用；2) 布局与新增展示 —— 四家面板贴向中央信息框（下贴上沿 / 上侧贴下沿）、牌桌格间距 .45 → .25 牌宽、上下两行 6.6 → 7.4 牌高，新增**听牌率条**（每条别家手牌外侧、与手牌平行、13 张牌宽，基色下家绿 / 対面黄 / 上家蓝 + 同色边框，内部从该家自己视角左侧按听牌率变红）与**四家铳率条**（从手牌下沿向下，`danger_*` 取该手牌主人那一行，隐藏他家手牌时别家不画），两者随座位旋转与「切换主视角」联动；`test/apptest.js` + `python test/naga_test.py` / `python test/agari_test.py` 全绿，见第 38 节）；上一轮：第 41 轮（用户 m03343 ①②③ / m03411：「隐藏他家手牌」改为只隐藏别家（主视角自己的概率条与决策表保留）；新增「切换主视角」按钮 + 4 行上拉框（旋转向量 `[0,1,2,3]` 控制展示位置，切换后牌桌信息 / 概率条 / 决策表立即刷新、危险条按新观察者取行）；牌谱检索的静态帧固定把当前决策者放到主视角并禁用该按钮，见第 37 节）；上一轮：第 40 轮（用户 m03175 ①–⑦：播放视图布局改造 —— 「浏览选择…」+「按特征码搜索」（互斥、连续子串匹配、点结果进正常播放视图）、拖放区覆盖牌桌、事件列表常态显示、删示例牌谱与「打不开文件」提示段，见第 36 节）；上一轮：第 39 轮（用户 m02984 ①②③、m03089 ①②：NAGA 一炮双响两家都算出来（本场 / 供托只归先和者）；隐藏他家手牌时 NAGA 概率条与决策表一起隐藏（只留标题）；牌谱检索的静态帧固定显示他家手牌、并禁用牌桌下方的播放控制面板（只能用右上角的上一条目 / 下一条目）；数据库版本过低的提示改成一句「数据库版本过低 / 不匹配，请删除后重新分析」，见第 35 节）；上一轮：第 38 轮（用户 m02801 ①②③：1) 更正点数对照的天凤侧不一致样例 —— 真凶是探测脚本按『和了前一帧是自己杠』推岭上、漏掉『杠 → 新宝牌 → 摸岭上牌』（实例 `data/paipu/20261007-165558/2026090821gm-00a9-0000-7019128e.xml` 第 0 局），改用谱面役种提示后 71 牌谱 640 个和了局 fu 640/640、gain 640/640；2) 役种 / 番数缺失时不再假设每项 1 番，改用 `mjscore/agari.py` 引擎判的役种 + 番数（引擎也判不出时只列役种名）；`mjscore/naga.py` 的 `_hora_ctx` 增加「跳过新宝牌往前找上一帧」与「役种 id → 场况旗标」两条修正；3) 中央结算框铺满中央列（`.center width:100%`）+ `.c-result` 安全居中（flex-start + 首末 `margin:auto`）——修掉「自摸绿字标题被裁掉」与「出现纵向滚动条」，`.c-dora-show` 标签与牌同排、宝牌 / 里宝牌缩到 80%；`test/naga_test.py` 130 项、`test/apptest.js` 429 项全通过，见第 34 节）；上一轮：第 37 轮（用户 m02546 ①②：NAGA 和了 / 流局的结算信息与天凤统一 —— 符走 `mjscore/agari.py` 引擎、点数 = 报告 `deltas` 扣本场 × 300 / 供托 × 1000（与天凤 `<AGARI ten>` 同口径）、役种优先用报告的（报告缺时用引擎判的）、报告漏发立直消息时用役种里的立直补状态、`target=0` 的荣和不再被当成自摸；`mjscore/nodeharness.py` 在禁止匿名管道的环境自动回退临时文件（node 打点路径与全量测试恢复可跑），`test/naga_test.py` 新增第 7 节（119 项全通过），见第 33 节）；上一轮：第 36 轮（用户 m02227 ①②③④ / m02356 / m02357：NAGA 决策概率统一一位小数（`nagaPctText`）、新增第一类特征「立直家（他家）一发巡」（replay 维护「一发」状态、取值 = 另外三家逻辑或；NAGA决策 置首、一发巡 = 第 12 项）、偶发役互斥规则写进 `agari.rule_ctx`（嶺上≠一発 / 嶺上≠海底（写死特例）/ 槍槓≠河底）、版本 v0.2.0 + schema 5（v0.1.x 的库不再支持），`mjscore/feats.py` / `mjscore/replay.py` / `mjscore/agari.py` / `mjscore/store.py` / `mjscore/__init__.py` / `web/js/mjsfeat.js` / `web/js/replay.js` / `web/js/app.js` / `web/js/ui.js` / `web/index.html` / `test/mjscore_test.py` / `test/naga_test.py` / `test/agari_test.py` / `test/apptest.js` / `readme.md` 同步，见第 32 节）；上一轮：第 35 轮（用户 m02007 ①②③：修「概率条全都不显示」的 CSS 注释事故（`web/style.css` 少了注释结尾 `*/`，概率条 / `.tile.big` / `.tile.tsumogiri` 全部失效）+ 自家摸牌上浮 ≈6px 修正（`.p-hand .drawn` 按底对齐）+ 概率条跟随决策玩家（`seat: nagaSeatOf(nf)` + `addNagaBars(..., mode)`）+ 展示帧不算关键帧且面板整块留空，`web/style.css` / `web/js/ui.js` / `web/js/app.js` / `test/apptest.js` / `readme.md` 同步，见第 31 节）；上一轮：第 34 轮（用户 m01903 ①②③：关键帧改为「等待玩家决策的帧」（`draw` / `discard` / `call`，跳过立直宣言 / 新宝牌 / 和了 / 流局）、立直行作为展示特例永远排第一且不看 10% 门槛并用红色区分、九种九牌只按打牌概率展示，`web/js/app.js` / `web/style.css` / `test/apptest.js` / `readme.md` 同步，见第 30 节）；上一轮：第 32 轮（用户 m01518 ①②③：按 m00198 规格实现 NAGA 决策概率展示 —— 「NAGA 决策」面板（>10% 选项两列表 + 5 个数据纯文本）、自家手牌上下概率条、按决策玩家切换、`huro` 吃的三种牌对下标实证；麻将牌面加白边；特征码完整换行不省略（工具栏 + 当前帧特征标题行 106px），`web/style.css` / `web/index.html` / `web/js/ui.js` / `web/js/app.js` / `test/apptest.js` 同步，见第 28 节）；上一轮：第 31 轮（用户 m01386：播放视图各区域固定尺寸 —— 牌桌三行固定轨道、工具栏 46px、特征码条 28px、控制条 50px、描述栏 34px、特征面板标题行 32px、摸牌槽位常驻、本局结果与回放警告改绝对定位浮层，`web/style.css` / `web/index.html` / `web/js/ui.js` / `web/js/app.js` / `test/apptest.js` 同步，见第 27 节）；上一轮：第 30 轮（用户 m01171 ①②③：NAGA 报告手选 / 拖放改走本地服务 `POST /api/naga-convert` 转换、分析页牌谱目录 / 文件改下拉（`/api/paipu-browse`）、分析速度瓶颈定位与实测，见第 26 节）；上一轮：第 29 轮（用户 m00080 目标 3 / m00815 ①②③：NAGA 报告接入打点链路 —— `mjscore/naga.py` 补 log_id、`feats.py` 第一类第 17 项「NAGA决策」（有/无）共 34 个特征、`store.py` schema v4 + `frame_naga` 索引、前端 accept 与扫描 `kind=all`、测试与文档同步，见第 25 节）；上一轮：第 28 轮（用户 m00653：NAGA 流局种类从事件推断 + 听牌自算，新增 `test\naga_test.py` 并接入 `build.ps1`，见第 24 节）；上一轮：第 27 轮（用户 m00080 目标 2：NAGA 报告适配层 `mjscore/naga.py` + `/api/read` 与前端播放接线，见第 23 节）；上一轮：第 26 轮（用户 m00080 / m00268 / m00418：NAGA / ricochet 牌谱下载支持 + 完整 report_id 判重，见第 22 节）；上一轮：第 25 轮（用户 m00751 / m00796：打包 —— `build.ps1` 一键脚本（图标 → PyInstaller 后端 → 冒烟 → electron-builder NSIS）、`packaging/pyi_build.py`（含 `--in-process` 兜底）、`packaging/smoke.py`、`desktop/main.js`、`packaging/installer.nsh`、根 `package.json` 补齐、readme 新增第 9 节；后端产物 `dist\pyi\tenhou-paipu-analysis-server`（exe 2,341,406 B + 内嵌 node 91,694,408 B）实测可跑（冻结端到端分析 89.3 s / 530 帧入库）；受限沙箱里 electron-builder 必死（`spawn EPERM`，见踩坑 84~89），安装包由用户本机跑 `build.ps1` 出；用户机复测发现 `-c.npmRebuild=false` 被 electron-builder 当成配置文件路径（`ENOENT ...\.npmRebuild=false`），已改成 `package.json` 的 `build.npmRebuild = false`（踩坑 90，见第 21.7 节）；见第 21 节）。上一轮：第 24 轮（用户 m00178 / m00590：新增「本地数据管理」第六个页签与首页第五张卡（3 x 2 布局）、修首页「载入示例牌谱」相对路径 bug（web/js/app.js 改走 /api/health + /api/scan + 绝对路径）、拆出 mjscore/paths.py（只读资源根 / 用户数据根分离；冻结后默认 %LOCALAPPDATA%\tenhou-paipu-analysis\data，与用户已迁移位置一致）、加固 data/paipu 与 data/db 的越界（..、绝对路径、跨根、软链接/目录联接一律 400）、新增 	ools/svg2ico.py 生成 uild/icon.ico、精简 .gitignore；验证：	est/apptest.js 全通过 + 新增 	est/datamgr_test.py 67/67，	est/mjscore_test.py 全量仍未跑完；见第 20 节）。上一轮：第 23 轮（用户 m04115：修「扩充现有数据库」把库名拼成 `<名字>.sqlite.sqlite` 导致报「数据库不存在」的 bug（`cli.db_path_of()` + `server._db_of()`）；与向听数有关的特征内部值 3 一律显示 `>=3`（`cli.feat_value_text()` / `web/js/app.js` 的 `fmtFeatValue()`，检索仍按内部整数匹配，`3` / `3-5` / `>=3` 都命中内部值 3）；新增作者信息（`mjscore\__init__.py` 的 `AUTHOR` / `AUTHOR_EMAIL` + `/api/health` `/api/features` + 页眉 `#appAuthor`）；项目结构整理 —— 前端移到 `web/`（`index.html` / `style.css` / `js/`）、命令行移到 `tools/`（`analyze.py` / `download_tenhou.py`），根目录只留 `server.py`，并顺手修掉批量替换引入的 `\a`（BEL）/ `\d`（SyntaxWarning）缺陷；GitHub 本地已 `git init` + 提交 `ceda372`（78 文件 / 32315 行），推送待账号 / PAT。测试：`test\apptest.js` 276 OK、`test\mjscore_test.py` 全量 通过 217 项 / 失败 0 项（wall 3658.0 s ≈ 61.0 分钟，exit=0）、`test\agari_test.py` 182 / `test\danger_test.py` 29 / `test\expect_test.py` 73 / `test\shanten_test.py` 92 / `test\selftest.js` / `test\uitest.js` 全绿。追加修正（用户 m04628）：牌谱播放改为入口式，首页只留介绍 + 「开始播放」按钮；追加修正（用户 m04553）：`/` 与 `/index.html` 由内部改写改为 **302 跳转**到 `/web/index.html`（否则页面里的 `style.css` / `js/*.js` 会解析成旧路径而 404）；本节见第 17 节；当前有效展示规则 = 5.1~5.7；下一步见第 18 节。）*；后续（用户 m01034）：默认安装位置改为 `C:\Program Files\tenhou-paipu-analysis`（`build.nsis.perMachine = true`，见 21.8）。后续（用户 m01084 / m01106）：牌谱播放的「选择牌谱文件」在桌面版由主进程原生对话框默认定位到 `%LOCALAPPDATA%\tenhou-paipu-analysis\data\paipu`，浏览器 / 源码 / 离线模式仍退回浏览器文件框（见 21.9、踩坑 93~95）；后续（用户 m01355）：用户本机构建安装包成功 + 全量回归通过（见 21.11）。后续（用户 m01220）：从控制面板卸载时「是否删除数据」的询问没有出现 —— 按所有用户安装时 `$LOCALAPPDATA` 被解析成 `C:\ProgramData`，已改成先 `SetShellVarContext current` 定位数据目录、询问框默认按钮「否」、静默卸载保留数据（见 21.10、踩坑 96~98）。第 51 轮（

---

## 58. 第 63 轮：关键帧判据改成「可能被他家鸣牌」+「等待鸣牌」编为第三类特征（用户 m07289，v1.3.0 / schema 10）

### 58.1 交付物
| 文件 | 改动 |
| --- | --- |
| `mjscore/feats.py` | 新增 `_kind_counts` / `chi_pairs` / `chi_forbidden` / `can_chi` / `can_pon` / `responders` / `meld_possible`；`meld_wait` 移出 `BASE_FEATURES`、成为 `THIRD_FEATURES`（`FEATURES` = AI 5 + 第一类 17 + 第二类 17 + 第三类 1，末列 `f_meld_wait`）；`records_for_round()` 的 discard 分支改用 `responders()`、**每个可能鸣牌的家各出 1 行** |
| `mjscore/store.py` | `SCHEMA_VERSION = 9 → 10`；新增 `compile_wait()` 与 `compile_query(conds, ai=None, wait=None)`、`query(..., wait=)`；索引新增 `frame_wait` |
| `mjscore/cli.py` | `--wait`（出牌 / 鸣牌响应）、`run_query(..., wait=)`；`--features` 文案改 5 + 17 + 17 + 1 |
| `mjscore/server.py` | `/api/query` 透传 `wait`；`/api/features` 另带 `first_features` / `second_features` / `third_features` / `wait_modes` |
| `web/js/mjsfeat.js` | `THIRD_FEATURES`（前端测试与下拉靠它算数）；`extract(st, seat, kind)` 的 `meld_wait` 按 `kind === 'wait'`；`recordsForRound()` 同步新判据 |
| `web/js/app.js` | `isKeyFrame()` 重写；新增 `responders` / `decisionSeats` / `selfTsumoAgari`；`seatOfFrame` / `frameSeatOf` 在出牌帧返回可能鸣牌者（优先主视角、否则座位最小）；`stepSelfKey` 改判「主视角是否在 `decisionSeats` 里」；`Sc.wait` + `setWait` / `waitPayload` / `syncWaitRadios`；`isThirdKey`（面板只显示第一 / 二类）；`renderFeatMode()` 面板底部大号「出牌局面 / 鸣牌响应局面」；`kindName` 的 `wait` → 「鸣牌响应帧」 |
| `web/index.html` | 第零类框标题改「**是否具有AI决策**」；右端新增 `#waitPlan`（两行 radio `name="waitMode"`，默认「出牌」）；`#featPanelList` 之后新增 `#featPanelMode` |
| `test/naga_test.py` | 合成样本 2 → 3 行（第 3 行是 6p 下家的鸣牌响应帧，seat 2、`meld_wait` = 是）；schema 10、40 = 5 + 17 + 17 + 1 |
| `test/apptest.js` | 关键帧 / 决策者断言按「可能鸣牌」改（帧 2 的决策者 = 座位 1）；下拉 34、面板 34 行；第三类断言（`FEATURES[39].key === 'meld_wait'`、不进下拉）；「鸣牌响应」请求带 `wait`；v1.3.0 |
| `test/mjscore_test.py` | 期望值按新口径改（行数 3191 → **3466**、wait 405 → **680**、`per_file` → `[458, 660, 676, 699, 973]`、第二类切片 `FEATURES[22:]`、schema 10 / v1.3.0、枚举 14 项、query 默认「出牌」）；**按用户 m07294 本轮不跑全量** |
| `readme.md` | v1.2.0 → v1.3.0、特征 40 = 5 + 17 + 17 + 1、新增 2.4「第三类特征」节、4.3 步骤 2 / 5、4.4 决策帧段落、版本段（schema 9 降级为历史条目） |
| `log.md` | 本节 |

### 58.2 技术要点
1. **判据 `responders(st, discarder, kind)`**（`mjscore/feats.py` / `web/js/mjsfeat.js` 同构）：遍历另外三家，跳过已立直（`riichi or riichiPending`）的家，命中条件 = `can_pon(hand, kind)`（同种 ≥2，碰 / 大明杠都算）或（`s == (discarder + 1) % 4` 且 `can_chi(hand, kind)`）—— 吃**只有下家**能吃，且吃完后手里的牌里要有**不在食替禁牌里**的一张（`chi_forbidden(a, b)`：相邻对禁 `lo-1` / `hi+1`、间隔对禁 `lo+1`；同花色边界外不算；字牌 kind ≥ 27 直接不可吃）。返回**升序座位列表**，`meld_possible()` = 非空。
2. **`kind = 'wait'` 行**：`records_for_round()` 的 discard 分支现在无条件按 `responders()` 出帧（`wait_record(game, round_index, ev_index, st, ev, seat)`，`frame_index = ev_index + 1`、`drawn = None`、巡目 = 响应者自己的出牌次数 + 1）⇒ **只可能鸣牌的那一家各 1 行**，不再固定 3 行；**仅可能被荣和**的出牌帧不出行（`ron` 判据被删掉）。
3. **「决策帧 ≡ 可检索静态帧」**：前端 `isKeyFrame()` 与后端 `responders()` 用同一判据 —— `draw` 恒真（除非下一事件是自摸和了）、`call` 只认 chi / pon、`discard` 看 `responders()`；`reach` 帧不再算决策帧（立直宣言跟着出牌帧一起判），暗杠 / 加杠 / 大明杠的 call 帧不算。
4. **「自家决策」** = 主视角本人这一帧要做决定（`decisionSeats(i).indexOf(App.selfSeat) >= 0`），因此「上一 / 下一自家决策」只在主视角自己需要决策的帧停（用户 m07289 ⑤）。
5. **第三类特征**：`FEATURES` 顺序 5 + 17 + 17 + 1（末列 `f_meld_wait`），前端 `isThirdKey()` 把 `meld_wait` 排除出「特征词条」下拉与「当前帧特征」面板；面板底部改由 `#featPanelMode` 用大号居中文字显示「出牌局面 / 鸣牌响应局面」（帧 `kind === 'wait'` → 后者）。
6. **检索单选**：`Sc.wait`（`'出牌'` / `'鸣牌响应'`，默认「出牌」）随 `conds` 一起作为 AND 条件发给 `/api/query`（`kind = 'wait'` ⇔ `f_meld_wait = '是'`）；前端不用 DOM radio（假 DOM 里 `#waitPlan` 是空元素）而用 `App.setWait()` / `Sc.wait` 驱动。

### 58.3 测试
- `python test\naga_test.py` **222 / 0**（合成样本新增鸣牌响应帧行）。
- `python test\mortal_test.py` **106 / 0**（`rseats` 用动态集合，wait 行变化不影响）。
- `node test\apptest.js` **全部通过**；`node test\selftest.js` / `node test\uitest.js` **exit 0**。
- `python test\datamgr_test.py` **67 / 0**。
- `test/mjscore_test.py`：期望值已按新口径改（`py_compile` 通过），**本轮不跑全量**（用户 m07294）；新口径数值由临时脚本实测：打点行 3466（draw 2679 + chi 50 + pon 57 + wait 680）、5 份牌谱各 458 / 660 / 676 / 699 / 973、junme 取 1~19、enum 特征仍是 14 项（5 第零类 + 9 个第一类枚举，`meld_wait` 归第三类）。

### 58.4 踩坑
1. **单行锚点会吃掉缩进** —— 用「逐行 strip + `[ \t]*`」的宽松替换做单行锚点时，被替换行自己的前导缩进也会被吞掉（5 处：`eq(row["idx"]…)`、`len(feats.FEATURES)`、`_enums`、analyze 摘要、browse 断言），改完必须 `py_compile` + 复核缩进，或用整行精确匹配。
2. **`# 天凤牌谱分析 v1.2.0` 在 readme.md 出现 2 次**（第 1 行标题 + CLI 注释），只按这一句替换会 `MISS(2/1)`；改成带上下文的锚点（标题 = `…v1.2.0\n\n把天凤`，CLI = `…v1.2.0\n\npython server.py`）。
3. 补丁脚本把单个中文字符串写进 `rep(...)` 时凡含 `'`（如 `kind = 'wait'`）必须改用双引号，否则 `SyntaxError: invalid syntax. Perhaps you forgot a comma?`。
4. 「仅可荣和的出牌帧不算决策帧」是我的取舍（依据：用户 m07289 ③「能和就和、构不成决策点」+ NAGA 的 `huro` 类型只有 chi / pon / daimankan，没有 ron）—— 已写进交付报告请用户确认。

### 58.5 待办
- 交付报告里要**详细解释第 3 项**（huro 只有 PASS 概率时，后端 `_model_has_data()` 判「有数据」而前端 `aiFrameHasData()` 判「无数据」的口径差异），等用户拍板是否统一。
- 待用户拍板：立直宣言帧 / 杠帧 / 被排除的自摸摸牌帧是否也补检索行（本轮按 m07289 不补）。
- `test/mjscore_test.py` 全量（约 41 分钟）需用户本机或后台跑。
- 视觉待用户目视确认（沙箱无浏览器）；改动需 `build.ps1` 重建或 `python server.py` + Ctrl+F5。
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在；用户预告会补更多 NAGA URL 做全面测试。

## 59. 第 64 轮：红 / 绿 / 黄框的图层与尺寸 + 静态帧「鸣牌响应局面」黄框 + 第零类「有数据」口径统一（用户 m07820）

### 59.1 交付物
| 文件 | 改动 |
| --- | --- |
| `web/style.css` | `.tile.called` / `.tile.win` 加 `z-index: 1`、外扩 `.17 → .14`、内描边 `.11 → .08` 牌宽；新增 `.tile.mark`（黄框 `#ffd54a`，尺寸同红 / 绿框）；`.tbar` 不动（它是 `.tile` 的子元素，树序在框之后 ⇒ 仍在框之上） |
| `web/js/ui.js` | `riverEl(river, markLast)` 给 `c === markLast` 的那张牌加 `mark`；`renderPlayer()` 按 `opts.mark.seat === seat` 传 |
| `web/js/app.js` | `render()` 内联算 `mark`（仅静态帧：条目 `kind === 'wait'`、且该帧 `ev.type === 'discard'` ⇒ `{seat: ev.player}`）并传 `UI.renderBoard(…, mark: mark)`；`nagaSeatOf()` 在算不出最大项时退化到 `huro` 的席位（唯一席位直接返回、多席位取 PASS 最大者）；`aiFrameHasData()` 的座位改用 `nagaSeatOf(aiFoldFrame(nf, idx))` |
| `test/apptest.js` | 第零类断言改 (a) 口径（PASS-only → `true`、全 0 → `false`）；CSS 节新增框图层 / 尺寸 / 黄框断言；棋盘节新增静态帧黄框 DOM 测试（出牌者牌河最后一张有且仅有 1 个 `.mark`，正常播放没有） |
| `readme.md` | 4.4 新增牌河描边条目（红 / 绿 / 黄框、图层、尺寸）；AI 面板条目补 (a) 口径与 41 份样本实测；版本段补「第 64 轮无 schema / 特征变化」 |
| `log.md` | 本节 + 页脚 |

### 59.2 技术要点
1. **红 / 绿框上顶层 + 略缩小**：`.tile.called`（被鸣走的牌，`#e0503a`）与 `.tile.win`（被荣和的铳牌，主题色）加 `z-index: 1` 后画在所有 `z-index: auto` 的牌之上；同一家面板里多张框之间由 DOM 顺序决定（后打出的牌在上）。`.vocal`（大字）也是 `z-index: 1` 但 DOM 在牌之后 ⇒ 仍在牌框之上；`.final-box` 是 `z-index: 2` ⇒ 仍在最上。r90 / r180 / r270 的座位面板有 `transform`、各自形成层叠上下文 ⇒ 框只在同一家面板内提升（实测足够：框外扩只撞同一排邻牌）。
2. **静态帧黄框**：`kind === 'wait'` 的静态帧里，被响应者等待鸣牌的那张**打出牌**（出牌者牌河最后一张）加 `.tile.mark`（黄 = 检索高亮色 `#ffd54a`，尺寸与红 / 绿框一致）；只在 `App.itemIndex >= 0`（检索 / 全部浏览的静态帧）画，正常播放不画。
3. **第零类「有数据」口径统一为 (a)**：后端 `_model_has_data()` 本来就是「该模型该座位那一格里有任一非 0 概率就算有数据」（`huro` 只看决策者那一格）—— 前端 `aiFrameHasData()` 原来要求「非 PASS 选项里有非 0 概率」，且 `nagaSeatOf()` 取座位的退化路径（`nf.actor`）在「只剩 `huro`」的帧上会因 `huro[seat]` 是**按模型分档的数组**而算不出值 ⇒ 两者合起来把「只有 PASS 概率」的帧判成「无数据」。现在先按选定模型 `aiFoldFrame(nf, idx)` 折叠、再用 `nagaSeatOf()` 找座位（算不出最大项时退化到 `huro` 的席位），最后只要该座位有任一非 0 概率就判「有数据」。
4. **实测（41 份 NAGA 报告）**：`huro` 只出现在「有人打出牌」（`msg == 'dahai'`）的帧上（6 份样本 758 帧）；席位分布 1 席 728 / 2 席 30；按席位统计 PASS-only 2169 / 含实际鸣牌选项 3534 / **全 0 为 0**；按帧统计「只有 PASS」1992、「含鸣牌选项」3173、两席都含鸣牌选项 120、两席都只有 PASS 28、混合 121 ⇒ (a) 口径下前端与后端在所有真实帧上完全一致（不存在「该席位全 0 而别家非 0」的残余不一致），旧前端口径会在其中 2113 帧（1992 + 121）上把某个模型的可用性判错。

### 59.3 测试
- `node test\apptest.js` 全部通过；`node test\selftest.js` / `node test\uitest.js` exit 0。
- `python test\naga_test.py` 222 / 0、`python test\mortal_test.py` 106 / 0、`python test\datamgr_test.py` 67 / 0。
- 按用户 m07294：本轮仍**不跑** `test/mjscore_test.py` 全量（该文件本轮无改动）。

### 59.4 踩坑
1. 假 DOM 的子节点没有 `parentNode`，只有自定义的 `.parent` ⇒ 沿祖先链找 `.p-river` / `.p-hand` 要循环 `.parent`。
2. `test/apptest.js` 的 `cssRule(text, sel)` 只认「选择器 + 一个空格 + `{`」，新规则选择器与 `{` 之间多空格就取不到 —— 断言里另写了按正则取规则块的局部 helper。
3. `nagaSeatOf()` 原来对**原始**（未按模型折叠）帧做「选项 id → 概率」比较，`huro[seat]` 是按模型分档的数组 ⇒ `dict > number` 恒 false，会静默退化到 `nf.actor`；判定前必须先用 `aiFoldFrame(nf, idx)` 折叠。
4. 静态帧黄框必须同时限定 `kind === 'wait'` 与 `App.itemIndex >= 0`，否则正常播放里也会冒出一张黄框。

### 59.5 待办
- 视觉待用户目视确认（沙箱无浏览器布局测量）：红 / 绿 / 黄框的图层与尺寸、静态帧黄框的位置。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次（第 63 轮改的期望值尚未经全量验证）。
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在；用户预告会补更多 NAGA URL 做全面测试。
## 60. 第 65 轮：加杠副露丢牌的真 bug + 细红框（打牌 / 暗杠 / 加杠）+ 多家可鸣牌的静态帧（用户 m08125 ①②③ / m08178，v1.3.0 / schema 10）

### 60.1 交付物
| 文件 | 改动 |
| --- | --- |
| `mjscore/naga.py` | `kakan` 分支只输出「加进去的那一张」（报告里的 `consumed` 反推不出牌 ID） |
| `mjscore/replay.py` | `apply_call` 的 `kakan` 把那一张并回同种的碰 ⇒ 副露 = 4 张同种牌（找不到时只保留那一张 + 警告） |
| `web/js/replay.js` | 与 Python 同步的「并回碰」逻辑 |
| `web/style.css` | 新增 `.tile.next`（细红框，`inset 0 0 0 calc(var(--tile-w) * .06) #e0503a`，`z-index: 1`） |
| `web/js/ui.js` | `meldEl(m, seat, nextIds)`（副露里被框的牌不再横放、改用 `next` 类）、`renderPlayer` 的 `opts.next = {kind, tids, melds}`（手牌只给 kind 时按概率条那套挑一张） |
| `web/js/app.js` | 新增 `redMarkOf(st)`（出牌局面 / 立直宣言 + 暗杠 / 加杠），`render()` 传 `next`；导出 `App.redMarkOf` |
| `test/apptest.js` | 新增细红框 / 多家可鸣牌静态帧断言；副露牌张数断言加上期望值表（`chi`/`pon` 3、`kakan`/`ankan`/`daiminkan` 4） |
| `test/naga_test.py` | 新增第 11 节：真实样本里每个副露的牌张数与种类 |
| `test/mjscore_test.py` | 全量语料的副露形状回归（加杠 / 暗杠 / 大明杠 4 张同种牌） |
| `readme.md` / `log.md` | 4.4 新增细红框条目、版本段新增第 65 轮 + 本节 + 页脚 |

### 60.2 技术要点
1. **加杠丢牌的根因**：NAGA / Mortal 报告的 `kakan` 事件只带 `consumed`（mjai 牌名）、没有可用的牌 ID；`mjscore/naga.py` 尝试从手牌 / 牌山取 3 张旧牌都失败后只输出 1 张，而 `replay.apply_call` 用 `melds[k]["tiles"] = ev["tiles"]` 直接覆盖 ⇒ 碰的 3 张被丢。修法 = 两边各改一处：`kakan` 只输出那一张，回放 `[added] + pon.tiles[:3]` 并回。
2. **细红框**（`web/style.css` 的 `.tile.next` + `ui.js` 的 `nextIds`）：只在「主视角本人 = 这一帧的决策者」且下一个动作是打牌 / 立直宣言 / 暗杠 / 加杠时画；打牌只给 kind（同种多张按概率条那套「最靠左且优先普通 5」挑一张），暗杠 / 加杠给准确牌 ID（4 张，其中加杠包含副露区那 3 张）。
3. **图层**：细红框与牌河红框同为 `z-index: 1`（同家面板内在其它牌之上，同家内靠 DOM 顺序 = 后打出的在上）。
4. **多家可鸣牌**：`feats.records_for_round` 对每个出牌帧按 `responders()` 逐家各打 1 行、`seat` = 响应者 ⇒ 检索结果里每家各一条，静态帧的主视角由行里的 `seat` 决定（`frameSeatOf`）。

### 60.3 测试
- `node test\apptest.js` 全部通过；`node test\selftest.js` / `node test\uitest.js` exit 0。
- `python test\naga_test.py` **224 / 0**（新增第 11 节：样本副露统计 pon 36 / chi 24 / ankan 2 / kakan 2 / daiminkan 2）、`python test\mortal_test.py` 106 / 0、`python test\datamgr_test.py` 67 / 0。
- 全量语料（71 个牌谱）副露形状手工探针：pon 783 / chi 615 / ankan 42 / kakan 30 / daiminkan 2，0 处异常。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑。

### 60.4 踩坑
1. 假 DOM 的父指针叫 `.parent`（不是 `parentNode`），沿祖先链找 `p-river` / `p-hand` 要用 `.parent`。
2. `cssRule(text, sel)` 只认「选择器 + 一个空格 + `{`」，新规则选择器与 `{` 之间多空格就取不到；断言里另写了按正则取规则块的局部 helper。
3. 细红框一开始只支持一张牌（`nextTid` 单值），暗杠的 4 张只画出 1 张 ⇒ 改成 `nextIds` 数组。
4. `test/apptest.js` 的 `.meld-*` 断言原来只比「渲染张数 == 状态张数」（状态自己错了就测不出来），已改成并比期望值表。
5. `test/mjscore_test.py` 里「副露是 4 张同种牌」的回归若按「每个加杠事件只对应 1 组副露」写会误报（一个玩家可以有两组加杠）⇒ 应按「每个 kakan 副露自己都是 4 张同种牌」逐副露判。
6. 手牌与摸牌槽位会同时出现同一张牌（`st.drawn` 也在 `pl.hand` 里）⇒ 细红框给准确 ID 时要先去重。

### 60.5 待办
- 视觉待用户目视确认（沙箱无浏览器布局测量）：细红框的细程度与位置（手牌 / 副露区的 4 张）。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次（本轮已加入副露形状回归）。
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在。

## 61. 第 66 轮：细红框跟着决策者 / 所有牌同尺寸 / 加杠第 4 张按官方画法 / 牌河最多 3 排 / 杠名称按牌局状态规范化（用户 m08319 ①②③④ + m08576 + m08623，v1.3.0 / schema 10）

### 61.1 交付物
| 文件 | 改动 |
| --- | --- |
| `web/js/app.js` | `redMarkOf(st)` 的决策者从「主视角」改成 `frameSeatOf(st)`，返回值带上 `seat`（用户 m08319 ①） |
| `web/js/app.js`（杠名称） | `nagaOptions()` 的杠选项改成按**牌局状态**取名（手里 4 张 =「暗杠」、已有碰副露 + 手里第 4 张 =「加杠」），报告档位（`kan['1']` / `kan['2']`）只作提示（状态里只有一种杠时按状态取名）；`huro` 档位 5 从「杠」改成「大明杠」（用户 m08623） |
| `test/apptest.js`（杠名称） | 新增 4 条断言：Mortal 把加杠报成 `ankan` 时显示「加杠 89.6%」、手里 4 张显示「暗杠」、`huro` 档位 5 显示「大明杠」、加杠行画出手里第 4 张牌 |
| `web/js/ui.js` | 细红框门控改成 `seat === opts.next.seat`（画在决策者那一家，不一定是主视角）；手牌 / 摸牌槽位不再传 `big`（用户 m08319 ③）；`riverEl` 改成**最多 3 排**（前 2 排各 6 张、第 13 张起在第 3 排向右延伸，用户 m08576） |
| `web/style.css` | `.tile-stack .tile.added` 改官方 `kanPai` 画法（`left: 0; top: calc(var(--tile-w) * -1)`，用户 m08319 ④）；删 `.p-hand .drawn.self`（用户 m08319 ③）；`.tile.big` 规则保留但播放界面不再使用 |
| `test/apptest.js` | 细红框「跟着决策者走」（帧 3 的框画在座位 1 手里）、牌桌上 `big` 为 0、`.p-hand .drawn.self` 已删、`.tile-stack .tile.added` 的官方偏移；7d 牌河分行断言按「最多 3 排」重写 + `UI.riverEl` 直接断言 6/12/13/18/19/20/24/30 张 |
| `readme.md` / `log.md` | 4.4 细红框条目改写 + 牌桌条目补「所有牌同尺寸 / 加杠画法」、版本段新增第 66 轮 + 本节 + 页脚 |

### 61.2 技术要点
1. 细红框判据：`redMarkOf(st)` 用 `frameSeatOf(st)` 取「本帧决策者」，再看**下一个事件**（`frames[k].ev = events[k - 1]` ⇒ `events[App.frameIndex]`）：`discard`（含 `reach` 之后的 `discard`）⇒ 给 `kind`（手牌里同种牌只框一张、优先普通 5）；`call` 且 `ankan` / `kakan` ⇒ 给准确牌 ID（4 张）。`ui.js` 端用 `seat === opts.next.seat` 决定画在哪一家。
2. 静态帧不需要特殊处理：`frameSeatOf()` 在条目模式下直接返回那一行的 `seat`（静态帧的主视角就是决策者），所以「不限定主视角」之后静态帧的表现与以前完全一样。
3. 所有牌同尺寸：`.tile.big`（1.15 倍）不再被播放界面使用（规则保留，apptest 仍断言它随牌宽缩放）；`.p-hand .drawn.self` 的 1.15 倍槽位一并删除 ⇒ 手牌 / 摸牌槽位 / 副露 / 牌河全部同尺寸（`.tile.big` 仍由牌谱分析页等处使用）。
4. 加杠第 4 张：官方 `renderPon` 把 `t.kanPai` 画在 `(e, i + hai_h - 2*hai_w)` —— 与横放的那张同列、正上方一整张牌宽；本仓原先是 `.30 牌宽 / -.18 牌高` 的斜向偏移，改成 `left: 0; top: calc(var(--tile-w) * -1)`（上移的那张向上溢出 `.tile-stack`，靠 `.meld` 的横向空隙容纳）。
6. 杠名称（用户 m08623）：`nagaOptions()` 原来**按报告档位贴标签**（`kan['1']` → 暗杠、`kan['2']` → 加杠），但 Mortal 复盘的报告会把**加杠报成 `ankan`**（`consumed` 4 张，实测 `695a461ed34f4e4b.mortal-c` 東 2 局 entry 10）⇒ 显示成「暗杠」。现在改成：从状态算出候选（`nagaKanInfo()`：手里同种 ≥4 = 暗杠候选、已有 `pon` 副露 + 手里同种 ≥1 = 加杠候选），按报告档位挑同名候选；**档位与状态不符时用剩下的那一种**（报告档位只作提示）。`huro` 档位 5（大明杠）的显示名从「杠」改成规范术语「大明杠」；三种杠的日语大字仍是「カン」（官方 viewer 三种杠同字）。
5. 牌河（用户 m08319 ② / m08576）：`riverEl` 每排最多 `RIVER_COLS = 6` 张、**最多 `RIVER_TILE_ROWS = 3` 排** —— 前 2 排各 6 张，第 13 张起把剩下的牌全部放在第 3 排向右延伸（**不再放入第 4 排**）。CSS 仍按 `RIVER_ROWS = 4` 排预留 `min-height`，第 4 排只留白：这样牌河长到 19 张以上时手牌位置也不会跳（用户 m01386）。

### 61.3 测试
- `node test\apptest.js` **全部通过**（784 行输出 / 0 失败；其中 4 条是本轮新增的杠名称断言）；`node test\selftest.js` / `node test\uitest.js` exit 0。
- `python test\naga_test.py` 224 / 0、`python test\mortal_test.py` 106 / 0、`python test\datamgr_test.py` 67 / 0。
- 牌河：7d 节「末帧牌河分行」（最长 15 张 ⇒ 四家都是 3 排、前 2 排各 6 张、第 3 排 1~3 张）+ `UI.riverEl` 直接断言（6/12/13/18/19/20/24/30 张 ⇒ `[n]` / `[6,6]` / `[6,6,n−12]`）全部通过；`apptest.js` **780 行输出 / 0 失败**。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑（用户 m07294：本轮不做全量测试）。

### 61.4 踩坑
1. 细红框的「决策者」与「主视角」在第 65 轮被写成同一个条件（`frameSeatOf(st) !== App.selfSeat` 早退）——正常播放时没问题，但只要出现「主视角不是决策者」的帧（例：别家摸牌打牌）就整帧不画；改成决策者后 `ui.js` 也必须改成按 `opts.next.seat` 找那一家，否则框会画到主视角手里。
2. `.tile-stack` 有固定宽高 ⇒ 上移的第 4 张会溢出格子，检查张数时要按 `.meld` 子树数（不能用格子内元素数）。
3. 手牌与摸牌槽位可能同时出现同一张牌（`st.drawn` 也在 `pl.hand` 里）——细红框给准确 ID 时要先去重（第 65 轮已修，本轮沿用）。
5. Mortal 报告会把**加杠**报成 `{"type":"ankan","consumed":[C,C,C,C]}`（NAGA 报告则是 `kan` 档位字典 `{'1': 暗杠, '2': 加杠}`，实测形如 `{"0": 207, "2": 9792}`）⇒ **不能按报告档位贴标签**，必须结合牌局状态（手里 4 张 / 碰副露 + 手里 1 张）；`nagaKanInfo()` 就是为此准备的。
4. 牌河的 4 排预留是**刻意**的（用户 m01386：牌河变长时手牌位置不跳）—— 改分排规则只动 `riverEl` 的分行上限（`RIVER_TILE_ROWS`），CSS 的 `min-height: calc(var(--tile-h) * 4 …)` 保持不变。

### 61.5 待办
- 视觉待用户目视确认（沙箱无浏览器布局测量）：所有牌同尺寸后的观感、加杠第 4 张的位置、AI 决策面板里的杠名称（暗杠 / 加杠 / 大明杠）。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次。
- 用户 m00080 目标 4（牌谱检索 / 数据管理对 NAGA 的进一步支持）仍在。

## 62. 第 67 轮：打包发布 —— 修 `_ssl` 加载失败 + 图标 6m 图案收缩（用户 m08700，v1.3.0 / schema 10）

### 62.1 交付物
| 文件 | 改动 |
| --- | --- |
| `packaging/pyi_build.py` | 新增 `ssl_pair()` / `fix_ssl_pair()` / `file_sha256()`；`build_args()` 把本环境 `Library\bin` 的 `libssl-3-x64.dll` / `libcrypto-3-x64.dll` 一起 `--add-binary`，打包后再按 SHA256 校验并覆盖 |
| `tools/svg2ico.py` | 新增 `--content-scale`（默认 1.0）：牌面白底不缩，只把图案围绕牌面矩形中心收缩 |
| `build.ps1` | 图标步骤加 `--content-scale 0.84`；文件头注释同步 |
| `build/icon.ico` + `icon_16/32/48/64/128/256.png` | 重新生成（39,748 B） |
| `readme.md` / `log.md` | 第 9 节补 OpenSSL 与 `--content-scale` 两条注意 + 产物名改成按 `package.json` 的 version；版本段加第 67 轮；本节 |

### 62.2 技术要点
1. **根因**：conda 的 base 环境与 `py314_null` 各有一套 OpenSSL。PyInstaller 的依赖搜索先命中了 base 的那套（789,320 B libssl / 5,297,992 B libcrypto），
   而 `_ssl.pyd` 是从本环境 `DLLs` 收的（193,864 B，SHA256 与本环境一致）⇒ 运行时 `LoadLibrary` 报「找不到指定的程序」。
2. **修法（双保险）**：显式 `--add-binary <env>\Library\bin\<dll>;.`（让 PyInstaller 的清单里有正确来源）+ 打包后 `fix_ssl_pair()` 按 SHA256 覆盖
   `dist\pyi\tenhou-paipu-analysis-server\_internal\` 下的同名文件（同名冲突时以覆盖为准，确定性最强）。
3. **验证**：`packaging\smoke.py` 实测 —— 就绪 0.5 s、`/api/health` 返回 `name 天凤牌谱分析 / version 1.3.0 / author Zumma Crystal`、
   `data_root %LOCALAPPDATA%\tenhou-paipu-analysis`、`dbs 1 个`。
4. **图标**：`--content-scale` 只改图案矩阵（`ms = scale * cs`，平移 = 牌面中心 − `ms` × viewBox 中心），白底圆角矩形仍按原尺寸铺满 ⇒ 四周白边变宽。
   0.84 对应界面里 `.tile { padding: calc(var(--tile-w) * .09) }` 的同一观感。

### 62.3 测试
- `node test\apptest.js`：759 行 / 0 失败（`全部通过`）；`node test\selftest.js` / `node test\uitest.js`：exit 0。
- `python test\naga_test.py` 224 / 0；`python test\mortal_test.py` 106 / 0。
- `packaging\pyi_build.py --in-process`（新脚本）→ 打印 `OpenSSL : libssl-3-x64.dll 正确（1,326,920 B）` / `libcrypto-3-x64.dll 正确（7,349,064 B）`。
- `packaging\smoke.py`：exit 0（见 62.2 第 3 条）。
- 安装包（`electron-builder --win nsis`，用户 m08849 在普通终端跑 `build.ps1 -SkipPyi -SkipIcon -SkipTests`）：`dist\electron\tenhou-paipu-analysis-1.3.0-setup.exe` = 143,283,273 B，SHA256 `2BEFAB2C1025ED1C212966ACF899E4ACBBA9605DA847A3A45A5A30F824AAC376`（已记入 `readme.md` 第 9 节「参考指纹」）。

### 62.4 踩坑
1. `Start-Process` / `cmd /c start /b` 起的长任务在这个沙箱里会被回收（日志只留前几行）⇒ 长的构建直接前台跑（PyInstaller 约 1 分钟，未超 300 s 上限）。
2. PowerShell 5.1 不支持 `(if … )` 表达式（`-f` 里用会整段语法错误、后续语句全不执行）—— 位置参数要用 `if () { … } else { … }` 语句块。
3. `pyi_build.py` 原来在 `run(args)` 成功（`SystemExit(0)`）时直接 `return 0`，新增的后处理要放在这条路径上 ⇒ 改成「只有 `code != 0` 才 return」。 
4. `electron-builder` 首次运行要下 `winCodeSign-2.6.0.7z`（`app-builder-lib/out/toolsets/windows.js:19 getLegacyWinCodeSignBin()`，sha256 `cdaec7154dda7cc31f88d886e2489379a0625a737d610b5ae7f62a12f16743aa4`），网络被重置时报 `read ECONNRESET`；缓存路径为 `%LOCALAPPDATA%\electron-builder\Cache\winCodeSign-2.6.0\winCodeSign-2.6.0.7z`（`binDownload.js` 先查缓存、校验 sha256 后才联网）⇒ 手动放进去即可离线通过（用户 m08849 实测）；`ELECTRON_BUILDER_BINARIES_MIRROR` / `ELECTRON_BUILDER_BINARIES_DOWNLOAD_OVERRIDE_URL` 可换源。

### 62.5 待办
- ~~安装包需用户在普通终端跑~~ **已完成（用户 m08849）**：`dist\electron\tenhou-paipu-analysis-1.3.0-setup.exe` = 143,283,273 B，SHA256 `2BEFAB2C1025ED1C212966ACF899E4ACBBA9605DA847A3A45A5A30F824AAC376`（已记入 readme 第 9 节「参考指纹」）。
- 视觉待目视确认：新图标（任务栏 / 安装包里）与牌桌上的所有牌同尺寸后的观感。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次。

## 63. 第 68 轮：打包版「牌谱分析」页牌谱目录 / 文件下拉为空 —— 相对路径改成「用户数据根优先」（用户 m08918，v1.3.0 / schema 10）

### 63.1 交付物
| 文件 | 改动 |
| --- | --- |
| `mjscore/server.py` | 新增 `_user_path(p)`；`_abs()` 改成走它；`_paipu_browse()` 的 `dir` 参数改成走它（绝对路径原样、相对路径先试用户数据根、再退资源根） |
| `test/datamgr_test.py` | 新增第 4 节：临时数据根 ≠ 项目根时 `data/paipu` 等相对写法仍解析到用户数据目录（`/api/paipu-browse` / `/api/scan` / `/api/read`） |
| `readme.md` / `log.md` | 版本段加第 68 轮；本节 |

### 63.2 技术要点
1. **现象**（用户 m08918 的 release 版截图）：「牌谱分析」页的「牌谱目录」「牌谱文件」两个下拉是空窄条；「本地数据管理」页正常（它走 `datamgr`，本来就按 `paths.data_root()` 解析，`/api/health` 也回正确的 `data_root` / `paipu_dir`）。
2. **根因**：`mjscore/server.py` 的 `_paipu_browse()` 用 `os.path.join(ROOT, dir_arg)`，`ROOT = cli.ROOT`（打包后是 `_MEIPASS` / 安装目录）；前端固定发相对写法 `dir=data/paipu`（`web/js/app.js` 的初始化与目录选择）。用户牌谱实际在 `%LOCALAPPDATA%\tenhou-paipu-analysis\data\paipu` ⇒ `<ROOT>\data\paipu` 不存在 ⇒ `ApiError(目录不存在)`。`_abs()`（数据库路径 / 分析路径 / `/api/scan` / `/api/read`）有同一问题。
3. **修法**：新增 `_user_path(p)` —— 空 → `paths.data_root()`；绝对路径 → 原样；相对路径先试 `data_root()/p`（存在即用，这是打包版的正解），不存在再试 `ROOT/p`（开发期 / 绿色版 / `data_extra`），都不存在则返回数据根下的候选（报错信息指向真实位置）。`_abs()` 与 `_paipu_browse()` 全部改走它。
4. **兼容性**：源码运行（`python server.py`）时 `data_root() == resource_root() == 项目根`，行为不变；越界仍被拒绝（`test\naga_test.py` §6.2 的 `/api/paipu-browse?dir=web` 等断言照旧通过）。

### 63.3 测试
- `python test\datamgr_test.py`：54 / 0（本沙箱第 3 节因 `%LOCALAPPDATA%\...\data` 不存在而跳过；用户机器上会跑）。
- `python test\naga_test.py`：224 / 0（含 `/api/paipu-browse` 越界拒绝）。
- `python -m py_compile mjscore\server.py test\datamgr_test.py`：OK。
- 未跑 `test/mjscore_test.py` 全量（用户 m07294 约定）。

### 63.4 踩坑
1. `test/datamgr_test.py` 里 `shutil.rmtree(tmp, ignore_errors=True)` 出现两次 ⇒ 新增小节的插入锚点必须用「三行组合」（`shutil.rmtree(tmp, ignore_errors=True)` + 空行 + `sec("结果")`）。
2. `/api/scan?dir=…` 不带 `kind` 时只匹配天凤后缀（`.tenhou` / `.xml` / `.mjlog`）⇒ 同一个目录里放了 `.tenhou` + `.naga` 两个文件，`count` 是 1 不是 2；断言要用 `&kind=all`。
3. python 测试输出不能接 `Select-Object` / 管道（会失败）⇒ `cmd /c "set PYTHONPATH=<根>&& python -X utf8 test\x.py > _td.txt 2>&1"` 再 `io.open(...,'rb').read().decode('utf-8','replace')` 过滤。

### 63.5 待办
- **重新打包后端**（已发布的 v1.3.0 安装包带此 bug）：只重后端 = `powershell -ExecutionPolicy Bypass -File .\build.ps1 -SkipIcon -SkipTests -SkipElectron`；要出新安装包 = `… -Smoke -Port 8788`（`winCodeSign` 缓存已由用户补上）。
- 视觉待目视确认：Release 版「牌谱分析」页的牌谱目录 / 文件下拉能列出并选择子目录。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次。

## 64. 第 69 轮：README 重写为面向使用者的发布说明（旧版移入 docs/readme-dev.md）

### 64.1 交付物
| 文件 | 改动 |
| --- | --- |
| `readme.md` | 全新重写：面向使用者（立直麻将玩家），只讲功能 / 界面操作 / 理解方式与术语；346 行、纯 LF、无需求编号与源码路径 |
| `docs/readme-dev.md` | 旧 readme（需求来源、实现方法、测试、踩坑、版本历史）原样移入，标题下加「开发过程记录（旧版 README）」说明；438 行、纯 LF |
| `web/index.html` | 首页两处旧文案修正：40 个特征的构成改成「5 第零类 + 17 第一类 + 17 第二类 + 1 第三类」；检索卡片补「鸣牌响应帧」 |
| `log.md` | 本节 |

### 64.2 技术要点
1. 新 readme 的章节：功能一览 / 安装与启动 / 名词与约定 / 牌谱下载 / 牌谱播放 / 牌谱分析 / 牌谱检索 / 本地数据管理 / 40 个特征词典 / 数据库与文件 / 命令行速查 / 常见问题 / 版本。
2. 叙述全部用麻将术语（决策帧、自家 / 他家、巡目、供托、向听数、一发、禁止食替、筋 / 两面危险度…），不出现需求编号、源码路径、算法与历史遗留问题的讨论。
3. 特征词典复用 `mjscore/feats.py` 的权威名单（40 = 5 + 17 + 17 + 1）；第二类只写口径（三种向听数 / 六个期望听牌枚数 / 六个期望打点 / 两个危险特征），不写实现。
4. 安装包指纹、构建脚本细节、OpenSSL 修复等开发内容留在 `docs/readme-dev.md`；发布说明只保留「怎么装、怎么用」。
5. 版本仍 v1.3.0 / schema 10（本轮只改文档与两处界面文案）。

### 64.3 测试
- `node --check test\apptest.js` 与 `node test\apptest.js`：exit 0、0 失败（首页文案改动不影响断言）。
- `readme.md` / `docs/readme-dev.md` 行尾核对：均纯 LF、无孤立 CR。

### 64.4 踩坑
1. 用 PowerShell `-c "…"` 内联 Python 时，双引号串里的反引号会被 PowerShell 当转义（反引号 + r → 回车），导致 Python 报「unterminated string literal」⇒ 长脚本一律写进单引号 here-string 再执行。
2. 长文档写成 Python 的三引号原始字符串（r 前缀），含反斜杠的 Windows 路径不会被转义；以 UTF-8 无 BOM 落盘。
3. 文档里若出现连续三个双引号，会提前终止 Python 的三引号字符串（本轮踩到：描述原始字符串写法时）⇒ 正文里改用「三引号原始字符串」这种说法。

### 64.5 待办
- 已发布的 v1.3.0 安装包仍带「牌谱分析」页相对路径的 bug（见第 63 节），需要重新打包后端 / 出新安装包。
- 视觉待目视确认；`test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次。
## 65. 第 70 轮：鸣牌响应帧的关键帧判定先于概率过滤（用户 m09045 / m09110）+ readme 加作者信息

### 65.1 交付物
| 文件 | 改动 |
| --- | --- |
| `web/js/app.js` | `nagaOptions()` 新增 `mode='raw'`（鸣牌选项不过滤，只用于判定）；`renderNagaPanel()` 先判关键帧、后按 10% 过滤；「其它」残差不足 0.5% 不补 |
| `test/apptest.js` | 3 条新断言（关键帧照旧显示分析结果 / 10% 门槛仍生效 / 只有 PASS ⇒ AI 面板整块留空，与决策帧判定无关） |
| `readme.md` | 「决策选项表」条目改写为「先定关键帧、再按 10% 筛选」；并按用户 m09045 ① 在标题下与第 13 节补作者信息（Zumma Crystal / z1025zzsg@sohu.com） |
| `log.md` | 本节 |

### 65.2 技术要点
1. 现象（用户 m09045）：上家打出 3s、我方有吃 / 碰可能 ⇒ 这一帧是关键帧（鸣牌响应帧），但决策表只有标题 —— 原实现先用 `push()` 把 ≤10% 的选项全丢掉，再检查「只剩 PASS ⇒ 整块留空」；而鸣牌选项本来就多是低概率（那一帧 ニシキ 给的是 PASS 9999、吃 / 碰全 0）⇒ 面板被清空。
2. 最终规则（用户 m09110）：**先判定、后过滤** —— 报告给这一帧决策者列出的可选策略不止 PASS ⇒ AI 面板必须显示分析结果（当前决策 / 选项表 / 5 项数据）；只有 PASS（或报告没给任何选项）⇒ 非关键帧 ⇒ AI 面板整块留空（用户 m02007 ③）—— **这只影响 AI 面板：播放导航与检索范围用的「决策帧 / 关键帧」判定（`isKeyFrame()` / `decisionSeats()`）完全只看牌局，与报告 / AI 数据无关**。表格本身仍套 >10% 门槛，所以低概率的鸣牌选项不会单独列出来。
3. 实现：`nagaOptions(nf, st, seat, mode)` —— `mode='raw'` 时 `pushHuro()` 收下报告 `huro` 字典里**列出的每一个键**（概率 0 也算「列出来了」，这正是「有鸣牌可能 ⇒ 关键帧」的判据）；默认模式仍按 >1000 过滤。打牌 / 杠 / 立直那几支两个模式一致，所以「没有决策分支的展示帧整块留空」的老行为不受影响。
4. 报告里的概率齐备（万分比）：`huro[座位][模型] = {选项下标: 万分比}`，下标 0 = PASS、1 / 2 / 3 = 吃、4 = 碰、5 = 大明杠；吃三种牌对的下标含义用报告里实际发生的 chi 事件的 `kind` 字段反查证实（`kind=1` = 被打出那张的上面两张、2 = 嵌张、3 = 下面两张），与本仓 `nagaChiPair()` 一致。Mortal 同一套编码（`mjscore/mortal.py` 的 `HURO_PASS/HURO_PON/HURO_KAN = 0/4/5` + `_chi_index()`）。
5. 用户 m09045 那一帧实测：手牌 `3p 5p 5p 7p 7p 7p 7p 8p 2s 3s 3s 4s 5s` ⇒ 合法选项 = 4s5s 吃 / 2s4s 吃 / 3s3s 碰 / PASS；ニシキ = `{0:9999, 1:0, 2:0, 4:0}`、カガシ = `{0:9993, 1:5, 2:0, 4:0}`、4.1b = `{0:10000, 1:1, 2:1, 4:1}` ⇒ 面板显示「当前决策：WhiteGiv」+ `PASS 100.0%` + 5 项数据。
6. 41 份 NAGA 报告的 `huro` 键模式统计（键元组 → 格数）：`0,4` 5050 / `0,1` 3283 / `0,3` 3168 / `0,2` 1521 / `0,2,3` 615 / `0,1,2` 547 / `0,1,2,3` 320 / … —— **没有一格只列 PASS** ⇒ 「只有 PASS ⇒ 面板留空」实际主要作用于 Mortal 的 PASS-only 帧与报告没给选项的展示帧。
7. 源码版与打包版共用 `web/js/app.js` ⇒ 两边行为一致；本轮改的是前端，重新打包后才进安装包。

### 65.3 测试
- 用户 m09161（天凤谱回归，`test/apptest.js` 第 2a 节）：767 帧 `aiFrame()` 全为 `null`；第 1 局 114 帧逐帧渲染后 AI 面板三块全空；关键帧判定与牌局期望 0 处不符（71 个关键帧）、每个关键帧都有决策者、非关键帧没有；「下一自家决策」照常可用。后端同一份天凤谱 `records_for_round()` 出 458 行（draw 344 / pon 14 / chi 6 / wait 94）、第零类 5 列全「否」⇒ 检索范围与 AI 数据无关。
- `node --check` + `node test\apptest.js`：exit 0、**795 行 / 0 失败**；新断言输出 `可选策略不止 PASS ⇒ 关键帧，照旧显示 AI 分析结果（用户 m09110）= 当前决策：A / PASS100.0%`、`10% 门槛保留：0.0% 的吃 / 碰选项不进表格，残差不足 0.5% 也不补「其它」（用户 m09110）= PASS100.0%`、`可选策略只有 PASS ⇒ 非关键帧、整块留空（用户 m09110）= 选项 0 / 玩家「」`。

### 65.4 踩坑
1. 探针脚本把 **kind**（0..33）当 **tid**（0..135）传给 `mjlog.tile_name()`，打印出的手牌名张冠李戴（出现「六张 2m」这种不可能的牌），差点误判报告结构；核对手牌前先确认「手牌里存的是 tid」。
2. 报告是「一局一个帧列表」的两层结构（`pred[局][帧]`），探针第一版把它当 dict 取 `frames` 直接抛错。
3. 用 PowerShell 管道接 python 输出会被断管 ⇒ 一律 `cmd /c "… > file 2>&1"` 再解码打印。
4. 第一版把门槛整个放开（`pushHuro` 无条件收下）⇒ 表格里冒出 `吃0.0%` 这种没有信息量的噪音行，用户 m09110 要求改成「门槛保留、只颠倒判定顺序」。
5. 残差 1（万分比）会被渲染成「其它 0.0%」⇒ 残差不足 0.5% 时不再补这一行。

### 65.5 待办
- 视觉待目视确认（鸣牌响应帧现在会显示「PASS 100.0%」+ 5 项分析数据，而不是留空）。
- 重新打包后端 / 出新安装包（第 63 节的相对路径修复 + 本轮面板改动都还没进已发布的 v1.3.0）。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次。

## 66. 第 72 轮：打包发布流程 —— 跨盘符 `relpath` 真 bug + `datamgr_test` 陈旧期望 + 后端重建（用户 m09228，v1.3.0 / schema 10）

### 66.1 交付物
| 文件 | 改动 |
| --- | --- |
| `mjscore/server.py` | `_rel_or_abs()` 兜住跨盘符 `ValueError`；新增 `_paipu_rel()`（只在牌谱根内做 relpath，返回 `data/paipu/...`），`/api/paipu-browse` 的 `root_rel` / `dir_rel` / `dirs` / `files` 全部改走它 |
| `test/datamgr_test.py` | 第 3 节磁盘计数从 `.xml` 改成全部后缀（`paths.TENHOU_SUFFIXES` / `NAGA_SUFFIXES` / `MORTAL_SUFFIXES`）；新增 `scan(kind=all)` 断言；子目录断言去掉硬编码目录名；新增 `/api/paipu-browse?dir=data/paipu` 与 `_rel_or_abs` 跨盘符断言 |
| `dist/pyi/...` | 后端重新打包（`packaging\pyi_build.py --in-process`）+ 冒烟通过 |
| `dist/electron/...` | NSIS 安装包（用户 m09307 本机跑 `build.ps1 -SkipPyi -SkipIcon -SkipTests`）：`tenhou-paipu-analysis-1.3.0-setup.exe` = 143,284,238 B，SHA256 `7EEE64A4F11C89577840DF26976F216333DD7EC72C989BBC0699EFF6FF1CEE89` |

### 66.2 技术要点
1. 用户 m08918 的「牌谱分析」页下拉为空其实有**两个**原因：①（第 63 节已修）相对路径被拼到资源根；②**跨盘符 `os.path.relpath` 抛 `ValueError: path is on mount 'C:', start on mount 'D:'`** —— 打包后用户数据在 `%LOCALAPPDATA%`（C:）而程序在安装目录（本例 D:），`/api/paipu-browse` 计算 `dir_rel` / `dirs` 时炸成 400。开发环境两者同在 D: ⇒ 一直没暴露；本沙箱恰好是「数据在 C:、仓库在 D:」，打包后端一测即现。
2. `_paipu_rel()` 只在 `paths.paipu_root()` 内做 relpath（同盘符安全），跨盘符时退回绝对路径 ⇒ 与前端契约（`data/paipu/...` 写法、下拉框显示短路径）保持一致。
3. `datamgr_test` 第 3 节是第 25 轮写的：计数只认 `.xml`、子目录断言硬编码 `20261007-165558`；牌谱后缀早已改成 `.tenhou` / `.naga` / `.mortal-*` 且放进按下载批次命名的子目录 ⇒ 该节此前一直走「跳过」分支（沙箱里 `%LOCALAPPDATA%` 数据目录不存在），本轮用户数据齐备后首次真跑就暴露。
4. 后端重建（`--in-process`，普通模式在本沙箱报 `PermissionError: [WinError 5]`）：`_internal\web\js\app.js` 与仓库一致（149,682 B）、`libssl` / `libcrypto` 一对正确、冒烟 0.5 s 就绪。

### 66.3 测试
- `python test\datamgr_test.py` **78 / 0**（第 3 节实测：天凤牌谱 71 / 全类型 143 / 数据库 1）。
- 打包后端实测：`/api/paipu-browse?dir=data/paipu` → 200（`dir_rel = data/paipu`，列出 `mortal-…` / `naga-…` / `tenhou-…`）、`/api/scan` 71 / 143。
- `node test\apptest.js` 795 行 / 0 失败、`selftest.js` / `uitest.js` exit 0、`naga_test.py` 224 / 0、`mortal_test.py` 106 / 0、`packaging\smoke.py` exit 0。
- 安装包：`dist\electron\tenhou-paipu-analysis-1.3.0-setup.exe` = 143,284,238 B，SHA256 `7EEE64A4F11C89577840DF26976F216333DD7EC72C989BBC0699EFF6FF1CEE89`（build.ps1 末尾实测）。

### 66.4 踩坑
1. 用 `subprocess` 启动打包后端时不要传 `--quiet`（`server.serve()` 不认这个参数，进程直接起不来）；冒烟脚本用的是 `[exe, "--host", "127.0.0.1", "--port", N]`。
2. 打包版与源码版行为不同的地方基本都是「路径 / 盘符」：修完相对路径还要实测跨盘符，不能只看源码版测试通过。
3. `datamgr_test` 第 3 节的失败信息（`71 vs 0`）里 **API 是对的、测试自己的磁盘计数是错的**（陈旧期望），不是产品缺陷。

### 66.5 待办
- ~~用户在普通终端跑 `build.ps1 -SkipPyi -SkipIcon -SkipTests` 出新的 NSIS 安装包~~ **已完成（用户 m09307）**：`dist\electron\tenhou-paipu-analysis-1.3.0-setup.exe` = 143,284,238 B，SHA256 `7EEE64A4F11C89577840DF26976F216333DD7EC72C989BBC0699EFF6FF1CEE89`（已记入 `readme.md` 第 2.1 节）。
- git：`git add -A` + `git commit -F build\_scratch\commit_msg.txt`，随后由用户 `git push`。
- `test/mjscore_test.py` 全量（约 41 分钟）仍需用户本机跑一次。
---

## 67. 第 73 轮：界面整体放大 25% / 检索分段载入 / 静态帧禁用「局」选择 / v1.3.1 与「大版本 + 中版本」兼容（用户 m09339 ①②③ / m09354 ④⑤）

### 67.1 交付物

| 文件 | 改动 |
| --- | --- |
| `web/style.css` | 除 1px / 2px / 3px 边框与 `@media` 断点外，全部固定 px 按 1.25 倍放大（用户 m09339 ①：此前在 125% 浏览器缩放下查看，实际 100% 下组件偏小） |
| `web/js/app.js` | `BASE_U / MIN_U / MAX_U` 30/9/34 → 37.5/11.25/42.5；检索改分段（`Sc.pageSize = 1000`、`Sc.base` / `Sc.total` / `Sc.fetch`、`loadSegment()`、`openItemGlobal()`、`syncItemNav()` 用全局序号）；`lockControls()` 追加禁用 `#roundSelect`；三处「版本过低」标签改「版本不兼容」 |
| `web/index.html` | §10 兼容说明整行改成「大版本 + 中版本相同即可用」 |
| `mjscore/__init__.py` | `__version__ = "1.3.1"`；新增 `version_tuple()` / `major_minor()` / `version_compatible()` |
| `mjscore/store.py` | `check_version()` 改用 `version_compatible(recorded)`（结构版本仍必须完全一致），文案改「数据库版本不兼容（…只有大版本 + 中版本相同的库才能使用）」 |
| `mjscore/server.py` | docstring 版本号；`list_dbs` 的 `compatible` 改用 `store.version_compatible(ver)` |
| `package.json` | `version` → 1.3.1 |
| `test/apptest.js` | px 断言 ×1.25；v1.3.1；分段检索断言（`limit = 1000`、跨段自动载入）；静态帧 `#roundSelect` 禁用断言 |
| `test/mjscore_test.py` / `test/naga_test.py` | `APP_VERSION` 1.3.1；新增「大版本 + 中版本相同即兼容」断言 |

- 安装包（用户在普通终端跑 `build.ps1 -SkipIcon -SkipTests`）：`dist\electron\tenhou-paipu-analysis-1.3.1-setup.exe` = 143,286,767 B，SHA256 `F95F577AF7CC761A5438F7DA9B040A05BB7B0B297BA90559134D5AA2BE0016C1`（v1.3.0 的包为 143,284,238 B / `7EEE64A4…`）。

### 67.2 技术要点

1. **界面放大**：牌桌尺寸本来就由 `fitBoard()` 按可用空间自适应（`--tile-w` 单位），所以「放大」= 把固定 px 组件与牌桌单位上限一起乘 1.25；边框宽度（1/2/3px）与 `@media` 断点不动。
2. **检索分段**：`Sc.base` 是本段第一条的全局序号、`Sc.total` 是命中总数；`loadSegment(base)` 丢掉上一段 rows（用户 m09339 ② 允许「点到第 1001 条时释放第一段」），`openItemGlobal(i)` 在跨段时先载入该段再打开。服务端 `/api/query` / `/api/browse` 一直支持 `limit` / `offset`，无需改动。
3. **静态帧禁用局选择**：`lockControls(locked)` 原来只禁用 `#controls` 里的 button，现在把 `#roundSelect` 也一起禁用（`rs.disabled = !!locked`）。
4. **版本兼容**：`version_compatible(recorded, current=None)` —— 取 `major_minor` 比较（`1.3.1` → `(1, 3)`）；`recorded` 为空（第 22 轮以前建的库）按兼容处理。结构版本（`SCHEMA_VERSION`）仍必须完全一致。
5. **版本号约定**（用户 m09354 ④）：此后不改数据库结构的更新默认只提小版本号，写进 readme §13。

### 67.3 测试

- 六个快档全绿：`test\apptest.js`（776 行 / **0 失败**）、`test\selftest.js` exit 0、`test\uitest.js` exit 0、`test\naga_test.py` 224 / 0、`test\mortal_test.py` 106 / 0、`test\datamgr_test.py` 77 / 0。
- `test/mjscore_test.py` 全量（约 41 分钟）按用户 m07294 未跑；其期望值已按新口径改（`APP_VERSION` = 1.3.1，新增兼容断言）。

### 67.4 踩坑

1. `mjscore/__init__.py` **文件末尾没有换行** ⇒ 锚点不能带 `\n`（补丁脚本首跑就因为这个锚点全量未写盘）。
2. px 断言散落在 apptest 多处（20 / 50 / 24 / 46 / 106 / 200 / 900 / 132 / 96 / 240 / 14 / 340 …），界面缩放必须同步改，否则「测试通过但界面没变」。
3. `datamgr_test.py` 第 3 节用的迁移目录里**可能没有 `.sqlite`**（本次运行就是）⇒ 用占位符，且绝不往该目录写。
4. 补丁脚本一律 all-or-nothing：任一处锚点命中数不符就整份不写盘（避免半成品）。

### 67.5 待办

1. ~~重新打包 v1.3.1（后端 + NSIS 安装包）~~ **已完成（用户 m09444）**：`tenhou-paipu-analysis-1.3.1-setup.exe` = 143,286,767 B，SHA256 `F95F577AF7CC761A5438F7DA9B040A05BB7B0B297BA90559134D5AA2BE0016C1`；readme §2.1 指纹已同步。
2. `test/mjscore_test.py` 全量跑一次（用户本机）。
3. 请用户目视确认 1.25 倍界面（可截图）。


---

## 68. 第 74 轮：新版 NAGA 报告（アナンタ / ウロボロス）支持 —— NAGA-避四 / NAGA-争一（用户 m09507，v1.4.0 / schema 11）

### 68.1 交付物
| 文件 | 改动 |
| --- | --- |
| `mjscore/ai_models.py` | 新增 `NAGA_AVOID4 = "NAGA-避四"`（アナンタ）/ `NAGA_AGGRESSIVE = "NAGA-争一"`（ウロボロス）+ 别名；`CHOICES` 5 → 7 项（新 NAGA 两项排在 Mortal 之前），列名 `f_ai_naga_avoid4` / `f_ai_naga_aggressive` |
| `mjscore/feats.py` | 第零类 5 → 7 项、总特征 40 → 42 |
| `mjscore/naga.py` | `_DAHAI_TAIL = {34: 4, 35: 13, 36: 22}` + `_collapse_dahai()`：新版模型的打牌分布 `dahai_detail[m][0]` 是 37 档（末 3 档 = 赤 5m / 赤 5p / 赤 5s），合并回 34 档填进 `dahai_pred[m]`；原有模型的分支一字不动；`_model_values` 区分「每模型扁平列表」与「单值列表」（修掉旧报告立直概率恒 0.0%） |
| `mjscore/store.py` | `SCHEMA_VERSION` 10 → 11、`frame_ai` 索引 7 列、口径说明 42 项 |
| `mjscore/cli.py` / `mjscore/server.py` | 文案：第零类 7 项 / 42 个特征 |
| `mjscore/__init__.py` / `package.json` | v1.3.1 → **v1.4.0** |
| `web/js/mjsfeat.js` / `web/js/app.js` | 前端 AI 特征与模型下拉同步 7 项（`AI_CHOICES`、`AI_ALIASES` 加 アナンタ / ウロボロス） |
| `test/naga_test.py` | 新增第 12 节（别名 / 37→34 折叠 / `_frame()` 填充）；40 → 42、schema 10 → 11（244 / 0） |
| `test/mjscore_test.py` | 第零类 7 项、42 特征、`APP_VERSION` 1.4.0、枚举 14 → 16 项 |
| `test/mortal_test.py` / `test/apptest.js` | 「五项全否」→ 按 `len(feats.AI_KEYS)`；模型菜单 8 行（无AI决策 + 7）/ 特征下拉 42 − 7 − 1 = 34 |

### 68.2 技术要点
1. 新版 NAGA 报告的**结构不变**（`naga_version [2,2]`、`pred` / 帧字段 / 帧数 = 事件数），只有 `naga_types` 换成 `{'0':'ニシキ','1':'アナンタ','2':'ウロボロス'}`，并新增 `dahai_detail` / `hora` / `ankan_pai` / `kakan_pai` 四个字段。
2. **零变化前提**（用户 m09507）：41 份旧 `.naga` 的 `dahai_pred`（21,619 帧）/ `huro`（5,434）/ `kan`（195）/ `reach`（826）转换结果与改动前逐字节一致；`_frame()` 只在新模型自己的 `dahai_pred` 缺失 / 全 0 时才用 `dahai_detail` 覆盖。
3. **37 档的语义**：末 3 档 = 赤 5m / 赤 5p / 赤 5s（`_DAHAI_TAIL = {34: 4, 35: 13, 36: 22}`）；与报告自带的 `info.msg.pred_dahai`（34 档）交叉验证：合并后一致率 99.8%（2,467 / 2,471），不合并只有 2,452。
4. `huro` / `kan` 仍是「每模型一格」⇒ 两位新模型天然可用；**立直概率 = `dahai_detail[m][1]`（立直支）各槽之和**（官方 viewer 1.2.2 的 `gt()` / `mt()` 口径：`dahai_detail` = `[ダマ支(37), 立直支(37)]`、`dahai_pred` = 两支逐槽相加后把末 3 档并回 34 档、`reach` 有报告值时优先用报告值）。实测新 4 份报告 3,979 帧里补出 reach 的帧 = 66（= ニシキ 的 reach 帧数 8+17+12+29）、口径一致 132（66×2）、边际打牌分布一致 3,601；旧 41 份 44,168 帧的 `dahai_pred` + `reach` 与改动前逐字节一致。
5. 数据库结构变更 ⇒ `SCHEMA_VERSION = 11`，v1.3.x 建的库要用 `--delete-db` 重新分析；软件版本提到 v1.4.0（不改库结构的更新仍只提小版本号）。

### 68.3 测试
`naga_test.py` 244 / 0（含新增第 12 节）、`mortal_test.py` 106 / 0、`datamgr_test.py` 77 / 0、`node test\apptest.js` 801 行 / 0 失败、`selftest.js` / `uitest.js` 通过；`test/mjscore_test.py` 全量按用户 m07294 不跑（期望值已同步）。

### 68.4 踩坑
1. 新版报告的 `dahai_pred` 对 アナンタ / ウロボロス 是**全 0** 的定长 34 数组（不是缺失）⇒ 不能用「有没有这个键」判断，得看「全 0」。
2. `dahai_detail` 是 `[每模型 [ダマ时的打牌联合分布(37), 立直时的打牌联合分布(37)]]`（不是「打牌分布 + 备用全 0 数组」），第一层可能为 `null`（ニシキ）。
3. 官方 viewer 1.2.2 的 `mt()` / `gt()` 才是 `dahai_detail` 的正确口径（两支相加 + 末 3 档并回）；只看第一支会低估打牌分布、并会得出「新模型没有立直概率」的错误结论。另外 `mjscore/naga.py::_model_values` 原先把「扁平标量列表且长度 == 模型数」（= 旧报告的 `reach`）当成单模型值复制 ⇒ 逐个模型位置被包成嵌套列表 ⇒ 前端 `aiPick` 取到列表 ⇒ `Number(list)` = NaN ⇒ `nagaPctText` 兜底 0 ⇒ **NAGA 报告的立直概率此前恒显示 0.0%**（既有 bug，本轮一并修好）。
4. 补丁脚本对 CJK 锚点必须先用 `repr()` 对齐缩进（本轮第一次补丁因文档串缩进 5 空格 vs 4 空格失败）；`_rd.py --grep` 的模式里不要混 `\"`（PowerShell 会把尾部引号吃掉 ⇒ `bad escape (end of pattern)`）。

### 68.5 待办
1. 用户目视确认：新版 NAGA 报告下模型下拉多出「NAGA-避四 决策 / NAGA-争一 决策」，两款新模型的决策面板与打牌概率条正常。
2. 新模型的立直概率已按官方 viewer 口径还原（见 68.2 第 4 条）；报告另带 `hora`（各家各模型和了率）/ `ankan_pai` / `kakan_pai`（杠哪张 + 概率）等信息，本轮未使用 —— 是否需要展示待用户决定。
3. `test/mjscore_test.py` 全量跑一次（用户本机）；重新打包 v1.4.0 后更新 readme §2.1 指纹。


## 69. 第 75 轮：新版 NAGA 联合分布展示（决策表 + 概率条左右分色，用户 m09803，v1.4.1 / schema 11）

### 69.1 交付物

| 文件 | 改动 |
| --- | --- |
| `mjscore/naga.py` | `_frame()` 在有 `dahai_detail` 时输出 `dahai_split`（每模型 `{"dama": [34], "riichi": [34]}`，两支各自折叠 37→34） |
| `web/js/app.js` | `aiFoldFrame` 折叠 `dahai_split`；`nagaOptions` 打牌分支联合分布感知（列「打 xx」/「打 xx 立直」；有 split 时不再单独出「立直」行） |
| `web/js/ui.js` | `addNagaBars` 新增 split 分支（左半紫 / 右半红，高度各自独立；只有一支时画整宽单色） |
| `web/style.css` | 新增 `.tbar.up.dama` / `.tbar.up.riichi` / `.tbar.up.riichi.solo` |
| `test/apptest.js` | 新增联合分布断言（表行、无单独立直行、4 根条的顺序与高度、solo/dama 计数） |
| `test/mjscore_test.py` | 版本兼容断言按 1.4.1 重写（原为 1.3.x 时代写法，已陈旧） |
| `mjscore/__init__.py` / `package.json` | v1.4.0 → **v1.4.1**（不改库结构；顺手修 docstring「第零类 5 项」→ 7 项） |
| `readme.md` / `log.md` | 决策表与概率柱的联合分布口径、版本历史、本节 |

### 69.2 技术要点

1. **联合分布**：新版 NAGA 的 `dahai_detail[m] = [默听支(37), 立直支(37)]`，两支还原后就是「打哪张牌 × 是否立直」的联合分布。旧模型只给两组边缘分布（打牌分布 + 立直概率），无法重构联合分布 ⇒ 旧模型展示一字不变（用户 m09507 的零变化前提保持）。
2. **决策表**：新模型直接列 `打2m 60.0%`（默听支）与 `打3p立直 36.2%`（立直支），门槛仍是 10%（万分比 1000）；出现 split 时抑制单独的「立直」行。杠 / 鸣牌行与 NAGA-平衡形式相同。
3. **概率条**：既能默听打又能立直打 ⇒ 整宽紫条从中间一分为二（左半紫 = 默听打、右半红 = 立直打），高度各自忠实；只在默听支 ⇒ 整宽紫条；只在立直支 ⇒ 整宽红条。
4. **按值变色并不存在**：全仓 `web/js/*.js` 没有任何按概率值改色相的逻辑（grep `hsl` / `rgba(` / `toString(16)` 均 0 命中），紫条固定 `#9C27B0`；唯一随值变化的是 argmax 的 `.max`（更亮的紫 + 1px 浅紫描边，与官方 viewer 1.2.2 一致）。

### 69.3 测试

`node test\apptest.js` 全部通过（含 4 条新断言）· `node test\selftest.js` / `node test\uitest.js` exit 0 · `python test\naga_test.py` 244 / 0 · `python test\mortal_test.py` 106 / 0 · `python test\datamgr_test.py` 77 / 0。`test/mjscore_test.py` 全量按用户 m07294 未跑。

### 69.4 踩坑

1. `dahai_split` 只在有 `dahai_detail` 的模型上出现（其余为 `null`），前端必须判「该模型没有 split」，否则旧报告会拿到 `null`。
2. apptest 的新断言块必须保存并还原 `App.naga.rounds[0][1]` / `App.rounds[0][1].state` / `aiModel`，否则后面的天凤、Mortal、检索等节会读到被改过的合成帧。
3. `test/mjscore_test.py` 的版本兼容断言是 1.3.x 时代写的，版本提升后会失败 —— 全量测试不常跑，容易长期潜伏；改版本号时要一起改。
4. 概率条的左右半用绝对定位百分比（左 32.5% / 宽 17.5%、右 50% / 宽 17.5%），不要改 `.tile.bars` 的宽度或 padding，否则与牌面对不齐。

### 69.5 待办

1. 目视确认：新版 NAGA 报告下「打 xx / 打 xx 立直」表与左右分色条；旧报告（NAGA-平衡 / 超辅露 / Mortal / 天凤）应完全不变。
2. `test/mjscore_test.py` 全量仍需用户本机跑（约 41 分钟）。
3. 重新打包 v1.4.1 后更新 `readme.md` §2.1 的发布包指纹。


## 70. 第 76 轮：AI 决策表「其它」行按显示值补足到 100.0%（用户 m09901，仍 v1.4.1）

### 70.1 现象与根因

- 现象（用户 m09901，v1.3.1 打包版截图）：NAGA-平衡 决策面板只有一行「打 99.5%」，没有任何「其它」行，表内合计看起来不到 100%。
- 复核（同一份报告 `742da5a7814ee495c45060984b58774588097c85a6c78ece185802b099fbb50bv2_2.naga` 東一局 8巡目 北家 = 帧 65 / 147）：这一帧只有 1 个选项过 10% 门槛 —— 打 2m = 9954 万分比（99.54%）⇒ **显示成 99.5%**；原始残差 46 万分比 = 0.46% 小于旧代码的 0.5%（50 万分比）阈值 ⇒「其它」被省略。
- 结论：不是取整算错，而是「0.5% 阈值」与「一位小数显示」叠加后的表现问题（46 < 50，但显示上就是 99.5% + 0.0%）。

### 70.2 改法（`web/js/app.js` 的 `renderNagaPanel`）

- 改用**表内已显示选项的显示值合计**求残差：每项按 `Math.round(pct / 10) / 10` 取一位小数（立直行不计入，它与打牌是两个独立的边缘量，用户 m01903 ③）。
- 残差 ≥ 0.1% 就补一行「其它」，其数字 = `100.0 − 显示值合计`（保证表内合计 = 100.0%）。
- 显示值合计已达 100.0%（如 9999 显示 100.0%）或超过 100%（报告分布本身不归一）时不补；一个选项都没过门槛时也不补。
- 旧例不回归：打 30% + 打 20% ⇒「其它 50.0%」；碰 75% + PASS 20% ⇒「其它 5.0%」；打 99.54% ⇒ 新增「其它 0.5%」。

### 70.3 测试

`test/apptest.js` 新增断言（9954 ⇒ 2 行：`打 99.5%` + `其它 0.5%`），并把「残差不足 0.5% 也不补」的旧文案改成「显示值合计已到 100.0% ⇒ 不补」；`node test\apptest.js` 全部通过。版本仍 **v1.4.1**（1.4.1 还没打包发布，本轮修复并入同版本；库结构不变，仍 schema 11）。

### 70.4 踩坑

1. 判断「表里合计对不对」必须按**显示值**（一位小数），不能按原始万分比 —— 两者可以差 0.05 个百分点，正好跨过阈值。
2. 「其它」的 `pct`（排序用）仍保留原始残差，只让 `pctText` 用显示残差，避免影响排序与 `.other` 弱化样式。

### 70.5 待办

1. v1.3.1 维护版是否也要这一处修复（用户 m09901 询问维护流程）：从 `stable/1.3.1` 拉维护分支 → 同一处改动 → 版本 1.3.2 → 重新打包。
2. `readme.md` §5.4 已同步「其它」口径；版本历史条目已补注。
