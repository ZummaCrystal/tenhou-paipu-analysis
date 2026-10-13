/* app.js — 界面逻辑：视图切换 / 载入牌谱 / 逐帧播放与回退
 *
 * 依赖顺序（index.html 中已保证）：tiles.js -> mjlog.js -> replay.js -> mjsfeat.js -> ui.js -> app.js
 * 播放模型：REPLAY.buildGame(game) 得到 rounds[i] = frames[]，
 *   frames[0] 为开局帧，frames[k] 为「执行完第 k 个事件」后的状态。
 *   因此「上一步 / 下一步」= 帧下标 ±1，天然支持回退。
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  /* 「决策帧」= 有待某位玩家做出选择的帧（用户 m01903 ①②、m02007 ③、m06670）：
     摸牌后 / 鸣牌后 / 立直后 → 等待出牌（打牌 · 立直 · 杠 · 自摸 · 九种九牌流局）；
     有人打出牌后 → 只有在有人真能鸣牌 / 荣和时才算（下一次事件是鸣牌或和了）；
     立直宣言 / 新宝牌 / 和了 / 流局只是「执行 / 展示」帧，不算决策帧。
     **判据只看牌局本身，与「这一帧有没有 AI 决策概率向量」无关**（用户 m06670）：NAGA 报告覆盖
     四家时两者恰好等价；Mortal 报告只复盘一家，概率向量只出现在被复盘那一家决策的帧上 ——
     若拿「有概率向量」当判据，「上一 / 下一决策」就只会停在被复盘那一家的帧上，那等于
     「上一 / 下一自家决策」。 */
  /* 下面这个函数表示「这一帧有没有 AI 决策概率向量」（面板里除「其它」外真有选项）——
     只说明 AI 数据的有无，与上面的「决策帧」是两个概念（用户 m06670）。 */
  function nagaFrameChoices(i) {
    var rs = (App.naga && App.naga.rounds) ? App.naga.rounds[App.roundIndex] : null;
    if (!rs) { return null; }                                 // 天凤牌谱：只按帧类型判断
    var nf = rs[i];
    if (!nf) { return false; }                                // 末帧（和了 / 流局）没有 NAGA 数据
    var fr = App.rounds[App.roundIndex][i];
    /* 「有没有概率向量」的判定不随所选 AI 模型变化（用户 m04556 ①）：固定按「平衡形」那一档的报告值判断 */
    var kf = aiFoldFrame(nf, aiModelIndex());
    var list = nagaOptions(kf, fr ? fr.state : null, nagaSeatOf(kf));
    for (var k = 0; k < list.length; k++) { if (!list[k].pass) { return true; } }
    return false;
  }

  /* 摸牌帧之后是不是「自摸和了」（第 63 轮，用户 m07289 ③：能和就和，不构成决策点）。 */
  function selfTsumoAgari(frames, i) {
    var ev = frames[i] && frames[i].ev;
    if (!ev || ev.type !== 'draw') { return false; }
    var nx = frames[i + 1] && frames[i + 1].ev;
    return !!(nx && nx.type === 'agari' && nx.winner === ev.player && nx.fromWho === ev.player);
  }

  /* 这一帧有哪些座位「等待做决策」（第 63 轮，用户 m07289）——「决策帧」的判据只和状态有关，
     与牌谱里实际有没有出现鸣牌无关：
       · 摸牌帧：摸牌者（自摸和了的摸牌帧不算）；
       · 吃 / 碰后等待出牌的帧：鸣牌者（暗杠 / 加杠 / 大明杠的宣言帧不出帧）；
       · 出牌帧：这张牌「可能被他家鸣牌」时，可能鸣牌的那几家各算一个决策者 ——
         非立直家手里有同种 2 张以上（能碰 / 能大明杠），或下家有能吃的两张且吃后仍有牌可打（食替）；
       · 立直宣言帧按正常的出牌动作处理，不再单独算关键帧。
     判据与 mjscore/feats.py responders() / frames 表里 kind='wait' 的行完全一致。 */
  function decisionSeats(frames, i) {
    if (!isKeyFrame(frames, i)) { return []; }
    var fr = frames[i], ev = fr.ev;
    if (ev.type === 'draw' || ev.type === 'call') { return [ev.player]; }
    if (ev.type === 'discard' && typeof MJSFEAT.responders === 'function') {
      return MJSFEAT.responders(fr.state, ev.player, MJLOG.kindOf(ev.tile));
    }
    return [];
  }

  function isKeyFrame(frames, i) {
    if (i <= 0) { return false; }                             // 第 0 帧是配牌
    var fr = frames[i];
    var t = fr && fr.ev ? fr.ev.type : null;
    var ev = fr ? fr.ev : null;
    if (t === 'draw') {                                       // 非自摸和了的摸牌帧
      return !selfTsumoAgari(frames, i);
    }
    if (t === 'call') {                                       // 只有吃 / 碰（暗杠 / 加杠 / 大明杠不出帧）
      return ev.callType === 'chi' || ev.callType === 'pon';
    }
    if (t === 'discard') {                                    // 这张牌可能被他家鸣牌吗
      if (typeof MJSFEAT.responders !== 'function') { return false; }
      return MJSFEAT.responders(fr.state, ev.player, MJLOG.kindOf(ev.tile)).length > 0;
    }
    return false;
  }

  /* ---------------------------------------------------- 牌桌自适应缩放 */
  /* 为了让不同分辨率的显示器上观感一致，牌桌内部所有尺寸都以「一张牌的宽度 --tile-w」为单位。
     这里先把单位设成基准值量出牌桌的自然尺寸，再按可用空间等比缩放这个单位。
     面板里有几处固定像素的间隙，所以迭代两次逼近。 */
  var BASE_U = 38, MIN_U = 11, MAX_U = 43;   /* 第 73 轮：整体放大 1.25 倍（用户 m09339 ①） */

  function setTileUnit(u) {
    var st = document.documentElement && document.documentElement.style;
    if (!st || !st.setProperty) { return; }
    st.setProperty('--tile-w', u.toFixed(2) + 'px');
    st.setProperty('--tile-h', (u * 4 / 3).toFixed(2) + 'px');
  }

  function fitBoard() {
    var box = $('boardBox'), board = $('board');
    if (!box || !board) { return; }
    var w = box.clientWidth || 0, h = box.clientHeight || 0;
    if (w < 60 || h < 60) { return; }   /* 视图隐藏 / 还没排版时量不准，直接跳过 */
    var u = BASE_U, i, bw, bh, k;
    for (i = 0; i < 3; i++) {
      setTileUnit(u);
      bw = board.offsetWidth || 0;
      bh = board.offsetHeight || 0;
      if (!bw || !bh) { return; }
      k = Math.min((w - 4) / bw, (h - 4) / bh);
      u = Math.max(MIN_U, Math.min(MAX_U, u * k));
      if (Math.abs(k - 1) < 0.01) { break; }
    }
    setTileUnit(u);
  }

  var App = {
    view: 'home',
    version: '',         /* 软件版本号，来自 GET /api/features（第 52 轮起 v0.3.0）*/
    schemaVersion: 0,    /* 数据库结构版本 */
    fileName: '',
    game: null,
    naga: null,        /* 当前牌谱是 NAGA 报告时 = game.naga（帧对齐的 NAGA 数据，用户 m00080 目标 2）*/
    rounds: [],        /* rounds[i] = frames[] */
    roundIndex: 0,
    frameIndex: 0,
    selfSeat: 0,       /* = viewRot[0]：坐在下方（主视角）的那一家 */
    viewRot: [0, 1, 2, 3],  /* 展示位置 → 绝对座位：0 下（主视角）/ 1 右 / 2 上 / 3 左（用户 m03343 ②） */
    hideOthers: false,
    aiModel: -1,       /* 本帧实际生效的决策数据来源：-1 = 无AI决策（天凤式展示），其余 = 模型下标（用户 m04556 ①） */
    aiPref: '',        /* 用户的 AI 决策偏好（第零类 key；'' = 无AI决策）：跨牌谱 / 跨帧保留（用户 m06323 ③） */
    finalShown: false, /* 完场结算框是否已跳出（用户 m05131 ②）：牌谱最终帧之后再点一次「下一步」才为真 */
    /* 牌谱分析 / 牌谱检索相关状态 */
    dbName: '',        /* 当前选中的本地数据库名 */
    dbList: [],        /* 服务端 data/db 下的库 */
    items: [],         /* 当前条目列表（检索结果 或 全部浏览） */
    itemIndex: -1,     /* 当前正在查看的条目下标，-1 = 不在条目模式 */
    itemSource: '',    /* 'query' | 'browse' */
    cache: {},         /* log_id -> 牌谱文本，切换条目时避免重复下载 */
    /* 用户数据目录（来自 /api/health；用户 m00178 第 8、9 条） */
    openMode: 'browse', /* 打开方式：'browse'（浏览选择）| 'search'（按特征码搜索），互斥（用户 m03175 ④） */
    codeIndex: [],     /* 按特征码搜索用的牌谱清单（来自 /api/scan，用户 m03175 ④） */
    dataRoot: '',      /* 用户数据根目录 */
    dbDir: '',         /* data/db 的绝对路径 */
    paipuDir: ''       /* data/paipu 的绝对路径 */
  };

  /* ------------------------------------------------------------ 视图 */
  var VIEWS = { home: 'view-home', replay: 'view-replay', analyze: 'view-analyze', search: 'view-search',
                download: 'view-download', data: 'view-data' };

  function setView(name) {
    if (!VIEWS[name]) { name = 'home'; }
    App.view = name;
    for (var k in VIEWS) {
      if (Object.prototype.hasOwnProperty.call(VIEWS, k)) {
        $(VIEWS[k]).classList.toggle('hidden', k !== name);
      }
    }
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle('active', tabs[i].getAttribute('data-view') === name);
    }
    if (name === 'replay') { fitBoard(); }
    if (name === 'analyze' || name === 'search') { refreshDbs(); }
    if (name === 'data') { dmInit(); }
  }

  /* 「牌谱播放」入口（首页卡片 / 顶部页签）：牌谱检索 / 全部浏览点开的静态帧不算「牌谱播放」
     状态。静态帧模式下点「牌谱播放」先把牌谱卸载、回到等待选择的播放界面；正常播放已载入的
     牌谱只是切回播放视图。用户 m04285 ①：先前静态帧模式点页签只重画同一帧（看起来没反应），
     从首页卡片再进来还会把入口栏 / 拖放提示叠在旧牌桌上。 */
  function openReplayView() {
    if (!App.game || App.itemIndex >= 0) { resetReplay(); return; }
    setView('replay');
  }

  /* 回到「未载入牌谱」状态：清掉牌谱、退出静态帧条目模式，并把牌桌 / 工具栏 / 各面板的旧 DOM
     一并清空（否则旧牌桌会留在播放视图里，用户 m04285 ①）。App.items（检索结果 / 全部浏览的
     条目表）保留 —— 用户之后在检索页再点一行，openItem() 会重新载入该牌谱并回到条目模式。 */
  function resetReplay() {
    App.finalShown = false;
    App.game = null;
    App.rounds = [];
    App.roundIndex = 0;
    App.frameIndex = 0;
    App.naga = null;
    App.fileName = '(未命名)';
    App.itemIndex = -1;
    App.hideOthers = false;
    App.viewRot = [0, 1, 2, 3];
    App.selfSeat = 0;
    syncItemNav();
    toggleViewMenu(false);
    resetAiModel();          /* 本帧生效值回到「无AI决策」；用户偏好保留（用户 m06323 ③） */

    clearNode($('board'));
    var rs = $('roundSelect');
    if (rs) { clearNode(rs); rs.value = ''; }
    clearNode($('eventListBody'));
    var fk = $('frameKey');
    if (fk) { fk.textContent = ''; fk.title = ''; }
    $('rpFile').textContent = '';
    $('rpFile').title = '';
    $('rpFrame').textContent = '';
    var wb = $('warnBar');
    if (wb) { wb.textContent = ''; wb.classList.add('hidden'); }
    setFileInfo('未载入牌谱');

    $('rpOpenBar').classList.remove('hidden');
    showDropZone(true);
    homeMsg('请「浏览选择」一个本地牌谱（天凤 .tenhou / NAGA .naga / Mortal .mortal-a|b|c），或「按特征码搜索」已下载的牌谱。');
    setView('replay');
    syncButtons();
    syncOthers();
    syncFeatPanel();
    renderNagaPanel();
  }

  function setFileInfo(text) { $('fileInfo').textContent = text; }

  function homeMsg(text, warn) {
    var m = $('homeMsg');
    m.textContent = text || '';
    m.classList.toggle('warn', !!warn);
  }

  /* -------------------------------------------------------- 载入牌谱 */
  /* 牌谱文本有两种：天凤 xml（MJLOG.parse）与 naga 报告（服务端 /api/read 已转成
     同构 JSON，直接 JSON.parse）。用户 m00080 目标 2。 */
  function parseGameText(text) {
    if (/^\s*\{/.test(String(text || ''))) { return JSON.parse(text); }
    return MJLOG.parse(text);
  }

  function loadText(text, name) {
    App.finalShown = false;
    var game;
    try {
      game = parseGameText(text);
    } catch (err) {
      homeMsg('牌谱解析失败：' + (err && err.message ? err.message : err), true);
      setFileInfo('解析失败');
      return false;
    }
    App.naga = (game && game.naga) ? game.naga : null;
    if (!game || !game.rounds || !game.rounds.length) {
      /* 原始 NAGA 报告（顶层 pred / info，没有 rounds）说明没经过服务端转换：
         浏览器里直接解压 .json.gz 只能得到原始报告（用户 m01171 第 1 条）。 */
      if (game && (game.pred || game.info)) {
        homeMsg('这是 NAGA 报告的原始数据，需要本地服务转换：请先运行 python server.py，'
          + '再用它打印的地址打开本页。', true);
      } else {
        homeMsg(App.naga ? 'NAGA 牌谱里没有找到任何对局。' : '牌谱里没有找到任何对局（缺少 INIT 标签）。', true);
      }
      setFileInfo('未载入牌谱');
      return false;
    }

    App.game = game;
    App.fileName = name || '(未命名)';
    App.rounds = REPLAY.buildGame(game);
    App.roundIndex = 0;
    App.frameIndex = 0;
    /* 新载入的牌谱回到它自己的初始主视角：mortal = 被复盘的那一家，naga / 天凤 = 0（用户 m06323 ①） */
    setViewSeat((game.meta && typeof game.meta.viewer_seat === 'number') ? game.meta.viewer_seat : 0);
    toggleViewMenu(false);
    resetAiModel();          /* 本帧生效值先回「无AI决策」，render() 里再按偏好重选（用户 m06323 ③） */

    buildRoundSelect();
    setFileInfo(App.fileName + ' · 共 ' + game.rounds.length + ' 局');
    $('rpFile').textContent = App.fileName;
    $('rpFile').title = App.fileName;   /* 工具栏里特征码完整换行显示、不省略，title 仍是完整名（用户 m01518 ①） */
    $('rpOpenBar').classList.add('hidden');   /* 载入牌谱后收起「浏览选择 / 按特征码搜索」栏 */
    showDropZone(false);                      /* 拖放提示只在没载入牌谱时显示（用户 m03175 ⑥） */
    homeMsg('');
    setView('replay');
    render();
    fitBoard();
    return true;
  }

  /* AI 报告（NAGA：.naga / 旧 .json.gz；Mortal：.mortal-a|b|c / 旧 .mortal / 裸 .json）交给服务端转换：
     原始报告里没有 rounds / naga 结构，浏览器自己 gunzip 只会得到原始字段，
     播放视图会误报「缺少 INIT 标签」（用户 m01171 第 1 条；m05937 ③ 起 Mortal 走同一条链路，
     服务端按文件名后缀 + 内容嗅探分派）。
     天凤 .tenhou / 旧 .xml、.mjlog 仍然在本地直接解析。 */
  function isNagaFileName(name) {
    return /\.(naga|json\.gz|json|gz)$/i.test(String(name || ''));
  }

  function isMortalFileName(name) {
    return /\.mortal(-[a-z])?$/i.test(String(name || ''));
  }

  function uploadNaga(file) {
    var name = (file && file.name) || '';
    setFileInfo('读取中… ' + name);
    apiUpload('/api/naga-convert?name=' + encodeURIComponent(name), file).then(function (d) {
      loadText(d.text, name);
    })['catch'](function (e) {
      homeMsg('AI 报告（NAGA / Mortal）需要本地服务解析：请先运行 python server.py，再用它打印的地址打开本页。'
        + (e && e.message ? '（' + e.message + '）' : ''), true);
      setFileInfo('未载入牌谱');
    });
  }

  function readFile(file) {
    if (!file) { return; }
    /* 手动「浏览选择…」/ 拖入的牌谱不算静态帧（用户 m04285 ①）：退出条目模式，
       否则播放视图会一边放新牌谱、一边显示旧检索结果的「上一条目 / 下一条目」。 */
    App.itemIndex = -1;
    syncItemNav();
    var name = file.name || '';
    /* NAGA / Mortal 报告都交给服务端转换（用户 m05937 ③：两条链路共用 /api/naga-convert，
       按文件名后缀分派；.json / .gz 两种报告都可能用，服务端再做内容嗅探）。 */
    if (isNagaFileName(name) || isMortalFileName(name)) { uploadNaga(file); return; }
    setFileInfo('读取中… ' + name);
    var fr = new FileReader();
    fr.onload = function () { loadText(String(fr.result), name); };
    fr.onerror = function () {
      homeMsg('读取文件失败：' + name, true);
      setFileInfo('未载入牌谱');
    };
    fr.readAsText(file, 'utf-8');
  }

  /* 载入首页下拉框里选中的示例牌谱：走服务端接口读绝对路径。用户 m00178 第 8 条：
     数据目录固定到 %LOCALAPPDATA% 之后，fetch('data/xxx.xml') 这种相对路径必然 404
     （页面在 /web/ 下，实际请求 /web/data/xxx.xml，而 web/data 根本不存在）。 */
  /* ------------------------------------------------ 按特征码搜索 / 拖放区（用户 m03175 ④⑤⑥）
     打开牌谱有两种互斥方式：浏览选择（原生对话框 / <input type=file>）与按特征码搜索。
     搜索规则 = 连续子串完全匹配：牌谱特征码（文件名去掉扩展名）完整包含用户输入的字符串。 */

  /* 牌谱特征码 = 文件名去掉新后缀 .tenhou / .naga / .mortal-a|b|c 与旧后缀 .json.gz / .xml / .mjlog / .json / .gz
     （用户 m05545 ②） */
  function codeOf(p) {
    return baseName(p)
      .replace(/\.json\.gz$/i, '')
      .replace(/\.(tenhou|naga|mortal(-[a-z])?|xml|mjlog|json|gz)$/i, '')
      .toLowerCase();
  }

  /* 两种打开方式互斥：切到「按特征码搜索」时禁用「浏览选择…」按钮，反之亦然。
     模式存在 App.openMode 里（调用时不带参数就按当前模式刷新），并同步两个 radio 的勾选状态 ——
     浏览器里 radio 本来会互斥联动，但状态存在这里才不依赖 DOM。 */
  function syncOpenMode(mode) {
    if (mode === 'search' || mode === 'browse') { App.openMode = mode; }
    var search = App.openMode === 'search';
    $('rpModeBrowse').checked = !search;
    $('rpModeSearch').checked = search;
    $('btnPickFile').disabled = search;
    $('codeInput').disabled = !search;
    if (search) {
      if (!App.codeIndex.length) { loadCodeIndex(); }
      renderCodeResults($('codeInput').value);
      if ($('codeInput').focus) { $('codeInput').focus(); }
    } else {
      $('codeResults').classList.add('hidden');
    }
  }

  /* 搜索用的牌谱清单：data/paipu 下的天凤 .tenhou/.xml + NAGA .naga/.json.gz（递归，来自 /api/scan?kind=all） */
  function loadCodeIndex() {
    var dir = App.paipuDir || 'data/paipu';
    return api('/api/scan?dir=' + encodeURIComponent(dir) + '&kind=all').then(function (d) {
      var files = (d && d.files) || [], out = [], i;
      for (i = 0; i < files.length; i++) {
        out.push({ path: files[i], name: baseName(files[i]), code: codeOf(files[i]) });
      }
      App.codeIndex = out;
      return App.codeIndex;
    })['catch'](function () {
      App.codeIndex = [];
      return App.codeIndex;
    });
  }

  /* 结果行里的一段文本（匹配到的子串用 .code-hit 高亮，用户 m03319） */
  function codeSpan(text, cls) {
    var sp = document.createElement('span');
    if (cls) { sp.className = cls; }
    sp.textContent = text;
    return sp;
  }

  /* 结果框：高度固定、单行显示牌谱名，超长靠容器横向滚动（用户 m03175 ⑤） */
  function renderCodeResults(q) {
    var box = $('codeResults'), needle = String(q || '').trim().toLowerCase();
    clearNode(box);
    box.classList.remove('hidden');
    if (!needle) { box.classList.add('hidden'); return; }
    var hits = [], i;
    for (i = 0; i < App.codeIndex.length; i++) {
      if (App.codeIndex[i].code.indexOf(needle) >= 0) { hits.push(App.codeIndex[i]); }
    }
    if (!hits.length) {
      var none = document.createElement('div');
      none.className = 'code-none';
      none.textContent = '没有找到特征码里包含「' + needle + '」的牌谱。';
      box.appendChild(none);
      return;
    }
    var max = 200;
    for (i = 0; i < hits.length && i < max; i++) {
      var row = document.createElement('div');
      row.className = 'code-row';
      row.setAttribute('data-path', hits[i].path);
      row.setAttribute('title', hits[i].path);
      var name = hits[i].name;
      var at = name.toLowerCase().indexOf(needle);
      if (at < 0) {
        row.textContent = name;
      } else {
        /* 匹配到的子串黄色高亮（用户 m03319）；匹配是按去掉扩展名的特征码算的，
           但特征码是文件名的前缀，所以同一段子串在文件名里也找得到。 */
        if (at > 0) { row.appendChild(codeSpan(name.slice(0, at), '')); }
        row.appendChild(codeSpan(name.slice(at, at + needle.length), 'code-hit'));
        if (at + needle.length < name.length) {
          row.appendChild(codeSpan(name.slice(at + needle.length), ''));
        }
      }
      box.appendChild(row);
    }
    if (hits.length > max) {
      var more = document.createElement('div');
      more.className = 'code-none';
      more.textContent = '还有 ' + (hits.length - max) + ' 条结果，请输入更长的特征码片段。';
      box.appendChild(more);
    }
  }

  /* 点搜索结果 → 正常播放视图（不是牌谱检索的静态帧模式，用户 m03175 ⑤）：
     先把条目模式复位，否则控制面板会保持禁用、他家手牌也被强制显示。 */
  function openPaipuPath(p) {
    App.itemIndex = -1;
    App.itemSource = '';
    App.items = [];
    App.hideOthers = false;
    syncItemNav();
    $('rpOpenBar').classList.add('hidden');
    loadFromPath(p);
  }

  /* 牌桌区域的拖放提示：只在没有载入牌谱时显示（用户 m03175 ⑥） */
  function showDropZone(on) {
    var dz = $('dropZone');
    if (dz) { dz.classList.toggle('hidden', !on); }
  }

  /* 「浏览选择…」：桌面版（Electron）走主进程的原生对话框，默认打开牌谱数据根目录
     （用户 m01084：数据目录固定到 %LOCALAPPDATA% 之后，用户第一次使用时很难自己找到它）。
     浏览器里没有 window.tenhouDesktop 这个桥（<input type=file> 的初始目录无法用脚本指定），
     自动退回原来的行为 —— python server.py + 浏览器、双击 web/index.html 离线播放都不受影响。 */
  function loadFromPath(p) {
    homeMsg('正在载入 ' + baseName(p) + ' …');
    return api('/api/read?path=' + encodeURIComponent(p)).then(function (d) {
      loadText(d.text || '', baseName(p));
    })['catch'](function (err) {
      homeMsg('载入牌谱失败（' + (err && err.message ? err.message : err) + '）。', true);
      setFileInfo('未载入牌谱');
    });
  }

  function openNativePicker(defaultDir) {
    var res;
    try {
      res = window.tenhouDesktop.pickPaipuFile(defaultDir || '');
    } catch (err) {
      homeMsg('打开牌谱失败（' + (err && err.message ? err.message : err) + '）。', true);
      return;
    }
    if (!res || typeof res.then !== 'function') { return; }
    res.then(function (r) {
      if (!r || r.canceled || !r.filePath) { return; }
      loadFromPath(r.filePath);
    })['catch'](function (err) {
      homeMsg('打开牌谱失败（' + (err && err.message ? err.message : err) + '）。', true);
    });
  }

  function pickPaipuFile() {
    var bridge = window.tenhouDesktop;
    if (!bridge || typeof bridge.pickPaipuFile !== 'function') { $('fileInput').click(); return; }
    if (App.paipuDir) { openNativePicker(App.paipuDir); return; }
    /* 还没拿到 /api/health 的 paipu_dir 时补问一次，免得对话框退回系统上次的目录 */
    api('/api/health').then(function (h) {
      App.paipuDir = h.paipu_dir || '';
      openNativePicker(App.paipuDir);
    })['catch'](function () { openNativePicker(''); });
  }

  /* -------------------------------------------------------- 局下拉框 */
  function roundSummary(round) {
    var evs = round.events, i;
    for (i = evs.length - 1; i >= 0; i--) {
      if (evs[i].type === 'agari') { return '和了'; }
      if (evs[i].type === 'ryuukyoku') { return '流局'; }
    }
    return '';
  }

  function buildRoundSelect() {
    var sel = $('roundSelect');
    while (sel.firstChild) { sel.removeChild(sel.firstChild); }
    for (var i = 0; i < App.game.rounds.length; i++) {
      var r = App.game.rounds[i], init = r.init;
      var lab = MJLOG.roundLabel(init.round);
      var tail = roundSummary(r);
      var o = document.createElement('option');
      o.value = String(i);
      o.textContent = (i + 1) + '. ' + lab.bakaze + lab.kyoku + '局 '
        + init.combo + '本場' + (tail ? ' · ' + tail : '');
      sel.appendChild(o);
    }
    sel.value = String(App.roundIndex);
  }

  /* -------------------------------------------------------- 帧控制 */
  function setRound(i, frameIdx) {
    if (!App.rounds.length) { return; }
    if (i < 0) { i = 0; }
    if (i > App.rounds.length - 1) { i = App.rounds.length - 1; }
    App.finalShown = false;   /* 换局收起完场结算框（用户 m05131 ②） */
    App.roundIndex = i;
    var sel = $('roundSelect');
    if (sel.value !== String(i)) { sel.value = String(i); }
    var frames = App.rounds[i];
    var f = (frameIdx === undefined) ? 0 : frameIdx;
    App.frameIndex = Math.max(0, Math.min(frames.length - 1, f));
    render();
  }

  function setFrame(i) {
    var frames = App.rounds[App.roundIndex];
    if (!frames) { return; }
    App.finalShown = false;   /* 跳帧收起完场结算框（用户 m05131 ②） */
    if (i < 0) { i = 0; }
    if (i > frames.length - 1) { i = frames.length - 1; }
    App.frameIndex = i;
    render();
  }

  /* 「下一步 / 下一决策 / 下一自家决策」在本局内找不到目标帧时不再禁用（用户 m05277 ③）：
     当前帧还在本局内 ⇒ 跳到本局结算帧；当前帧就是本局结算帧 ⇒ 跳到下一局开局
     （最后一局的结算帧等同「完场」：跳出完场结算框）。 */
  /* 「上一步 / 上一决策 / 上一自家决策」在本局内找不到目标帧时的兜底（用户 m05350）：
     还在本局里 ⇒ 退回本局开局；已经在本局开局 ⇒ 退回上一局结算（上一局末帧）；
     第 0 局开局无处可退 ⇒ 原地不动。 */
  function prevFallback() {
    var frames = App.rounds[App.roundIndex] || [];
    if (!frames.length) { return; }
    if (App.frameIndex > 0) { setFrame(0); return; }
    if (App.roundIndex <= 0) { return; }
    var prev = App.rounds[App.roundIndex - 1] || [];
    if (!prev.length) { return; }
    setRound(App.roundIndex - 1, prev.length - 1);
  }

  function nextFallback() {
    var frames = App.rounds[App.roundIndex] || [];
    if (!frames.length) { return; }
    if (App.frameIndex < frames.length - 1) { setFrame(frames.length - 1); return; }
    if (App.roundIndex >= App.rounds.length - 1) {
      if (!App.finalShown) { App.finalShown = true; render(); }
      return;
    }
    setRound(App.roundIndex + 1, 0);
  }

  function stepKey(dir) {
    var frames = App.rounds[App.roundIndex];
    if (!frames) { return; }
    var i = App.frameIndex + dir;
    if (dir < 0) {
      for (; i > 0; i--) {
        if (isKeyFrame(frames, i)) { setFrame(i); return; }
      }
      prevFallback();   /* 本局内没有上一个决策帧（用户 m05350） */
      return;
    }
    for (; i < frames.length; i++) {
      if (isKeyFrame(frames, i)) { setFrame(i); return; }
    }
    nextFallback();   /* 本局内没有下一个决策帧（用户 m05277 ③） */
  }

  /* ------------------------------------------------ 控制面板跳转（用户 m05131 ③④） */
  /* 是否停在「整个牌谱的最终帧」（最后一局的末帧）——「下一步」在这里保持可用，
     再点一次只跳出完场结算框，不改变帧号（用户 m05131 ②）。 */
  function atGameEnd() {
    if (!App.game || !App.rounds.length) { return false; }
    var li = App.rounds.length - 1;
    if (App.roundIndex !== li) { return false; }
    var frames = App.rounds[li] || [];
    return frames.length > 0 && App.frameIndex >= frames.length - 1;
  }

  /* 「完场」= 整个牌谱的结束：跳到最后两局的最终帧并直接跳出结算框（用户 m05131 ④）。 */
  function showGameEnd() {
    if (!App.game || !App.rounds.length) { return; }
    var li = App.rounds.length - 1;
    setRound(li, (App.rounds[li] || []).length - 1);
    App.finalShown = true;
    render();
  }

  /* 某一帧由谁决策（打点视角的座位）：decisionSeats() 里优先主视角，否则取座位最小的那一家
     （用户 m05131 ④；等待鸣牌帧一行只属于一家，用户 m07289）。不是决策帧 → null。 */
  function seatOfFrame(frames, i) {
    var seats = decisionSeats(frames, i);
    if (!seats.length) { return null; }
    return (seats.indexOf(App.selfSeat) >= 0) ? App.selfSeat : seats[0];
  }

  /* 「上一 / 下一自家决策」：跳到最近一个「等待主视角做决策」的关键帧（用户 m05131 ④）。
     第 63 轮（用户 m07289 ⑤）：只有主视角本人这一帧确实要做决策才停 —— 出牌帧上等待决策的是
     「可能鸣牌」的几家，响应者不是主视角时就不算「自家」。 */
  function stepSelfKey(dir) {
    var frames = App.rounds[App.roundIndex] || [];
    for (var i = App.frameIndex + dir; i >= 0 && i < frames.length; i += dir) {
      if (decisionSeats(frames, i).indexOf(App.selfSeat) < 0) { continue; }
      setFrame(i); return;
    }
    if (dir > 0) { nextFallback(); }   /* 本局内没有下一个自家决策（用户 m05277 ③） */
    else { prevFallback(); }           /* 本局内没有上一个自家决策（用户 m05350） */
  }

  /* 完场结算框的数据（用户 m05131 ②）：最后一局末帧的分数排名。
     名字来自牌谱（天凤 meta.names / NAGA player_info），分数取末帧状态。 */
  function finalBoxRows() {
    if (!App.finalShown || App.itemIndex >= 0 || !App.game || !App.rounds.length) { return null; }
    var li = App.rounds.length - 1;
    var frames = App.rounds[li] || [];
    if (!frames.length) { return null; }
    var st = frames[frames.length - 1].state || {};
    var rows = [];
    for (var i = 0; i < 4; i++) {
      var pl = (st.players && st.players[i]) || {};
      var sc = (st.scores && typeof st.scores[i] === 'number') ? st.scores[i] : (pl.score || 0);
      rows.push({ name: pl.name || ('P' + i), score: sc });
    }
    rows.sort(function (a, b) { return b.score - a.score; });
    return rows;
  }

  /* 画完场结算框（黑底半透明 + 白字大字号）。renderBoard 每次会清空牌桌，所以在 render() 末尾重画。 */
  function renderFinalBox() {
    var rows = finalBoxRows();
    var host = $('board');
    if (!rows || !host) { return; }
    var box = document.createElement('div');
    box.className = 'final-box';
    for (var i = 0; i < rows.length; i++) {
      var r = document.createElement('div');
      r.className = 'fb-row';
      var a = document.createElement('span'); a.className = 'fb-rank'; a.textContent = (i + 1) + '位';
      var b = document.createElement('span'); b.className = 'fb-id'; b.textContent = rows[i].name;
      var c = document.createElement('span'); c.className = 'fb-score'; c.textContent = String(rows[i].score);
      r.appendChild(a); r.appendChild(b); r.appendChild(c);
      box.appendChild(r);
    }
    host.appendChild(box);
  }

  function onAct(act) {
    var frames = App.rounds[App.roundIndex] || [];
    if (act !== 'allLast') { App.finalShown = false; }   /* 离开终局浮层（用户 m05131 ②） */
    switch (act) {
      case 'first':     setFrame(0); break;
      case 'prev':
      /* 本局没有上一帧时不再禁用：退回本局开局 / 上一局结算（用户 m05350） */
      if (App.frameIndex <= 0) { prevFallback(); break; }
      setFrame(App.frameIndex - 1); break;
      case 'next':
      /* 牌谱最终帧：再点一次「下一步」跳出完场结算框（浮层，不改变帧号；用户 m05131 ②） */
      if (!App.finalShown && atGameEnd()) { App.finalShown = true; render(); break; }
      /* 本局没有下一帧时不再禁用：跳到本局结算帧 / 下一局开局（用户 m05277 ③） */
      if (App.frameIndex >= frames.length - 1) { nextFallback(); break; }
      setFrame(App.frameIndex + 1); break;
      case 'last':      setFrame(frames.length - 1); break;
      case 'prevKey':   stepKey(-1); break;
      case 'nextKey':   stepKey(1); break;
      case 'prevSelf':  stepSelfKey(-1); break;
      case 'nextSelf':  stepSelfKey(1); break;
      case 'allFirst':  setRound(0, 0); break;
      case 'allLast':   showGameEnd(); break;
      case 'prevRound': setRound(App.roundIndex - 1, 0); break;
      case 'nextRound': setRound(App.roundIndex + 1, 0); break;
      case 'others':
      if (othersLocked()) { break; }          /* 静态帧禁用（用户 m02984 ③） */
      App.hideOthers = !App.hideOthers; syncOthers(); render(); break;
      case 'view':
      if (othersLocked()) { break; }          /* 静态帧禁用（用户 m03343 ③） */
      toggleViewMenu(); break;
    }
  }

  /* -------------------------------------------------------- 渲染 */
  /* ① 显示/隐藏他家手牌：按钮文字随状态切换，隐藏时按钮高亮 */
  function othersBtn() { return $('btnOthers'); }
  /* 静态帧（牌谱检索 / 全部浏览的条目）固定显示他家手牌：隐藏了他家手牌，
     概率条与决策表会跟着空掉，看着像缺了一块（用户 m02984 ②③） */
  function othersLocked() { return App.itemIndex >= 0; }
  /* 静态帧（检索结果 / 全部浏览的条目）只允许用右上角的「上一条目 / 下一条目」跳转，
     下面的播放控制面板整块禁用（用户 m03089 ①） */
  function lockControls(locked) {
    var box = $('controls');
    if (!box) { return; }
    box.classList.toggle('locked', !!locked);
    var bs = box.querySelectorAll('button');
    for (var i = 0; i < bs.length; i++) { bs[i].disabled = !!locked; }
    /* 静态帧同时禁用右上角的「局」下拉框：只允许用「上一条目 / 下一条目」切换（用户 m09339 ③） */
    var rs = $('roundSelect');
    if (rs) { rs.disabled = !!locked; }
  }
  function syncOthers() {
    var b = othersBtn();
    if (!b) { return; }
    var locked = othersLocked();
    if (locked) { App.hideOthers = false; }
    b.disabled = locked;
    b.classList.toggle('on', App.hideOthers);
    b.textContent = App.hideOthers ? '显示他家手牌' : '隐藏他家手牌';
    b.title = locked ? '静态帧（牌谱检索 / 全部浏览）固定显示他家手牌'
      : (App.hideOthers ? '当前：他家手牌已隐藏' : '当前：他家手牌可见');
  }

  function setDisabled(act, off) {
    var b = document.querySelector('#controls button[data-act="' + act + '"]');
    if (b) { b.disabled = !!off || othersLocked(); }   /* 静态帧整块禁用（用户 m03089 ①） */
  }

  /* -------------------------------------------- 切换主视角（用户 m03343 ②）
     四家的展示位置由「旋转向量」决定：viewRot[展示位置] = 绝对座位，
     下标 0 下（主视角）/ 1 右（下家）/ 2 上（対面）/ 3 左（上家）。初始 [0,1,2,3]，
     换主视角只重排这个向量（相对方位自动保持），牌桌 / 概率条 / 决策表跟着整块刷新。 */
  function setViewSeat(seat) {
    var s = ((Number(seat) || 0) % 4 + 4) % 4;
    App.viewRot = [s, (s + 1) % 4, (s + 2) % 4, (s + 3) % 4];
    App.selfSeat = App.viewRot[0];
  }

  /* 上拉框的 4 行：按原始牌谱东 1 局的座次 東 > 南 > 西 > 北（用户 m03343 ②） */
  function viewMenuRows() {
    var g = App.game || {}, rows = [];
    var r0 = (g.rounds && g.rounds[0] && g.rounds[0].init) ? g.rounds[0].init : {};
    var oya = (typeof r0.oya === 'number') ? r0.oya
      : ((g.meta && typeof g.meta.oya === 'number') ? g.meta.oya : 0);
    var names = (g.meta && g.meta.names && g.meta.names.length) ? g.meta.names : [];
    for (var k = 0; k < 4; k++) {
      var seat = (oya + k) % 4;
      rows.push({ seat: seat, wind: ['東', '南', '西', '北'][k], name: names[seat] || ('玩家 ' + (seat + 1)) });
    }
    return rows;
  }

  function viewBtn() { return $('btnView'); }

  function renderViewMenu() {
    var box = $('viewMenu');
    if (!box) { return; }
    clearNode(box);
    var rows = viewMenuRows();
    for (var i = 0; i < rows.length; i++) {
      var row = document.createElement('div');
      row.className = 'view-row' + (rows[i].seat === App.selfSeat ? ' cur' : '');
      row.setAttribute('data-seat', String(rows[i].seat));
      row.title = '把 ' + rows[i].name + '（' + rows[i].wind + '家）放到主视角';
      var w = document.createElement('span');
      w.className = 'vw-wind';
      w.textContent = rows[i].wind + '家';
      var nm = document.createElement('span');
      nm.className = 'vw-id';
      nm.textContent = rows[i].name;
      row.appendChild(w);
      row.appendChild(nm);
      box.appendChild(row);
    }
  }

  /* 上拉框贴着「切换主视角」按钮向上弹出（用户 m03498：原先 CSS 的 right/bottom 把它钉在了
     界面右下角）。用按钮与包含块的实时位置算 left / bottom；量不到尺寸时保持 CSS 兜底值。 */
  function placeViewMenu() {
    var menu = $('viewMenu'), btn = viewBtn();
    if (!menu || !btn || !btn.getBoundingClientRect) { return; }
    var b = btn.getBoundingClientRect();
    if (!b) { return; }
    var host = menu.offsetParent;
    var hb = (host && host.getBoundingClientRect) ? host.getBoundingClientRect()
      : (($('view-replay') && $('view-replay').getBoundingClientRect) ? $('view-replay').getBoundingClientRect() : null);
    if (!hb) { return; }
    var left = b.left - hb.left;                 /* 与按钮左对齐 */
    var bottom = hb.bottom - b.top + 8;          /* 按钮上沿再往上留 8px */
    var w = menu.offsetWidth || 0;
    var maxLeft = (hb.width || 0) - w - 10;
    if (w && left > maxLeft) { left = maxLeft; }
    if (!(left > 10)) { left = 10; }
    menu.style.right = 'auto';
    menu.style.left = Math.round(left) + 'px';
    menu.style.bottom = Math.round(bottom) + 'px';
  }

  function placeViewMenuIfOpen() {
    var vm = $('viewMenu');
    if (vm && !vm.classList.contains('hidden')) { placeViewMenu(); }
  }

  function toggleViewMenu(show) {
    var box = $('viewMenu');
    if (!box) { return; }
    var hide = (show === undefined) ? !box.classList.contains('hidden') : !show;
    if (hide) { box.classList.add('hidden'); return; }
    renderViewMenu();
    box.classList.remove('hidden');
    placeViewMenu();
  }

  /* 按钮文字带上当前主视角的玩家 ID（按钮够宽，单行显示得下，用户 m03343 ②） */
  function syncViewBtn() {
    var b = viewBtn();
    if (!b) { return; }
    var rows = viewMenuRows(), cur = null;
    for (var i = 0; i < rows.length; i++) { if (rows[i].seat === App.selfSeat) { cur = rows[i]; } }
    b.textContent = cur ? ('切换主视角：' + cur.name) : '切换主视角';
    b.title = othersLocked() ? '静态帧（牌谱检索 / 全部浏览）固定把当前决策者放到主视角'
      : (cur ? ('当前主视角：' + cur.wind + '家 ' + cur.name + '（点击换人）') : '切换主视角');
  }

  function syncButtons() {
    var frames = App.rounds[App.roundIndex] || [];
    var last = frames.length - 1;
    var first = App.frameIndex <= 0;
    var end = App.frameIndex >= last;
    setDisabled('first', first);
    /* 「上一步 / 上一决策」本局内没有目标帧时也不再变灰（用户 m05350）：
       点它退回本局开局、再点退回上一局结算，兜底逻辑在 onAct / stepKey 里 */
    setDisabled('prev', false);
    setDisabled('prevKey', false);
    /* 「下一步 / 下一决策」本局内没有目标帧时也不再变灰（用户 m05277 ③）：
       点它跳到本局结算帧、再从结算帧跳到下一局开局，兜底逻辑在 onAct / stepKey 里 */
    setDisabled('next', false);
    setDisabled('nextKey', false);
    setDisabled('last', end);
    setDisabled('prevRound', App.roundIndex <= 0);
    setDisabled('nextRound', App.roundIndex >= App.rounds.length - 1);
    setDisabled('allFirst', App.roundIndex <= 0 && first);     /* 「开局」= 整个牌谱第 0 局第 0 帧（用户 m05131 ④） */
    setDisabled('allLast', atGameEnd() && App.finalShown);     /* 「完场」只在已弹出结算框时禁用（用户 m05277 ②） */
    setDisabled('prevSelf', false);
    setDisabled('nextSelf', false);
    syncViewBtn();
    var uBtn = $('btnCopyUrl');
    if (uBtn) {
      var u = paipuUrl();
      uBtn.disabled = !u;
      uBtn.title = u ? ('复制牌谱 URL：' + u) : '复制原始牌谱 URL';
    }
  }

  function render() {
    if (!App.game) { return; }
    var frames = App.rounds[App.roundIndex];
    if (!frames) { return; }
    var st = frames[App.frameIndex].state;

    /* 静态帧（牌谱检索 / 全部浏览的条目）：主视角固定切到当前决策者（用户 m03343 ③） */
    if (App.itemIndex >= 0) {
      var fs = frameSeatOf(st);
      if (fs !== null && fs !== App.viewRot[0]) { setViewSeat(fs); }
    }

    /* 每帧按偏好重选决策数据：偏好模型在这一帧有概率表就用它，否则临时退回「无AI决策」，
       等之后某一帧又有数据时自动切回（用户 m06323 ③）。 */
    syncAiModel();
    var nf = aiFrame();       /* 按所选 AI 模型折叠；无AI决策 ⇒ null（不画 AI 专属数据，用户 m04556 ①） */
    syncAiModelBtn();
    /* seat = 当前决策者：牌上方的打牌预测柱画在他手上（用户 m02007 ②）。
     * 「隐藏他家手牌」只影响别家：主视角自己的概率条与决策表照旧显示（用户 m03343 ①）。 */
    /* 大字（vocalization，用户 m03978 ②）：吃 / 碰 / 杠 / 自摸 / 荣和帧在桌面上画大字，
     * pos = 该玩家在牌桌上的展示位置（随「切换主视角」一起旋转），坐标见 ui.js 的 VOCAL_POS。 */
    var vocal = vocalForFrame();
    /* 黄框（用户 m07820 补充 2）：牌谱检索 / 全部浏览的静态帧里，本帧是「鸣牌响应局面」时，
       把主视角正在等着回应（吃 / 碰 / 杠）的那张被打出的牌用黄框标出来。
       等待帧的状态 = 该出牌事件之后 ⇒ 那张牌就是出牌者牌河的最后一张（ui.js 的 riverEl）。 */
    var mark = null;
    if (App.itemIndex >= 0 && App.items[App.itemIndex]
      && App.items[App.itemIndex].kind === 'wait') {
      var mit = App.items[App.itemIndex];
      var mfr = (App.rounds[mit.round_index] || [])[mit.frame_index];
      if (mfr && mfr.ev && mfr.ev.type === 'discard') { mark = { seat: mfr.ev.player }; }
    }
    var red = redMarkOf(st);
    UI.renderBoard($('board'), st, { selfSeat: App.selfSeat, viewRot: App.viewRot, hideOthers: App.hideOthers,
      vocal: vocal, mark: mark, next: red,
      naga: nf ? { frame: nf, seat: nagaSeatOf(nf), hideOthers: App.hideOthers } : null });

    $('rpFrame').textContent = App.frameIndex + ' / ' + (frames.length - 1) + ' 步';
    /* 静态帧里必须能看到并可复制「牌谱特征码 + 局况 + 本场 + 巡目 + 风位」 */
    var fk = $('frameKey');
    if (fk) {
      var keyText = frameKeyText();
      fk.textContent = keyText;
      fk.title = keyText ? ('点击复制：' + keyText) : '';
    }

    var wb = $('warnBar');
    if (st.warnings && st.warnings.length) {
      wb.textContent = '回放警告：' + st.warnings.join('；');
      wb.classList.remove('hidden');
    } else {
      wb.classList.add('hidden');
    }

    /* 事件列表常态显示（用户 m03175 ①：删掉右上角的勾选项） */
    UI.renderEventList($('eventListBody'), frames, App.frameIndex);

    renderFinalBox();       /* 完场结算框（用户 m05131 ②）：浮层，不参与步进 */
    syncButtons();
    syncOthers();
    syncFeatPanel();
    renderNagaPanel();
  }

  /* -------------------------------------------------------- 键盘 */
  function onKey(e) {
    if (App.view !== 'replay' || !App.game) { return; }
    var tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') { return; }
    if (e.ctrlKey || e.altKey || e.metaKey) { return; }
    var frames = App.rounds[App.roundIndex] || [];
    switch (e.key) {
      case 'ArrowLeft':  setFrame(App.frameIndex - 1); break;
      case 'ArrowRight': setFrame(App.frameIndex + 1); break;
      case 'ArrowUp':    stepKey(-1); break;
      case 'ArrowDown':  stepKey(1); break;
      case 'Home':       setFrame(0); break;
      case 'End':        setFrame(frames.length - 1); break;
      case 'PageUp':     setRound(App.roundIndex - 1, 0); break;
      case 'PageDown':   setRound(App.roundIndex + 1, 0); break;
      default:           return;
    }
    e.preventDefault();
  }

  /* ============================================ 本地服务：牌谱分析 / 牌谱检索
   * 浏览器不能随便读写本地磁盘、也拉不起 python，所以这两件事交给项目根的 server.py：
   *   GET  /api/health /api/features /api/dbs /api/scan?dir= /api/read?path=
   *        /api/analyze-progress /api/download-progress
   *   POST /api/analyze /api/query /api/browse /api/detail /api/round-frames /api/delete-db
   *        /api/frame-feats /api/download
   * 用服务打开页面（同源）时走相对路径；直接双击 index.html（file://）时退回 127.0.0.1:8770。
   */
  var API_PORT = 8770;
  var FEATURES = (typeof MJSFEAT !== 'undefined' && MJSFEAT && MJSFEAT.FEATURES) ? MJSFEAT.FEATURES : [];

  function apiBase() {
    var loc = (typeof window !== 'undefined' && window.location) || {};
    var proto = loc.protocol || '';
    if (proto === 'http:' || proto === 'https:') { return ''; }
    return 'http://127.0.0.1:' + API_PORT;
  }

  function api(path, body) {
    var opt = { method: body === undefined ? 'GET' : 'POST' };
    if (body !== undefined) {
      opt.headers = { 'Content-Type': 'application/json' };
      opt.body = JSON.stringify(body);
    }
    return fetch(apiBase() + path, opt).then(function (r) {
      return r.text().then(function (t) {
        var data = null;
        try { data = JSON.parse(t); } catch (e) { data = null; }
        if (!data) { throw new Error('本地服务返回的不是 JSON（HTTP ' + r.status + '）。'); }
        if (!r.ok || data.ok === false) { throw new Error(data.error || ('HTTP ' + r.status)); }
        return data;
      });
    }, function () {
      throw new Error('连不上本地服务（' + apiBase() + '）。请在项目根目录运行 "python server.py"，'
        + '再打开它打印的地址（不要直接用 file:// 打开本页）。');
    });
  }

  /* 上传文件字节（NAGA 报告是 gzip 二进制，塞不进 api() 的 JSON body）。
     浏览器手选 / 拖放的文件没有磁盘路径，只能把字节发给服务端转换（用户 m01171 第 1 条）。 */
  function apiUpload(path, file) {
    return fetch(apiBase() + path, { method: 'POST', body: file }).then(function (r) {
      return r.text().then(function (t) {
        var data = null;
        try { data = JSON.parse(t); } catch (e) { data = null; }
        if (!data) { throw new Error('本地服务返回的不是 JSON（HTTP ' + r.status + '）。'); }
        if (!r.ok || data.ok === false) { throw new Error(data.error || ('HTTP ' + r.status)); }
        return data;
      });
    }, function () {
      throw new Error('连不上本地服务（' + apiBase() + '）。请在项目根目录运行 "python server.py"，'
        + '再打开它打印的地址（不要直接用 file:// 打开本页）。');
    });
  }

  function bind(id, fn) {
    var el = $(id);
    if (el && el.addEventListener) { el.addEventListener('click', fn); }
  }

  function setMsg(id, text, warn) {
    var m = $(id);
    if (!m) { return; }
    m.textContent = text || '';
    m.classList.toggle('warn', !!warn);
  }

  function clearNode(node) {
    while (node && node.firstChild) { node.removeChild(node.firstChild); }
  }

  function valOf(id, dflt) {
    var el = $(id);
    var v = el ? el.value : '';
    if (v === undefined || v === null || v === '') { v = dflt; }
    return String(v).trim();
  }

  function plainRow(text, cls) {
    var d = document.createElement('div');
    d.className = cls || 'muted';
    d.textContent = text;
    return d;
  }

  function featOf(key) {
    for (var i = 0; i < FEATURES.length; i++) { if (FEATURES[i].key === key) { return FEATURES[i]; } }
    return null;
  }
  function featName(key) { var f = featOf(key); return f ? f.name : key; }
  function featHint(f) {
    if (!f) { return ''; }
    if (f.kind === 'enum') { return (f.values || []).join(' / '); }
    if (f.kind === 'float') {
      /* 第二类特征里的期望枚数 / 期望打点是实数（服务端 parse_cond 支持小数） */
      return '实数 / 区间 ' + (f.min !== undefined ? f.min : '') + '-' + (f.max !== undefined ? f.max : '')
        + ' / 列表 0,1,2.5 / 比较 >=3';
    }
    if (SHANTEN_KEYS[f.key]) {
      /* 向听数：内部取值 {-1,0,1,2,3}，3 表示「>=3 向听」，只有展示写成 >=3；
         检索条件仍按内部整数匹配（填 3 / 3-5 / >=3 都会命中内部值 3，用户 m04115②、m04182）。 */
      return '整数 / 区间 ' + (f.min !== undefined ? f.min : '') + '-' + (f.max !== undefined ? f.max : '')
        + ' / 列表 1,2,3 / 比较 >=3（内部值 3 = >=3，按整数匹配）';
    }
    return '整数 / 区间 ' + (f.min !== undefined ? f.min : '') + '-' + (f.max !== undefined ? f.max : '')
      + ' / 列表 1,2,3 / 比较 >=3';
  }

  /* 互斥取值的特征用下拉选取（取值来自 MJSFEAT.FEATURES 的 values）；整数与实数特征用文本框
     （实数可填 0.5 / 0-1.5 / 0,1,2.5 / >=3，解析在服务端 store.parse_cond） */
  function featIsEnum(f) { return !!(f && f.kind === 'enum' && f.values && f.values.length); }

  /* ------------------------------------------------------------ 牌谱分析 */
  var An = { files: [], browse: null, pickerDir: '' };

  function setAllFiles(on) {
    var box = $('anFileList');
    var cbs = (box && box.querySelectorAll) ? box.querySelectorAll('input[type="checkbox"]') : [];
    for (var i = 0; i < cbs.length; i++) { cbs[i].checked = !!on; }
  }

  function anSelected() {
    var box = $('anFileList'), out = [];
    var cbs = (box && box.querySelectorAll) ? box.querySelectorAll('input[type="checkbox"]') : [];
    for (var i = 0; i < cbs.length; i++) {
      if (cbs[i].checked && An.files[i] !== undefined) { out.push(An.files[i]); }
    }
    return out;
  }

  function renderFileList(files) {
    var box = $('anFileList');
    An.files = files || [];
    if (box) {
      clearNode(box);
      if (!An.files.length) { box.appendChild(plainRow('（这个目录里没有牌谱文件：天凤 .tenhou / .xml 或 NAGA .naga / .json.gz）', 'muted')); }
      for (var i = 0; i < An.files.length; i++) {
        var lab = document.createElement('label');
        lab.className = 'an-file';
        var cb = document.createElement('input');
        cb.setAttribute('type', 'checkbox');
        cb.checked = true;
        cb.setAttribute('data-i', String(i));
        var nm = document.createElement('span');
        nm.textContent = An.files[i];
        lab.appendChild(cb);
        lab.appendChild(nm);
        box.appendChild(lab);
      }
    }
    var cnt = $('anFileCount');
    if (cnt) { cnt.textContent = An.files.length ? ('共 ' + An.files.length + ' 个牌谱文件') : ''; }
  }

  function scanFiles() {
    var dir = valOf('anSourceDir', 'data/paipu');
    setMsg('anMsg', '正在扫描 ' + dir + ' …');
    api('/api/scan?dir=' + encodeURIComponent(dir) + '&kind=all').then(function (d) {
      renderFileList(d.files);
      setMsg('anMsg', '找到 ' + d.count + ' 个牌谱文件：（' + d.dir + '）');
    })['catch'](function (e) { setMsg('anMsg', '扫描失败：' + e.message, true); });
  }

  /* 牌谱目录 / 牌谱文件改成下拉选择（用户 m01171 第 2 条）：目录树与文件来自
     GET /api/paipu-browse，前缀固定 data/paipu；选目录后扫描整个目录，
     只选一个牌谱文件时只分析这一个。 */
  function loadPaipuPicker(dir, quiet) {
    return api('/api/paipu-browse' + (dir ? '?dir=' + encodeURIComponent(dir) : '')).then(function (d) {
      An.browse = d;
      An.pickerDir = d.dir_rel;
      var ds = $('anSourceDir');
      if (ds && ds.tagName === 'SELECT') {
        clearNode(ds);
        for (var i = 0; i < d.dirs.length; i++) {
          var op = document.createElement('option');
          op.value = d.dirs[i];
          op.textContent = d.dirs[i];
          ds.appendChild(op);
        }
        if (d.dir_rel) { ds.value = d.dir_rel; }
      }
      var fs = $('anSourceFile');
      if (fs && fs.tagName === 'SELECT') {
        clearNode(fs);
        var whole = document.createElement('option');
        whole.value = '';
        whole.textContent = '（整个目录：' + (d.dir_rel || '') + '，共 ' + d.files.length + ' 个牌谱）';
        fs.appendChild(whole);
        for (var j = 0; j < d.files.length; j++) {
          var of = document.createElement('option');
          of.value = d.files[j];
          of.textContent = baseName(d.files[j]);
          fs.appendChild(of);
        }
        fs.value = '';
      }
      return d;
    })['catch'](function (e) {
      An.browse = null;
      if (!quiet) { setMsg('anMsg', '读取牌谱目录失败：' + e.message, true); }
      return null;
    });
  }

  function anDirChanged() {
    loadPaipuPicker(valOf('anSourceDir', ''), true).then(function (d) {
      if (d) { scanFiles(); } else { setMsg('anMsg', '读取牌谱目录失败：请确认本地服务已启动。', true); }
    });
  }

  function anFileChanged() {
    var f = valOf('anSourceFile', '');
    if (f) {
      setMsg('anMsg', '只分析选中的这一个牌谱：（' + f + '）');
      renderFileList([f]);
      return;
    }
    scanFiles();
  }

  /* 软件信息：标题栏版本号 + 「--full」说明（都来自 GET /api/features） */
  function loadMeta() {
    return api('/api/features').then(function (d) {
      App.version = d.version || '';
      App.schemaVersion = d.schema_version || 0;
      var ver = $('appVer');
      if (ver) { ver.textContent = App.version ? ('v' + App.version) : ''; }
      var nm = $('brandName');
      if (nm && d.name) { nm.textContent = d.name; }
      var au = $('appAuthor');
      if (au) {
        au.textContent = d.author
          ? ((App.version ? 'v' + App.version + ' · ' : '') + d.author + (d.author_email ? ' <' + d.author_email + '>' : ''))
          : '';
      }
      var note = $('anFullNote');
      if (note && d.full_note) { note.textContent = d.full_note; }
      return d;
    })['catch'](function () { return null; });
  }

  /* 新建数据库 / 扩充现有数据库：两个入口互斥（扩充时数据库名输入框禁用） */
  function anSetMode(mode) {
    An.mode = (mode === 'extend') ? 'extend' : 'new';
    var ext = (An.mode === 'extend');
    var row = $('anExtendRow');
    if (row) { row.classList.toggle('hidden', !ext); }
    var nm = $('anDbName');
    if (nm) { nm.disabled = ext; }
    if (ext) { fillExtendSelect(App.dbList || []); }
  }

  function fillExtendSelect(dbs) {
    var sel = $('anExtendDb');
    if (!sel) { return; }
    var cur = sel.value || '';
    clearNode(sel);
    for (var i = 0; i < dbs.length; i++) {
      var o = document.createElement('option');
      o.value = dbs[i].name;
      o.textContent = dbs[i].name + '（' + ((dbs[i].meta && dbs[i].meta.record_count) || 0) + ' 行'
        + ' · ' + (dbs[i].app_version ? ('v' + dbs[i].app_version) : '版本未记录')
        + (dbs[i].compatible === false ? ' ⚠ 版本不兼容' : '') + '）';
      if (dbs[i].compatible === false) { o.disabled = true; }
      sel.appendChild(o);
    }
    if (cur) { sel.value = cur; }
    /* 极简 DOM（测试）不会自动选中第一项，这里显式兜一下；真实浏览器里 sel.value 已经等于第一项 */
    if (!sel.value && sel.childNodes.length) { sel.value = sel.childNodes[0].value; }
    anExtendInfo();
  }

  function anExtendInfo() {
    var el = $('anExtendInfo');
    if (!el) { return; }
    var sel = $('anExtendDb');
    var name = (sel && sel.value) || '';
    var db = null;
    var list = App.dbList || [];
    for (var i = 0; i < list.length; i++) { if (list[i].name === name) { db = list[i]; } }
    if (!db) { el.textContent = ''; return; }
    el.textContent = '版本 ' + (db.app_version || '未记录')
      + (db.compatible === false ? ' · ⚠ 版本不兼容，不能扩充，请删除后重新分析' : ' · 可扩充');
  }

  /* 本次分析写哪个库：新建（数据库名）或用「扩充现有数据库」选中的那个 */
  function anTargetDb() {
    if (An.mode === 'extend') {
      var sel = $('anExtendDb');
      return { db_name: (sel && sel.value) || '', extend: true };
    }
    return { db_name: valOf('anDbName', 'paipu'), extend: false };
  }

  function doAnalyze() {
    var paths = anSelected();
    if (!paths.length) { setMsg('anMsg', '请先扫描并勾选要分析的牌谱文件。', true); return; }
    var tgt = anTargetDb();
    if (tgt.extend && !tgt.db_name) {
      setMsg('anMsg', '请先在「要扩充的数据库」里选择一个数据库。', true); return;
    }
    var full = !!($('anFull') && $('anFull').checked);
    setMsg('anMsg', '正在分析 ' + paths.length + ' 个牌谱（node + python 自动）'
      + (tgt.extend ? ('，扩充 ' + tgt.db_name) : '') + '…');
    anProgressStart();
    api('/api/analyze', { paths: paths, db_name: tgt.db_name, extend: tgt.extend, full: full }).then(function (d) {
      var w = (d.warnings && d.warnings.length) ? ('；注意：' + d.warnings.join('；')) : '';
      var skip = (d.skipped && d.skipped.length) ? ('，跳过已入库 ' + d.skipped.length + ' 个牌谱') : '';
      setMsg('anMsg', '完成：' + d.logs + ' 个牌谱 / ' + d.rounds + ' 局 / 打点 ' + d.annotations
        + ' 行（库内共 ' + d.db_total + ' 行）→ ' + d.db
        + (d.extend ? ('（扩充 ' + tgt.db_name + skip + '）') : '') + w,
        !!(d.warnings && d.warnings.length));
      anProgressDone(true, '分析完成：' + d.logs + ' 个牌谱 / ' + d.rounds + ' 局 / 打点 ' + d.annotations
        + ' 行 ｜ ' + ((d.elapsed_ms || 0) / 1000).toFixed(1) + ' s');
      refreshDbs();
    })['catch'](function (e) {
      setMsg('anMsg', '分析失败：' + e.message, true);
      anProgressDone(false, '分析失败：' + e.message);
    });
  }

  function setDb(name) {
    App.dbName = name || '';
    var sel = $('scDbSelect');
    if (sel) { sel.value = App.dbName; }
    setMsg('scMsg', App.dbName ? ('当前数据库：' + App.dbName) : '');
  }

  function dbRow(db) {
    var row = document.createElement('div');
    row.className = 'db-row';
    var nm = document.createElement('b');
    nm.textContent = db.name;
    var meta = document.createElement('span');
    meta.className = 'muted';
    meta.textContent = '打点 ' + ((db.meta && db.meta.record_count) || 0) + ' 行 · '
      + ((db.meta && db.meta.tool) || '-') + ' · ' + Math.max(1, Math.round(db.size / 1024)) + ' KB'
      + ' · 版本 ' + (db.app_version || '未记录')
      + (db.compatible === false ? ' ⚠ 版本不兼容（不能扩充 / 加载）' : '');
    var use = document.createElement('button');
    use.className = 'ghost';
    use.textContent = '设为当前库';
    use.addEventListener('click', function () { setDb(db.name); });
    var del = document.createElement('button');
    del.className = 'ghost';
    del.textContent = '删除';
    del.addEventListener('click', function () {
      if (typeof window.confirm === 'function' && !window.confirm('删除数据库 ' + db.name + '？')) { return; }
      api('/api/delete-db', { db_name: db.name }).then(function () {
        setMsg('anMsg', '已删除 ' + db.name);
        refreshDbs();
      })['catch'](function (e) { setMsg('anMsg', '删除失败：' + e.message, true); });
    });
    row.appendChild(nm);
    row.appendChild(meta);
    row.appendChild(use);
    row.appendChild(del);
    return row;
  }

  function fillDbSelect(dbs) {
    var sel = $('scDbSelect');
    App.dbList = dbs || [];
    if (!sel) { return; }
    var cur = sel.value || App.dbName || '';
    clearNode(sel);
    for (var i = 0; i < App.dbList.length; i++) {
      var o = document.createElement('option');
      o.value = App.dbList[i].name;
      o.textContent = App.dbList[i].name + '（' + ((App.dbList[i].meta && App.dbList[i].meta.record_count) || 0) + ' 行'
        + (App.dbList[i].app_version ? (' · v' + App.dbList[i].app_version) : '') + '）';
      sel.appendChild(o);
    }
    if (cur) { sel.value = cur; }
    if (!App.dbName && App.dbList.length) { App.dbName = App.dbList[0].name; }
  }

  function refreshDbs() {
    return api('/api/dbs').then(function (d) {
      var box = $('anDbList');
      if (box) {
        clearNode(box);
        if (!d.dbs.length) { box.appendChild(plainRow('（还没有数据库：先在上面选牌谱并点「开始分析并入库」）', 'muted')); }
        for (var i = 0; i < d.dbs.length; i++) { box.appendChild(dbRow(d.dbs[i])); }
      }
      fillDbSelect(d.dbs);
      fillExtendSelect(d.dbs);
      return d.dbs;
    })['catch'](function (e) {
      setMsg('anMsg', '读取数据库列表失败：' + e.message, true);
      return [];
    });
  }

  /* ------------------------------------------------------------ 牌谱检索 */
  /* wait = 第三类特征（局面）必选单选（第 63 轮，用户 m07289）：'出牌'（默认）/ '鸣牌响应'。 */
  /* pageSize = 每段载入的结果条数；base = 当前段在全局结果里的起点；total = 全局命中数
     （用户 m09339 ②：结果超过一段时按段载入，翻到别的段就把上一段换掉，内存不随总数增长） */
  var Sc = { conds: [], pageSize: 1000, aiMode: '', aiPicks: {}, wait: '出牌',
             base: 0, total: 0, fetch: null };

  function scDbPayload() {
    var custom = valOf('scDbPath', '');
    if (custom) { return { db: custom }; }
    var sel = $('scDbSelect');
    var name = (sel && sel.value) || App.dbName || '';
    return name ? { db_name: name } : {};
  }

  /* ---------------------- 第零类特征（AI 分析模型）检索方案（用户 m04556 ③）----------------------
   * 第零类不参与「添加特征词条 + 填取值」的选取方式，而是四种互斥方案：
   *   任意AI决策 / NAGA决策 / Mortal决策 / 同时具有（勾选的第零类特征必须全为「是」）。
   * 与第一、二类条件一起 AND 作用于检索；不选择 = 不筛选（保持旧行为）。 */
  var AI_MODE_LIST = [
    { key: 'any', name: '任意AI决策', hint: '只要具备任意一种 AI 模型的分析结果' },
    { key: 'naga', name: 'NAGA决策', hint: '只要具备任意一种 NAGA 系列（NAGA-平衡 / NAGA-超副露 …）' },
    { key: 'mortal', name: 'Mortal决策', hint: '只要具备任意一种 Mortal 系列（Mortal-4.1-平衡 / 避四 / 争一 …）' },
    { key: 'multi', name: '同时具有', hint: '勾选的第零类特征必须全部为「是」' }
  ];

  function aiFeatures() { return MJSFEAT.AI_FEATURES || []; }

  function isAiKey(key) {                     /* 第零类特征的 key（与 mjscore/ai_models.py 的 CHOICES 一致） */
    var ai = aiFeatures();
    for (var i = 0; i < ai.length; i++) { if (ai[i].key === key) { return true; } }
    return false;
  }

  /* 第三类特征（局面）的 key（第 63 轮，用户 m07289）：只有「等待鸣牌」一项，
     不进「添加特征词条」的下拉，也不列进「当前帧特征」。 */
  function isThirdKey(key) {
    var th = MJSFEAT.THIRD_FEATURES || [];
    for (var i = 0; i < th.length; i++) { if (th[i].key === key) { return true; } }
    return false;
  }

  function aiPickedKeys() {
    var ai = aiFeatures(), out = [];
    for (var i = 0; i < ai.length; i++) { if (Sc.aiPicks[ai[i].key]) { out.push(ai[i].key); } }
    return out;
  }

  function aiPayload() {                      /* null = 不筛选 */
    if (!Sc.aiMode) { return null; }
    return { mode: Sc.aiMode, picks: (Sc.aiMode === 'multi') ? aiPickedKeys() : [] };
  }

  function setAiMode(mode) {
    Sc.aiMode = String(mode || '');
    renderAiPlan();
  }

  function setAiPick(key, on) {
    if (on) { Sc.aiPicks[key] = 1; } else { delete Sc.aiPicks[key]; }
    renderAiPlan();
  }

  function clearAiPlan() {
    Sc.aiMode = '';
    Sc.aiPicks = {};
    renderAiPlan();
    setMsg('scMsg', '');
  }

  /* 第三类特征（局面）单选（第 63 轮，用户 m07289）：与第零类方案、第一/二类条件同时满足（AND）。
     「出牌」= 只看等待出牌的局面（出牌帧）；「鸣牌响应」= 只看有人打出牌后可能鸣牌的那几家各一行的帧。 */
  function setWait(v) {
    Sc.wait = (String(v || '') === '鸣牌响应') ? '鸣牌响应' : '出牌';
    syncWaitRadios();
  }

  function waitPayload() { return (Sc.wait === '鸣牌响应') ? '鸣牌响应' : '出牌'; }

  function syncWaitRadios() {
    var modes = (document.querySelectorAll) ? document.querySelectorAll('input[name="waitMode"]') : [];
    for (var i = 0; i < modes.length; i++) { modes[i].checked = (modes[i].value === Sc.wait); }
  }

  function renderAiPlan() {
    var modesEl = $('aiModes'), picksEl = $('aiPicks');
    if (!modesEl || !picksEl) { return; }
    clearNode(modesEl);
    for (var i = 0; i < AI_MODE_LIST.length; i++) {
      (function (i) {
        var m = AI_MODE_LIST[i];
        var lab = document.createElement('label');
        lab.title = m.hint;
        var inp = document.createElement('input');
        inp.type = 'radio';
        inp.name = 'aiMode';
        inp.value = m.key;
        inp.setAttribute('data-mode', m.key);
        inp.checked = (Sc.aiMode === m.key);
        inp.addEventListener('change', function () { setAiMode(m.key); });
        lab.appendChild(inp);
        var sp = document.createElement('span');
        sp.textContent = m.name;
        lab.appendChild(sp);
        modesEl.appendChild(lab);
      })(i);
    }
    clearNode(picksEl);
    var showPicks = (Sc.aiMode === 'multi');
    picksEl.classList.toggle('hidden', !showPicks);
    if (!showPicks) { return; }
    var ai = aiFeatures();
    for (var j = 0; j < ai.length; j++) {
      (function (j) {
        var f = ai[j];
        var lab = document.createElement('label');
        lab.title = f.name;
        var inp = document.createElement('input');
        inp.type = 'checkbox';
        inp.setAttribute('data-key', f.key);
        inp.checked = !!Sc.aiPicks[f.key];
        inp.addEventListener('change', function () { setAiPick(f.key, !!this.checked); });
        lab.appendChild(inp);
        var sp = document.createElement('span');
        sp.textContent = f.name;
        lab.appendChild(sp);
        picksEl.appendChild(lab);
      })(j);
    }
  }

  function renderFeatSelect() {
    var sel = $('scFeatSelect');
    if (!sel) { return; }
    clearNode(sel);
    var used = {};
    for (var i = 0; i < Sc.conds.length; i++) { used[Sc.conds[i].key] = 1; }
    for (var j = 0; j < FEATURES.length; j++) {
      if (isAiKey(FEATURES[j].key)) { continue; }   /* 第零类走「第零类检索方案」（用户 m04556 ③） */
      if (isThirdKey(FEATURES[j].key)) { continue; }   /* 第三类走「出牌 / 鸣牌响应」单选（用户 m07289） */
      if (used[FEATURES[j].key]) { continue; }   /* 同一条特征不能重复添加 */
      var o = document.createElement('option');
      o.value = FEATURES[j].key;
      o.textContent = FEATURES[j].name;
      sel.appendChild(o);
    }
  }

  function renderConds() {
    var box = $('scCondList');
    if (!box) { return; }
    clearNode(box);
    if (!Sc.conds.length) {
      box.appendChild(plainRow('（「牌谱特征」框为空：在上方选一个特征并点「添加」，再指定它的条件）', 'muted'));
      return;
    }
    for (var i = 0; i < Sc.conds.length; i++) {
      (function (i) {
        var c = Sc.conds[i], f = featOf(c.key);
        var row = document.createElement('div');
        row.className = 'cond-row';
        var nm = document.createElement('label');
        nm.textContent = (i + 1) + '. ' + featName(c.key);
        var inp;
        if (featIsEnum(f)) {
          /* 互斥取值的特征：下拉选取（第一项是占位项，值为空 = 还没选择） */
          inp = document.createElement('select');
          inp.className = 'cond-ctl cond-select';
          var ph = document.createElement('option');
          ph.value = '';
          ph.textContent = '请选择';
          inp.appendChild(ph);
          for (var vi = 0; vi < f.values.length; vi++) {
            var op = document.createElement('option');
            op.value = String(f.values[vi]);
            op.textContent = String(f.values[vi]);
            inp.appendChild(op);
          }
          inp.value = c.expr || '';
        } else {
          inp = document.createElement('input');
          inp.type = 'text';
          inp.className = 'cond-ctl cond-input';
          inp.value = c.expr || '';
          inp.placeholder = featHint(f);
        }
        inp.setAttribute('data-key', c.key);
        inp.addEventListener('input', function () { c.expr = String(this.value || '').trim(); });
        inp.addEventListener('change', function () { c.expr = String(this.value || '').trim(); });
        var del = document.createElement('button');
        del.className = 'ghost';
        del.textContent = '删除';
        del.addEventListener('click', function () {
          Sc.conds.splice(i, 1);
          renderConds();
          renderFeatSelect();
        });
        row.appendChild(nm);
        row.appendChild(inp);
        row.appendChild(del);
        box.appendChild(row);
      })(i);
    }
    markUsedFeatures();
  }

  function collectConds() {
    var box = $('scCondList'), out = [];
    for (var i = 0; i < Sc.conds.length; i++) {
      out.push({ key: Sc.conds[i].key, expr: String(Sc.conds[i].expr || '').trim() });
    }
    /* 以 DOM 里的当前值为准（防止某些浏览器不触发 input 事件） */
    var inputs = (box && box.querySelectorAll) ? box.querySelectorAll('.cond-ctl') : [];
    for (var j = 0; j < inputs.length; j++) {
      var k = inputs[j].getAttribute('data-key');
      for (var m = 0; m < out.length; m++) {
        if (out[m].key === k && inputs[j].value) { out[m].expr = String(inputs[j].value).trim(); }
      }
    }
    return out;
  }

  function addFeat() {
    var sel = $('scFeatSelect');
    var key = sel ? sel.value : '';
    if (!key) { setMsg('scMsg', '请先选择一个牌谱特征再点「添加」。', true); return; }
    for (var i = 0; i < Sc.conds.length; i++) {
      if (Sc.conds[i].key === key) { setMsg('scMsg', '「' + featName(key) + '」已经添加过了。', true); return; }
    }
    Sc.conds.push({ key: key, expr: '' });
    renderConds();
    renderFeatSelect();
    setMsg('scMsg', '已添加「' + featName(key) + '」，请'
      + (featIsEnum(featOf(key)) ? '在下拉里选择' : '填写') + '它的检索条件。');
  }

  function clearConds() {
    Sc.conds = [];
    renderConds();
    renderFeatSelect();
    setMsg('scMsg', '');
    var box = $('scResultList');
    if (box) { clearNode(box); }
    var info = $('scResultInfo');
    if (info) { info.textContent = ''; }
  }

  function checkConds() {
    if (!Sc.conds.length) {
      /* 只选第零类方案也能检索（用户 m04556 ③）：两者都空才拦住 */
      if (!aiPayload()) {
        setMsg('scMsg', '请先添加并填写「牌谱特征」条件，或在上方选择一个「第零类特征」检索方案。', true);
        return null;
      }
      return [];
    }
    var conds = collectConds();
    for (var i = 0; i < conds.length; i++) {
      if (!conds[i].expr) { setMsg('scMsg', '「' + featName(conds[i].key) + '」的条件还没'
        + (featIsEnum(featOf(conds[i].key)) ? '选择' : '填写') + '。', true); return null; }
    }
    return conds;
  }

  function renderResults(rows) {
    var box = $('scResultList');
    if (box) {
      clearNode(box);
      for (var i = 0; i < rows.length; i++) {
        (function (i) {
          var r = rows[i];
          var b = document.createElement('button');
          b.className = 'item-row';
          b.setAttribute('data-i', String(i));
          b.textContent = r.label;
          b.title = r.url || '';
          b.addEventListener('click', function () { openItem(i); });
          box.appendChild(b);
        })(i);
      }
    }
    var info = $('scResultInfo');
    if (info) {
      if (!rows.length) { info.textContent = ''; }
      else {
        var total = Sc.total || (Sc.base + rows.length);
        info.textContent = '第 ' + (Sc.base + 1) + ' ~ ' + (Sc.base + rows.length) + ' 条（共 ' + total
          + ' 条）' + (total > rows.length ? '；翻段时自动载入' : '');
      }
    }
  }

  function runQuery() {
    var conds = checkConds();
    if (!conds) { return; }
    markUsedFeatures();
    var dbq = scDbPayload();
    if (!dbq.db && !dbq.db_name) { setMsg('scMsg', '请先选择（或填写）要检索的本地数据库文件。', true); return; }
    var ai = aiPayload();                      /* 第零类检索方案（用户 m04556 ③），null = 不筛选 */
    var wait = waitPayload();                  /* 第三类特征（局面）单选（用户 m07289），默认「出牌」 */
    var dbid = dbq.db || null, dbname = (dbq.db || null) ? null : dbq.db_name;
    /* 分段载入（用户 m09339 ②）：同一套条件可以反复按 offset 取，翻段时复用 */
    Sc.fetch = function (offset) {
      return api('/api/query', { conds: conds, limit: Sc.pageSize, offset: offset,
        ai: ai, wait: wait, db: dbid, db_name: dbname });
    };
    setMsg('scMsg', '检索中…');
    Sc.fetch(0).then(function (d) {
      App.items = d.rows || [];
      Sc.base = 0;
      Sc.total = (typeof d.total === 'number') ? d.total : App.items.length;
      App.itemIndex = -1;
      App.itemSource = 'query';
      renderResults(App.items);
      syncItemNav();
      setMsg('scMsg', '命中 ' + Sc.total + ' 个打点帧（条件：' + (d.used || []).join('、')
        + '）。点条目跳转到对应帧；条目名＝牌谱特征码 + 局况 + 本场 + 巡目 + 风位。'
        + (Sc.total > Sc.pageSize ? '结果多于 ' + Sc.pageSize + ' 条：用「上一条目 / 下一条目」翻到下一段时自动载入。' : ''));
    })['catch'](function (e) { setMsg('scMsg', '检索失败：' + e.message, true); });
  }

  function browseAll() {
    var dbq = scDbPayload();
    if (!dbq.db && !dbq.db_name) { setMsg('scMsg', '请先选择（或填写）要浏览的本地数据库文件。', true); return; }
    var dbid = dbq.db || null, dbname = (dbq.db || null) ? null : dbq.db_name;
    /* 全部浏览同样按段载入（用户 m09339 ②）：库大时一次读全部会很慢 */
    Sc.fetch = function (offset) {
      return api('/api/browse', { limit: Sc.pageSize, offset: offset, db: dbid, db_name: dbname });
    };
    setMsg('scMsg', '正在读取全部条目…');
    Sc.fetch(0).then(function (d) {
      App.items = d.rows || [];
      Sc.base = 0;
      Sc.total = (typeof d.total === 'number') ? d.total : App.items.length;
      App.itemIndex = -1;
      App.itemSource = 'browse';
      renderResults(App.items);
      syncItemNav();
      setMsg('scMsg', '全部浏览：共 ' + Sc.total + ' 个打点帧（按牌谱特征码顺序）。点任意条目进入阅图模式，'
        + '再用「上一条目 / 下一条目」切换。'
        + (Sc.total > Sc.pageSize ? '（每段 ' + Sc.pageSize + ' 条，翻段时自动载入）' : ''));
    })['catch'](function (e) { setMsg('scMsg', '读取失败：' + e.message, true); });
  }

  /* --------------------------------------------------- 条目导航 / 跳转 */
  function syncItemNav() {
    var info = $('itemInfo'), p = $('btnPrevItem'), n = $('btnNextItem');
    var on = App.itemIndex >= 0 && App.items.length > 0;
    var gi = Sc.base + App.itemIndex;                  /* 全局条目号（跨分段，用户 m09339 ②） */
    var total = Sc.total || (Sc.base + App.items.length);
    if (info) {
      info.classList.toggle('hidden', !on);
      var kindName = '';
      if (on) {
        var k = String(App.items[App.itemIndex].kind || 'draw');
        kindName = '｜ ' + (k === 'chi' ? '吃后帧' : (k === 'pon' ? '碰后帧' : (k === 'wait' ? '鸣牌响应帧' : '摸牌帧')));
      }
      info.textContent = on ? ('条目 ' + (gi + 1) + ' / ' + total
        + '（' + (App.itemSource === 'browse' ? '全部浏览' : '检索结果') + '）' + kindName) : '';
    }
    if (p) { p.classList.toggle('hidden', !on); p.disabled = !on || gi <= 0; }
    if (n) { n.classList.toggle('hidden', !on); n.disabled = !on || gi >= total - 1; }
    syncOthers();       /* 静态帧（条目模式）固定显示他家手牌：按钮禁用状态跟着 itemIndex 走 */
    lockControls(on);   /* 静态帧：下面的播放控制面板整块禁用（用户 m03089 ①） */
  }

  function installGame(text, logId) {
    loadText(text, logId + '.tenhou');
  }

  function jumpRow(it) {
    var ri = parseInt(it.round_index, 10);
    if (!(ri >= 0) || ri >= App.rounds.length) { setMsg('scMsg', '这个条目所在的对局不在牌谱里。', true); return; }
    /* 条目模式（静态帧）强制显示他家手牌，退出条目模式后自动恢复（用户 m02984 ③） */
    App.hideOthers = false;
    toggleViewMenu(false);
    App.roundIndex = ri;
    var frames = App.rounds[ri];
    var fi = parseInt(it.frame_index, 10);
    if (!(fi >= 0)) { fi = 0; }
    if (fi > frames.length - 1) { fi = frames.length - 1; }
    App.frameIndex = fi;
    buildRoundSelect();
    var sel = $('roundSelect');
    if (sel) { sel.value = String(ri); }
    setView('replay');
    render();
    fitBoard();
  }

  function openItem(i) {
    if (!(i >= 0) || i >= App.items.length) { return; }
    var it = App.items[i];
    App.itemIndex = i;
    syncItemNav();
    var logId = it.log_id;
    if (App.game && gameLogId() === String(logId)) { jumpRow(it); setMsg('scMsg', ''); return; }
    if (App.cache[logId]) { installGame(App.cache[logId], logId); jumpRow(it); setMsg('scMsg', ''); return; }
    setMsg('scMsg', '正在载入牌谱 ' + logId + ' …');
    api('/api/read?path=' + encodeURIComponent(it.log_path || ('data/' + logId + '.tenhou'))).then(function (d) {
      App.cache[logId] = d.text;
      installGame(d.text, logId);
      jumpRow(it);
      setMsg('scMsg', '');
    })['catch'](function (e) { setMsg('scMsg', '载入牌谱失败：' + e.message, true); });
  }

  /* 分段载入 / 跨段跳转（用户 m09339 ②）：i 是**全局**条目下标；不在当前段就换段
     （换段 = 丢掉上一段的 rows，只保留当前段，内存不随结果总数增长）。 */
  function loadSegment(base) {
    if (!Sc.fetch) { return null; }
    if (App.items.length && base === Sc.base) { return null; }   /* 已在内存 */
    setMsg('scMsg', '正在载入第 ' + (base + 1) + ' 条起的结果…');
    return Sc.fetch(base).then(function (d) {
      App.items = d.rows || [];
      Sc.base = base;
      if (typeof d.total === 'number') { Sc.total = d.total; }
      renderResults(App.items);
      return App.items.length;
    })['catch'](function (e) { setMsg('scMsg', '载入失败：' + e.message, true); return 0; });
  }

  function openItemGlobal(i) {
    if (!(i >= 0) || (Sc.total && i >= Sc.total)) { return; }
    var base = Math.floor(i / Sc.pageSize) * Sc.pageSize;
    if (App.items.length && base === Sc.base) { openItem(i - base); return; }
    var pend = loadSegment(base);
    if (!pend) { openItem(i - base); return; }
    pend.then(function (n) { if (n) { openItem(i - base); } });
  }

  function stepItem(dir) {
    if (App.itemIndex < 0) { return; }
    openItemGlobal(Sc.base + App.itemIndex + dir);
  }

  /* ------------------------------------------------ 静态帧的特征串 */
  function gameLogId() {
    var n = String(App.fileName || '');
    return n
      .replace(/\.json\.gz$/i, '')
      .replace(/\.(tenhou|naga|mortal(-[a-z])?|xml|mjlog|json|gz)$/i, '')
      || '(未命名)';
  }

  /* 与 mjscore/feats.py row_label() 保持同一格式：
     「牌谱特征码 局况 本场 巡目 风位家」，例如
     「2026083021gm-00a9-0000-d0810acf 東三局 0本場 3巡目 西家」 */
  function frameKeyText() {
    if (!App.game) { return ''; }
    var frames = App.rounds[App.roundIndex];
    if (!frames || !frames[App.frameIndex]) { return ''; }
    var st = frames[App.frameIndex].state;
    /* 条目模式：直接用数据库里的同一条记录，保证与检索结果逐字一致 */
    var it = (App.itemIndex >= 0) ? App.items[App.itemIndex] : null;
    if (it && String(it.log_id) === gameLogId()
        && parseInt(it.round_index, 10) === App.roundIndex
        && parseInt(it.frame_index, 10) === App.frameIndex) {
      return it.label;
    }
    /* 手动播放：先判断当前帧是「摸牌帧」还是「吃/碰后等待出牌的帧」，再按同一口径现算 */
    var seat = frameSeatOf(st);
    if (seat === null) { return ''; }
    var mine = (st.players || [])[seat];
    if (!mine) { return ''; }
    var junme = (mine.turns || 0) + 1;   /* 巡目 = 该家已出牌次数 + 1 */
    var jou = MJLOG.joukyokuLabel(st.round);
    var wind = REPLAY.seatWind(seat, st.oya);
    return gameLogId() + ' ' + jou + ' ' + st.honba + '本場' + ' ' + junme + '巡目' + ' ' + wind + '家';
  }

  /* 复制文本到剪贴板（clipboard API + execCommand 兜底）；成功后给 node 加 .copied 700ms */
  function copyTextTo(text, node) {
    if (!text) { return false; }
    var done = function () {
      if (!node || !node.classList) { return; }
      node.classList.add('copied');
      window.setTimeout(function () { node.classList.remove('copied'); }, 700);
    };
    var fallback = function () {
      var ta = document.createElement('textarea');
      ta.value = text;
      if (node) { node.appendChild(ta); }
      if (ta.select) { ta.select(); }
      try { if (document.execCommand) { document.execCommand('copy'); } } catch (e) { /* 忽略 */ }
      if (node) { node.removeChild(ta); }
      done();
    };
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
    return true;
  }

  function copyFrameKey() {
    var el = $('frameKey');
    if (!el) { return; }
    copyTextTo(el.textContent || '', el);
  }

  /* 原始牌谱 URL（用户 m03479 ① / m05937 ③）：天凤 = tenhou.net 的观战页、NAGA = 官网 naga.dmv.nico
     的观看页、Mortal = mjai.ekyu.moe 的报告 JSON 地址。
     ricochet 代理地址不还原（NAGA 牌谱复制出来的是「naga 开头」的地址）。 */
  function paipuUrl() {
    var g = App.game;
    var meta = (g && g.meta) ? g.meta : null;
    var id = (meta && meta.log_id) ? String(meta.log_id) : '';
    if (!id) { id = gameLogId(); }        /* 天凤 xml 的 meta 里没有 log_id ⇒ 用文件名里的特征码 */
    if (!id || id === '(未命名)') { return ''; }
    if (App.naga) {
      var rid = App.naga.report_id ? String(App.naga.report_id) : id;
      if (App.naga.kind === 'mortal') {     /* Mortal 报告 = mjai.ekyu.moe 的报告 JSON（用户 m05937 ③） */
        return 'https://mjai.ekyu.moe/report/' + rid + '.json';
      }
      return 'https://naga.dmv.nico/htmls/report_viewer.html?report_id=' + rid + '&tw=0';
    }
    return 'http://tenhou.net/0/?log=' + id + '&tw=0';
  }

  function copyUrl() {
    var btn = $('btnCopyUrl');
    var url = paipuUrl();
    if (!url) { return; }
    copyTextTo(url, btn);
    if (btn) {
      btn.textContent = '已复制';
      window.setTimeout(function () { btn.textContent = '复制url'; }, 700);
    }
  }


  /* 细红框（用户 m08125 ② / m08178 / m08319 ①）：本帧决策者接下来要做的事 ——
 *   打牌（立直宣言算打出的宣言牌）→ 即将打出的那一张（只给 kind，ui.js 按紫色条那套筛选逻辑挑一张）；
 *   暗杠 / 加杠 → 准备杠的 4 张（暗杠 = 手里 4 张，加杠 = 手里 1 张 + 副露区那 3 张，给准确 id）。
 * 第 66 轮（用户 m08319 ①）起不再限定主视角：谁在这一帧做决策（frameSeatOf）就把框画在谁手里 ——
 * 静态帧的主视角本来就会被调成决策者，所以静态帧看起来依旧是「框主视角」，限定主视角只是表现形式。
 * 决策者本帧没有要打的牌（鸣牌响应局面、别家出牌后的等待帧等）一律 null。
 * frames[k].ev = events[k - 1] ⇒ 下一事件 = events[App.frameIndex]。 */
function redMarkOf(st) {
  if (!st || !App.game) { return null; }
  var r = App.game.rounds[App.roundIndex];
  var self = frameSeatOf(st);
  if (!r || typeof self !== 'number') { return null; }
  var evs = r.events || [];
  var ev = evs[App.frameIndex];
  if (!ev || ev.player !== self) { return null; }
  if (ev.type === 'reach') { ev = evs[App.frameIndex + 1]; }
  if (ev && ev.type === 'discard' && ev.player === self) {
    return { seat: self, kind: MJLOG.kindOf(ev.tile), tids: [], melds: [] };
  }
  if (ev && ev.type === 'call' && ev.player === self
    && (ev.callType === 'ankan' || ev.callType === 'kakan')) {
    var ts = ev.tiles || [];
    if (!ts.length) { return null; }
    var kind = MJLOG.kindOf(ts[0]);
    var pl = st.players[self];
    var hand = [], melds = [];
    var seq = pl.hand.slice();
    if (st.drawn && st.drawn.player === self) { seq.push(st.drawn.tile); }
    for (var i = 0; i < seq.length; i++) {
      if (MJLOG.kindOf(seq[i]) === kind && hand.indexOf(seq[i]) < 0) { hand.push(seq[i]); }
    }
    for (var m = 0; m < pl.melds.length; m++) {
      var mm = pl.melds[m];
      if (mm.callType === 'pon' && mm.tiles.length && MJLOG.kindOf(mm.tiles[0]) === kind) {
        melds = mm.tiles.slice();
        break;
      }
    }
    return { seat: self, kind: kind, tids: hand, melds: melds };
  }
  return null;
}

/* ------------------- 帧特征面板（40 个特征里的 34 个：不含第零类 5 项与第三类 1 项） */
  /* 当前帧的「打点视角」座位（第 63 轮，用户 m07289）：
     条目模式（检索结果）直接用它那一行的 seat —— 等待鸣牌帧一张出牌对应好几行、各家一行；
     正常播放则取 decisionSeats() 里优先主视角、否则座位最小的那一家；不是决策帧 → null。 */
  function frameSeatOf(st) {
    if (!st) { return null; }
    var it = (App.itemIndex >= 0) ? App.items[App.itemIndex] : null;
    var itSeat = it ? parseInt(it.seat, 10) : NaN;
    if (it && itSeat >= 0 && String(it.log_id) === gameLogId()
      && parseInt(it.round_index, 10) === App.roundIndex
      && parseInt(it.frame_index, 10) === App.frameIndex) {
      return itSeat;
    }
    var frames = App.rounds[App.roundIndex] || [];
    return seatOfFrame(frames, App.frameIndex);
  }
  /* ------------- AI 决策模型切换（用户 m04556 ①）-------------
   * NAGA 报告里 dahai_pred / huro / reach / kan 的外层是「模型」维（naga_types 的档，
   * 例：{'0':'ニシキ','1':'アナンタ','2':'ウロボロス'}）。App.aiModel = -1 表示「无AI决策」：
   * 不画任何 AI 专属数据（= 天凤牌谱的展示方式，用户 m04556 ①）。 */
  var AI_CHOICES = [
    { key: 'ai_balance', name: 'NAGA-平衡', label: 'NAGA-平衡 决策' },
    { key: 'ai_superhuro', name: 'NAGA-超副露', label: 'NAGA-超副露 决策' },
    { key: 'ai_naga_avoid4', name: 'NAGA-避四', label: 'NAGA-避四 决策' },
    { key: 'ai_naga_aggressive', name: 'NAGA-争一', label: 'NAGA-争一 决策' },
    { key: 'ai_mortal41a', name: 'Mortal-4.1-避四', label: 'Mortal-4.1-避四 决策' },
    { key: 'ai_mortal41b', name: 'Mortal-4.1-平衡', label: 'Mortal-4.1-平衡 决策' },
    { key: 'ai_mortal41c', name: 'Mortal-4.1-争一', label: 'Mortal-4.1-争一 决策' }
  ];
  /* 与 mjscore/ai_models.py 的 ALIASES 保持一致：报告里 naga_types 的值 → 规范名 */
  var AI_ALIASES = {
    'ニシキ': 'NAGA-平衡', 'カガシ': 'NAGA-超副露',
    'アナンタ': 'NAGA-避四', 'ウロボロス': 'NAGA-争一',   /* 用户 m09507 */
    'ヒバカリ': 'NAGA-ヒバカリ', 'オメガ': 'NAGA-オメガ', 'ガンマ': 'NAGA-ガンマ',
    'ニュー': 'NAGA-ニュー', 'シグマ': 'NAGA-シグマ',
    '4.1a': 'Mortal-4.1-避四', '4.1b': 'Mortal-4.1-平衡', '4.1c': 'Mortal-4.1-争一'
  };

  function aiNormalize(raw) {
    var t = String(raw === null || raw === undefined ? '' : raw).trim();
    if (!t) { return ''; }
    if (AI_ALIASES[t]) { return AI_ALIASES[t]; }
    var _mv = /^(\d+(?:\.\d+)?)([a-z]?)$/i.exec(t);
    if (_mv) {                                  /* 4.1a 避四 / 4.1b 平衡 / 4.1c 争一（用户 m05806 ①） */
      var _ms = { a: '避四', b: '平衡', c: '争一' }[(_mv[2] || '').toLowerCase()];
      return 'Mortal-' + _mv[1] + '-' + (_ms || '平衡');
    }
    return t;
  }

  function aiModelList() {                    /* [{index, raw, name, series}]（后端 game.naga.models 优先） */
    var naga = App.naga;
    if (!naga) { return []; }
    if (naga.models && naga.models.length) { return naga.models; }
    var types = naga.types || {}, out = [];
    for (var k in types) {
      if (!Object.prototype.hasOwnProperty.call(types, k)) { continue; }
      var idx = Number(k);
      if (!isFinite(idx)) { continue; }
      var nm = aiNormalize(types[k]);
      out.push({ index: idx, raw: types[k], name: nm, series: nm ? nm.split('-')[0] : '' });
    }
    out.sort(function (a, b) { return a.index - b.index; });
    return out;
  }

  function aiChoiceOf(models) {               /* 三个第零类模型在本牌谱里是否可用（缺 ⇒ index = -1） */
    var map = {};
    for (var i = 0; i < models.length; i++) { map[models[i].name] = models[i]; }
    var out = [];
    for (var j = 0; j < AI_CHOICES.length; j++) {
      var m = map[AI_CHOICES[j].name] || null;
      out.push({ key: AI_CHOICES[j].key, name: AI_CHOICES[j].name, label: AI_CHOICES[j].label,
        index: m ? m.index : -1 });
    }
    return out;
  }

  function aiModelIndex() {                   /* 「平衡形」在模型列表里的下标（关键帧判定用，与所选模型无关） */
    var mi = App.naga ? App.naga.model_index : null;
    if (typeof mi === 'number' && mi >= 0) { return mi; }
    var models = aiModelList();
    return models.length ? models[0].index : -1;
  }

  /* 把「每模型」的值折叠到第 idx 个模型：dahai_pred / reach / kan 是「每模型」，huro 是「每座位 × 每模型」。
     形状容错：非数组 / 旧式扁平数组（外层不是模型维）原样返回。 */
  function aiPick(v, idx, models) {
    if (v === null || v === undefined) { return v; }
    if (!(v instanceof Array)) { return v; }
    if (!v.length) { return v; }
    var first = v[0];
    var perModel = (first && typeof first === 'object');
    if (!perModel && v.length === models.length) { perModel = true; }   /* 标量数组：长度 == 模型数 */
    if (!perModel) { return v; }
    return (idx >= 0 && idx < v.length) ? v[idx] : null;
  }

  function aiFoldFrame(nf, idx) {             /* 把一帧折叠到第 idx 个模型（不改原对象） */
    if (!nf) { return null; }
    var models = aiModelList();
    if (idx < 0 && models.length) { idx = models[0].index; }
    var out = {};
    for (var k in nf) { if (Object.prototype.hasOwnProperty.call(nf, k)) { out[k] = nf[k]; } }
    out.dahai_pred = aiPick(nf.dahai_pred, idx, models) || [];
    /* 新版 NAGA 的联合分布（用户 m09803）：每模型一份 { dama:[34], riichi:[34] } */
    out.dahai_split = aiPick(nf.dahai_split, idx, models) || null;
    out.reach = aiPick(nf.reach, idx, models);
    out.kan = aiPick(nf.kan, idx, models) || {};
    var huro = {}, src = nf.huro || {};
    for (var s in src) {
      if (!Object.prototype.hasOwnProperty.call(src, s)) { continue; }
      var one = aiPick(src[s], idx, models);
      if (one) { huro[s] = one; }
    }
    out.huro = huro;
    return out;
  }

  function aiFrame() {                        /* 当前帧按所选模型折叠后的数据；-1 = 无AI决策 ⇒ null */
    if (App.aiModel < 0) { return null; }
    return aiFoldFrame(nagaFrameOf(), App.aiModel);
  }

  /* ------------- AI 决策偏好：按帧判定 + 跨牌谱保留（用户 m06323 ②③、m06560）-------------
   * App.aiPref = 第零类 key（'' = 无AI决策）= 「用户最后一次的选择」，跨牌谱 / 跨帧保留；
   * App.aiModel = 本帧实际生效的模型下标（偏好在这一帧没有决策概率表 ⇒ -1，临时显示「无AI决策」）。
   * 一帧有没有某个模型的数据，与后端 mjscore/feats.py 的 _model_has_data() 同口径（用户 m06560）：
   * 数据属于**这一帧的决策者**（nagaSeatOf）—— 帧级 dahai_pred / reach / kan 属于这一帧的 actor，
   * huro 只看决策者自己那一格。 */

  function aiKeyOfIndex(idx) {                /* 模型下标 → 第零类 key（'' = 认不出） */
    if (typeof idx !== 'number' || idx < 0) { return ''; }
    var list = aiChoiceOf(aiModelList());
    for (var i = 0; i < list.length; i++) {
      if (list[i].index === idx && list[i].index >= 0) { return list[i].key; }
    }
    return '';
  }

  function aiPrefIndex(pref) {                /* 偏好 key → 本牌谱里的模型下标（-1 = 本牌谱没有这个模型） */
    if (!pref) { return -1; }
    var list = aiChoiceOf(aiModelList());
    for (var i = 0; i < list.length; i++) {
      if (list[i].key === pref && list[i].index >= 0) { return list[i].index; }
    }
    return -1;
  }

  function anyVal(v) {                        /* {下标: 万分比} 里有没有非 0 值（标量则直接比 0） */
    if (!v || typeof v !== 'object') { return Number(v) > 0; }
    for (var k in v) {
      if (Object.prototype.hasOwnProperty.call(v, k) && Number(v[k]) > 0) { return true; }
    }
    return false;
  }

  function aiFrameHasData(nf, idx, models) {  /* 这一帧的**决策者**有没有第 idx 个模型的概率表（用户 m06560 口径） */
    if (!nf || typeof idx !== 'number' || idx < 0) { return false; }
    /* 席位要用「折叠到该模型」后的 huro 判：原始帧的 huro 是每座位 x 每模型（每格一个列表），
       在这里算不出吃 / 碰 / 杠的最大项，会退化成 actor（第 64 轮，用户 m07820 ① 口径 (a)）。 */
    var seat = nagaSeatOf(aiFoldFrame(nf, idx));
    if (typeof seat !== 'number') { return false; }
    if (nf.actor === seat) {   /* 帧级预测（打哪张 / 立直 / 杠）属于这一帧的 actor = 决策者 */
      var dp = aiPick(nf.dahai_pred, idx, models);
      if (dp && dp.length) { return true; }
      if (Number(aiPick(nf.reach, idx, models)) > 0) { return true; }
      if (anyVal(aiPick(nf.kan, idx, models))) { return true; }
    }
    var hu = nf.huro || {};    /* huro 只看决策者自己那一格 */
    return anyVal(aiPick(hu[String(seat)], idx, models));
  }

  function aiFrameKeys(nf) {                  /* 这一帧带决策概率表的模型 key 列表（与入库判定同口径） */
    var models = aiModelList(), out = [];
    if (!nf) { return out; }
    for (var i = 0; i < models.length; i++) {
      if (aiFrameHasData(nf, models[i].index, models)) { out.push(aiKeyOfIndex(models[i].index)); }
    }
    return out;
  }

  function syncAiModel() {                    /* 每帧把偏好落到可用模型上（用户 m06323 ③） */
    var pref = App.aiPref || '';
    var idx = pref ? aiPrefIndex(pref) : -1;
    if (idx >= 0) {
      var models = aiModelList();
      if (!aiFrameHasData(nagaFrameOf(), idx, models)) { idx = -1; }   /* 这一帧没数据 ⇒ 临时「无AI决策」 */
    }
    App.aiModel = idx;
    syncAiModelBtn();
  }

  function setAiPref(key) {                   /* 直接记偏好（'' = 无AI决策）并立刻按本帧可用性重画 */
    App.aiPref = key || '';
    syncAiModel();
    toggleAiModelMenu(false);
    if (App.game) { render(); }
  }

  function resetAiModel() {                   /* 只重置「本帧生效值」，不动用户偏好（用户 m06323 ③） */
    App.aiModel = -1;
    toggleAiModelMenu(false);
    syncAiModelBtn();
  }

  function setAiModel(idx) {                  /* 菜单点击：记偏好 + 按本帧可用性立刻生效 */
    App.aiPref = (typeof idx === 'number' && idx >= 0) ? aiKeyOfIndex(idx) : '';
    syncAiModel();
    toggleAiModelMenu(false);
    if (App.game) { render(); }
  }


  function syncAiModelBtn() {
    var b = $('nagaModelBtn');
    if (!b) { return; }
    var list = aiChoiceOf(aiModelList()), cur = null, prefRow = null, n = 0;
    var pref = App.aiPref || '';
    for (var i = 0; i < list.length; i++) {
      if (list[i].index >= 0) { n++; }
      if (list[i].index === App.aiModel && list[i].index >= 0) { cur = list[i]; }
      if (pref && list[i].key === pref && list[i].index >= 0) { prefRow = list[i]; }
    }
    b.textContent = cur ? cur.label : '无AI决策';
    if (App.aiModel < 0) {
      if (prefRow) {   /* 偏好还在、只是这一帧没有数据 ⇒ 临时「无AI决策」，之后自动切回（用户 m06323 ③） */
        b.title = '本帧没有 ' + prefRow.label + ' 的决策数据；已记住偏好，之后有数据的帧会自动切回';
      } else if (n) {
        b.title = '当前：无AI决策（本牌谱含 ' + n + ' 个 AI 模型的决策数据，点击切换）';
      } else {
        b.title = '当前：无AI决策（本牌谱不含 AI 决策数据）';
      }
    } else {
      b.title = '当前：' + b.textContent + '（点击切换；「无AI决策」= 天凤牌谱的展示方式）';
    }
  }

  function renderAiModelMenu() {
    var box = $('nagaModelMenu');
    if (!box) { return; }
    clearNode(box);
    var list = aiChoiceOf(aiModelList());
    var models = aiModelList(), nf = nagaFrameOf();
    var pref = App.aiPref || '';
    var rows = [{ label: '无AI决策', index: -1, ok: true, key: '', hasData: true }];
    for (var i = 0; i < list.length; i++) {
      rows.push({ label: list[i].label, index: list[i].index, ok: list[i].index >= 0, key: list[i].key,
        hasData: (list[i].index < 0) ? false : aiFrameHasData(nf, list[i].index, models) });
    }
    for (var j = 0; j < rows.length; j++) {
      var cur = pref ? (rows[j].key === pref) : (rows[j].index === -1);   /* 高亮的是「偏好」而不是生效值 */
      var row = document.createElement('div');
      row.className = 'ai-row' + (rows[j].ok ? '' : ' disabled') + (cur ? ' cur' : '');
      row.setAttribute('data-index', String(rows[j].index));
      row.textContent = rows[j].label;
      if (!rows[j].ok) {
        row.title = rows[j].label + '：本牌谱没有这个模型的分析结果';
      } else if (!rows[j].hasData) {
        row.title = rows[j].label + '：本帧没有决策数据（选中后记成偏好，有数据的帧会自动切回）';
      } else {
        row.title = rows[j].label;
      }
      box.appendChild(row);
    }
  }

  function toggleAiModelMenu(show) {
    var box = $('nagaModelMenu');
    if (!box) { return; }
    var hide = (show === undefined) ? !box.classList.contains('hidden') : !show;
    if (hide) { box.classList.add('hidden'); return; }
    renderAiModelMenu();
    box.classList.remove('hidden');
  }

  // ---------------- NAGA 决策概率展示（用户 m00198 / m01518 ③）----------------
  // 数据来自 mjscore/naga.py 转换后的 game.naga.rounds[局][帧]，帧下标与 App.frameIndex 对齐
  // （naga 帧 j 携带的正是我们 events[j] 要兑现的那个决策）。非 NAGA 牌谱时一切留空。
  function nagaFrameOf() {
    if (!App.naga || !App.naga.rounds) { return null; }
    var rs = App.naga.rounds[App.roundIndex];
    if (!rs || App.frameIndex >= rs.length) { return null; }
    return rs[App.frameIndex] || null;
  }

  /* 大字（vocalization，用户 m03978 ②）：官方 viewer 的 replay 状态机在吃 / 碰 / 杠帧给状态对象写
   * vocalization = チー / ポン / カン（再由 renderBa 用 900 字重画在桌面上）；和了帧官方从结算信息
   * 取「ツモ / ロン」。我们按事件等价还原：call.chi→チー、pon→ポン、三种杠→カン；
   * agari 时 winner === fromWho = 自摸 ⇒ ツモ，否则 ロン。拔北（nuki）官方不画大字。 */
  function vocalTextOf(ev) {
    if (!ev) { return null; }
    if (ev.type === 'call') {
      if (ev.callType === 'chi') { return 'チー'; }
      if (ev.callType === 'pon') { return 'ポン'; }
      if (ev.callType === 'ankan' || ev.callType === 'kakan' || ev.callType === 'daiminkan') { return 'カン'; }
      return null;
    }
    if (ev.type === 'agari') { return (ev.winner === ev.fromWho) ? 'ツモ' : 'ロン'; }
    return null;
  }

  /** 当前帧的大字：{ pos, text } 或 null（pos = 展示位置 0 下 / 1 右 / 2 上 / 3 左）
   *  牌谱检索 / 全部浏览的静态帧不画大字（用户 m04456）。 */
  function vocalForFrame() {
    if (App.itemIndex >= 0) { return null; }        /* 静态帧不显示大字（用户 m04456） */
    var rnd = App.game && App.game.rounds && App.game.rounds[App.roundIndex];
    if (!rnd || !rnd.events) { return null; }
    var ev = rnd.events[App.frameIndex - 1];
    var text = vocalTextOf(ev);
    if (!text) { return null; }
    var seat = (ev.type === 'agari') ? ev.winner : ev.player;
    if (typeof seat !== 'number' || seat < 0 || seat > 3) { return null; }
    var pos = App.viewRot ? App.viewRot.indexOf(seat) : seat;
    if (pos < 0) { pos = seat; }
    return { pos: pos, text: text };
  }

  function nagaKindId(kind) { return kind * 4 + 1; }        // 避开赤 5（kind*4 会被 Tiles 当成 0m）

  function nagaKindOfName(name) {                           // mjai 牌名 → 0..33
    var s = String(name || '');
    if (!s) { return null; }
    var H = 'ESWNPFC', c = s.charAt(0);
    if (H.indexOf(c) >= 0) { return 27 + H.indexOf(c); }    // 字牌：E/S/W/N/P/F/C
    var m = /^([0-9])([mps])r?$/.exec(s);                   // 数牌，允许赤 5 的尾 r（'5pr'）
    if (!m) { return null; }
    var num = Number(m[1]);
    if (num === 0) { num = 5; }                             // '0m' / '0p' / '0s' = 赤 5
    return { m: 0, p: 1, s: 2 }[m[2]] * 9 + num - 1;
  }

  function nagaChiPair(kind, idx) {                          // 吃的三种牌对（三样本 24/24 实证）
    if (idx === 1) { return [kind + 1, kind + 2]; }          // 被打出的牌作最小
    if (idx === 2) { return [kind - 1, kind + 1]; }          // 作中间
    if (idx === 3) { return [kind - 2, kind - 1]; }          // 作最大
    return null;
  }

  function nagaPctText(p) {                                  // 万分比 → 统一一位小数（用户 m02227 ①）
    var v = (Number(p) || 0) / 100;
    return v.toFixed(1) + '%';
  }

  function nagaSeatOf(nf) {                                  // 本帧「轮到谁决策」
    if (!nf) { return null; }
    var huro = nf.huro;
    if (huro) {
      var best = null, bestP = 0;
      for (var s in huro) {
        if (!Object.prototype.hasOwnProperty.call(huro, s)) { continue; }
        var m = huro[s] || {}, mx = 0;
        for (var i in m) {
          if (!Object.prototype.hasOwnProperty.call(m, i)) { continue; }
          if (Number(i) > 0 && (m[i] || 0) > mx) { mx = m[i] || 0; }
        }
        if (mx > bestP) { bestP = mx; best = Number(s); }
      }
      if (best !== null) { return best; }
      /* 第 64 轮（用户 m07820 ①，口径 (a)）：huro 里列出的席位就是「可能鸣牌的那一家」——
         吃 / 碰 / 杠概率全是 0（只剩 PASS）时上面取不到最大项，这里退化为那一格
         （唯一席位就直接用它；多个席位时取 PASS 概率最大的那个）。
         后端 mjscore/feats.py 的 _model_has_data() 同样认这一格（有数据就算「有」）。 */
      var uq = null, uqP = -1, hcount = 0;
      for (var s2 in huro) {
        if (!Object.prototype.hasOwnProperty.call(huro, s2)) { continue; }
        hcount += 1;
        var one2 = huro[s2], p0 = (one2 && typeof one2['0'] === 'number') ? one2['0'] : 0;
        if (p0 > uqP) { uqP = p0; uq = Number(s2); }
      }
      if (hcount === 1) { return uq; }
      if (uqP > 0) { return uq; }
    }
    return (typeof nf.actor === 'number') ? nf.actor : null;
  }

  function nagaKanInfo(seat, st) {                            // 报告不给杠哪张牌 ⇒ 从手牌推断
    var out = { ankan: [], kakan: [] };
    if (!st || !st.players || !st.players[seat]) { return out; }
    var pl = st.players[seat], cnt = Tiles.countsByKind(pl.hand || []);
    for (var k in cnt) {
      if (!Object.prototype.hasOwnProperty.call(cnt, k)) { continue; }
      if (cnt[k] >= 4) { out.ankan.push(Number(k)); }
    }
    var melds = pl.melds || [];
    for (var i = 0; i < melds.length; i++) {
      var m = melds[i];
      if (!m || m.callType !== 'pon' || !m.tiles || !m.tiles.length) { continue; }
      var kk = Tiles.kindOf(m.tiles[0]);
      if ((cnt[kk] || 0) > 0) { out.kakan.push(kk); }
    }
    return out;
  }

  function nagaOptions(nf, st, seat, mode) {                   // 默认只保留 >10% 的选项（用户 m00198 ③）；mode='raw' 只用于关键帧判定：鸣牌选项不过滤
    var raw = (mode === 'raw');
    var list = [];
    if (!nf) { return list; }
    function push(tiles, word, p, pass) {                   // 打牌 / 杠：只保留 >10% 的选项（用户 m00198 ③）
      if (!p || p <= 1000) { return; }
      list.push({ tiles: tiles || [], word: word, pct: p, pctText: nagaPctText(p), pass: !!pass });
    }
    /* 鸣牌（吃 / 碰 / 大明杠 / 过）：报告里**列出的键**就是这一帧的合法选项（概率可能是 0）。
       mode='raw' 时全部收下（给 renderNagaPanel 判定「可选策略是否只有 PASS」），
       显示用的默认模式仍套 >10% 门槛（用户 m09110：门槛保留、判定顺序颠倒）。 */
    function pushHuro(tiles, word, p, pass) {
      if (!raw && !(p > 1000)) { return; }
      list.push({ tiles: tiles || [], word: word, pct: p || 0, pctText: nagaPctText(p || 0), pass: !!pass });
    }
    if (nf.msg === 'dahai') {                                 // 鸣牌决策：huro（0 过 / 1-3 吃 / 4 碰 / 5 大明杠）
      var m = (nf.huro || {})[String(seat)] || {};
      var dk = nagaKindOfName(nf.pai);
      for (var i in m) {
        if (!Object.prototype.hasOwnProperty.call(m, i)) { continue; }
        var idx = Number(i), p = m[i] || 0;
        if (idx === 0) { pushHuro([], 'PASS', p, true); }
        else if (idx === 4) { pushHuro(dk === null ? [] : [dk, dk], '碰', p); }
        else if (idx === 5) { pushHuro(dk === null ? [] : [dk], '大明杠', p); }
        else if (dk !== null) { var pr = nagaChiPair(dk, idx); if (pr) { pushHuro(pr, '吃', p); } }
      }
    } else {                                     // 打牌决策：dahai_pred / dahai_split / reach / kan
      /* 新版 NAGA（アナンタ = NAGA-避四 / ウロボロス = NAGA-争一）给的是「是否立直 × 打哪张牌」
         的联合分布（用户 m09803）：默听支 → 「打 xx」、立直支 → 「打·立直 xx」，两表共同构成这一帧
         的决策空间；此时不再单独列「立直」行（立直与打牌本来就是同一个动作）。
         旧模型只给边缘分布（dahai_pred / reach）⇒ 走原来的两条分支，展示一字不变。 */
      var sp = nf.dahai_split;
      var split = (sp && sp.dama && sp.riichi) ? sp : null;
      if (split) {
        for (var ks = 0; ks < 34; ks++) {
          var dv = split.dama[ks] || 0, rv = split.riichi[ks] || 0;
          if (dv > 1000) { push([ks], '打', dv); }
          if (rv > 1000) { push([ks], '打·立直', rv); }
        }
      } else {
        var dp = nf.dahai_pred || [];
        for (var k = 0; k < dp.length && k < 34; k++) {
          if ((dp[k] || 0) > 1000) { push([k], '打', dp[k]); }
        }
      }
      var reachItem = null;
      if (!split && nf.reach !== null && nf.reach !== undefined) { // 立直是展示规则的特例（用户 m01903 ③）：
        reachItem = { tiles: [], word: '立直', pct: nf.reach || 0,   // 这一帧只要有立直选项就显示，
          pctText: nagaPctText(nf.reach || 0), reach: true };        // 不看是否 >10%，且永远排第一
      }
      var kan = nf.kan || {}, ki = nagaKanInfo(seat, st);
      /* 杠的规范名称按**牌局状态**判定（用户 m08623）：手里 4 张 = 暗杠；已有碰副露 + 手里第 4 张 = 加杠。
       * 报告只给「档位」（kan['1'] = 暗杠、kan['2'] = 加杠），而 Mortal 会把加杠也报成 ankan
       * （`consumed` 4 张，实测 kyoku 2 entry 10）⇒ 状态里只有一种杠时一律按状态取名。 */
      var kcands = [];
      for (var kni = 0; kni < ki.ankan.length; kni++) { kcands.push({ kind: ki.ankan[kni], word: '暗杠', used: false }); }
      for (var knj = 0; knj < ki.kakan.length; knj++) { kcands.push({ kind: ki.kakan[knj], word: '加杠', used: false }); }
      var krep = [kan['1'] || 0, kan['2'] || 0], kword = ['暗杠', '加杠'];
      for (var knd = 0; knd < 2; knd++) {
        if (!(krep[knd] > 1000)) { continue; }
        var kpick = null;
        for (var kne = 0; kne < kcands.length; kne++) {
          if (!kcands[kne].used && kcands[kne].word === kword[knd]) { kpick = kcands[kne]; break; }
        }
        if (!kpick) {                                    /* 报告档位与状态不符：用状态里剩下的那一种 */
          for (var knf = 0; knf < kcands.length; knf++) { if (!kcands[knf].used) { kpick = kcands[knf]; break; } }
        }
        if (kpick) { kpick.used = true; }
        push(kpick ? [kpick.kind] : [], kpick ? kpick.word : kword[knd], krep[knd]);
      }
    }
    list.sort(function (a, b) { return b.pct - a.pct; });
    if (reachItem) { list.unshift(reachItem); }
    return list;
  }

  function nagaOptEl(it) {
    var row = document.createElement('div');
    row.className = 'naga-opt' + (it.other ? ' other' : '') + (it.reach ? ' reach' : '');
    if (it.tiles.length) {
      var box = document.createElement('span');
      box.className = 'naga-opt-tiles';
      for (var i = 0; i < it.tiles.length; i++) {
        var tid = nagaKindId(it.tiles[i]);
        var img = document.createElement('img');
        img.draggable = false;
        img.src = Tiles.tileSrc(tid);
        img.alt = Tiles.tileLabel(tid);
        img.title = Tiles.tileLabel(tid);
        box.appendChild(img);
      }
      row.appendChild(box);
    }
    var w = document.createElement('span');
    w.className = 'naga-opt-word';
    w.textContent = it.word;
    row.appendChild(w);
    var pc = document.createElement('span');
    pc.className = 'naga-opt-pct';
    pc.textContent = it.pctText;
    row.appendChild(pc);
    return row;
  }

  function nagaHudCell(k, v, wide) {
    var cell = document.createElement('div');
    cell.className = 'nh-cell' + (wide ? ' nh-wide' : '');
    var a = document.createElement('span');
    a.className = 'nh-k';
    a.textContent = k;
    var b = document.createElement('span');
    b.textContent = v;
    cell.appendChild(a);
    cell.appendChild(b);
    return cell;
  }

  function renderNagaPanel() {                                // 天凤牌谱：三块全部留空（用户 m00198 ⑤）
    var optsEl = $('nagaOptions'), whoEl = $('nagaWho'), hudEl = $('nagaHud');
    if (!optsEl || !whoEl || !hudEl) { return; }
    while (optsEl.firstChild) { optsEl.removeChild(optsEl.firstChild); }
    while (hudEl.firstChild) { hudEl.removeChild(hudEl.firstChild); }
    whoEl.textContent = '';
    whoEl.title = '';
    var nf = aiFrame();       /* 无AI决策 ⇒ null：三块留空（= 天凤牌谱的展示方式，用户 m04556 ①） */
    if (!nf) { return; }
    var st = App.rounds[App.roundIndex][App.frameIndex].state;
    var seat = nagaSeatOf(nf);
    /* 隐藏他家手牌时只有「别家」的决策表留空、只保留标题；主视角自己的决策照旧显示（用户 m03343 ①） */
    if (App.hideOthers && seat !== App.selfSeat) { return; }
    var name = (seat !== null && st.players[seat]) ? st.players[seat].name : '';
    /* 关键帧判定先做、概率过滤后做（用户 m09110）：报告给这一帧的决策者列出的可选策略不止 PASS
       ⇒ 关键帧 ⇒ 必须显示 AI 分析结果（当前决策 / 选项表 / 5 项数据）；可选策略只有 PASS、或报告
       根本没给选项（没有决策分支的展示帧）⇒ 非关键帧 ⇒ 整块留空、只留标题「NAGA 决策」（用户 m02007 ③）。 */
    var avail = nagaOptions(nf, st, seat, 'raw');
    var real = false;
    for (var q = 0; q < avail.length; q++) { if (!avail[q].pass) { real = true; break; } }
    if (!real) { return; }
    var list = nagaOptions(nf, st, seat);
    whoEl.textContent = (seat === null) ? '当前没有决策' : ('当前决策：' + name);
    whoEl.title = whoEl.textContent;
    var shown = 0;
    // 立直与打牌（dahai_pred）是同一帧里两个独立的边缘量，「其它」只算打牌 / 鸣牌选项的残差（用户 m01903 ③）
    for (var i = 0; i < list.length; i++) { if (!list[i].reach) { shown += list[i].pct; } }
    /* 「其它」= 100.0% − 表内已显示选项的**显示值**合计（用户 m01810 ②；用户 m09901）。
       必须按显示值（一位小数）而不是原始万分比判断：9954（99.54%）会显示成 99.5%，原始残差只有 0.46%
       却仍会在表里留下「合计 99.5%」的观感；一个选项都没过门槛、或显示值合计已到 100.0%
       （甚至因报告分布不归一而超过 100%）时，不再补这种没有信息量的行（用户 m02007 ③、m09110）。 */
    if (list.length) {
      var shownTxt = 0;                                   // 立直与打牌是两个独立的边缘量，不计入（用户 m01903 ③）
      for (var j = 0; j < list.length; j++) {
        if (!list[j].reach) { shownTxt += Math.round(list[j].pct / 10) / 10; }
      }
      var restTxt = Math.round((100 - shownTxt) * 10) / 10;
      if (restTxt >= 0.1) {
        list.push({ tiles: [], word: '其它', pct: 10000 - shown, pctText: restTxt.toFixed(1) + '%', other: true });
      }
    }
    for (i = 0; i < list.length; i++) { optsEl.appendChild(nagaOptEl(list[i])); }
    var hs = (seat === null) ? App.selfSeat : seat;           // 5 个数据（纯文本，用户 m00198 ②）
    var et = nf.end_type, gr = nf.game_rank;
    function pct1(r) { return (et && et[r]) ? ((et[r][hs] || 0) / 100).toFixed(1) + '%' : '—'; }
    hudEl.appendChild(nagaHudCell('流局率', pct1(3)));
    hudEl.appendChild(nagaHudCell('横移率', pct1(2)));
    hudEl.appendChild(nagaHudCell('放铳率', pct1(1)));
    hudEl.appendChild(nagaHudCell('和了率', pct1(0)));
    var exp = '—';
    if (gr && gr[hs]) {
      var sum = 0;
      for (var r = 0; r < gr[hs].length && r < 4; r++) { sum += (r + 1) * (gr[hs][r] || 0); }
      exp = (sum / 10000).toFixed(2) + ' 位';
    }
    hudEl.appendChild(nagaHudCell('期待顺位', exp, true));
  }


  var FeatPanel = { key: '', seq: 0, loading: false, error: '', row: null, usedKeys: {} };

  function featUsed(key) { return !!FeatPanel.usedKeys[key]; }

  /* 检索条件里用到的特征 ⇒ 在面板里高亮 */
  function markUsedFeatures() {
    var used = {};
    for (var i = 0; i < Sc.conds.length; i++) { used[Sc.conds[i].key] = 1; }
    FeatPanel.usedKeys = used;
    renderFeatPanel();
  }

  /* 向听数（国士無双 / 七対子 / 面子手）内部取值 3 表示「>=3 向听」，
     对外一律显示成 >=3（用户 m04115②；对应 Python 侧 cli.feat_value_text()）。 */
  var SHANTEN_KEYS = { shanten_kokushi: 1, shanten_chiitoi: 1, shanten_mentsu: 1 };

  function fmtFeatValue(key, v) {
    if (v === null || v === undefined || v === '') { return '—'; }
    if (SHANTEN_KEYS[key] && Number(v) === 3) { return '>=3'; }
    if (typeof v === 'number') {
      if (isFinite(v) && Math.floor(v) === v) { return String(v); }
      return String(Math.round(v * 1e6) / 1e6);
    }
    return String(v);
  }

  function renderFeatPanel() {
    var box = $('featPanelList');
    if (!box) { return; }
    renderFeatMode();                    /* 先按当前状态刷新底部局面文字 */
    clearNode(box);
    if (FeatPanel.loading) { box.appendChild(plainRow('正在读取这一帧的特征…', 'muted')); return; }
    if (FeatPanel.error) { box.appendChild(plainRow('读取失败：' + FeatPanel.error, 'warn')); return; }
    var row = FeatPanel.row;
    if (!row) {
      box.appendChild(plainRow(App.game
        ? '当前帧没有打点行：只有「非自摸的摸牌帧」、「吃/碰后等待出牌的帧」与「鸣牌响应帧」才有特征值。'
        : '（未载入牌谱）', 'muted'));
      return;
    }
    var feats = row.feats || {}, used = 0, shown = 0;
    for (var i = 0; i < FEATURES.length; i++) {
      var f = FEATURES[i];
      /* 第零类特征不列进「当前帧特征」（用户 m05937 ②）：牌谱含哪些 AI 模型的信息已经由右上角
         「NAGA 决策 / Mortal 决策」模型选择按钮体现；第三类「等待鸣牌」（用户 m07289）也不列进来，
         改由面板底部的局面文字体现。这里只列第一类 17 项 + 第二类 17 项。 */
      if (isAiKey(f.key) || isThirdKey(f.key)) { continue; }
      shown += 1;
      var r = document.createElement('div');
      r.className = 'feat-row' + (featUsed(f.key) ? ' used' : '');
      r.setAttribute('data-key', f.key);
      var nm = document.createElement('span');
      nm.className = 'feat-name';
      nm.textContent = f.name;
      var vv = document.createElement('span');
      vv.className = 'feat-value';
      vv.textContent = fmtFeatValue(f.key, Object.prototype.hasOwnProperty.call(feats, f.key) ? feats[f.key] : undefined);
      r.appendChild(nm);
      r.appendChild(vv);
      if (featUsed(f.key)) { r.title = '这一条正用于当前检索条件'; used += 1; }
      box.appendChild(r);
    }
    renderFeatMode();
  }

  /* 面板底部的局面文字（第三类特征「等待鸣牌」的展示方式，用户 m07289）：
     大号、醒目的居中文字「出牌局面」/「鸣牌响应局面」，没有打点行时不显示。 */
  function renderFeatMode() {
    var el = $('featPanelMode');
    if (!el) { return; }
    var row = FeatPanel.row, txt = '';
    if (row && !FeatPanel.loading && !FeatPanel.error) {
      var isWait = (row.kind === 'wait')
        || !!(row.feats && row.feats.meld_wait === '是');
      txt = isWait ? '鸣牌响应局面' : '出牌局面';
    }
    el.textContent = txt;
    if (el.classList) { el.classList.toggle('hidden', !txt); }
  }

  /* 每次 render() 后同步：先看当前帧是不是打点帧，再按「数据库 + 帧」缓存读取 */
  function syncFeatPanel() {
    var box = $('featPanelList');
    if (!box) { return; }
    var info = $('featPanelInfo');
    var frames = App.rounds[App.roundIndex];
    var st = (frames && frames[App.frameIndex]) ? frames[App.frameIndex].state : null;
    var seat = frameSeatOf(st);
    if (seat === null || !App.game) {
      FeatPanel.key = '';
      FeatPanel.seq += 1;
      FeatPanel.loading = false;
      FeatPanel.error = '';
      FeatPanel.row = null;
      if (info) { info.textContent = ''; info.title = ''; }
      renderFeatPanel();
      return;
    }
    if (info) { var fpTitle = frameKeyText(); info.textContent = fpTitle; info.title = fpTitle; }

    /* 条目模式：直接取检索结果那一行（/api/detail 用 idx），保证与列表逐字一致 */
    var it = (App.itemIndex >= 0) ? App.items[App.itemIndex] : null;
    var sameItem = !!(it && it.idx !== undefined && it.idx !== null
      && String(it.log_id) === gameLogId()
      && parseInt(it.round_index, 10) === App.roundIndex
      && parseInt(it.frame_index, 10) === App.frameIndex);
    var dbq = scDbPayload();
    var dbKey = dbq.db || dbq.db_name || '';
    var ck = sameItem
      ? ('idx|' + it.idx + '|' + dbKey)
      : ('frame|' + gameLogId() + '|' + App.roundIndex + '|' + App.frameIndex + '|' + seat + '|' + dbKey);
    if (FeatPanel.key === ck) { renderFeatPanel(); return; }
    if (!sameItem && !dbq.db && !dbq.db_name) {
      FeatPanel.key = ck;
      FeatPanel.loading = false;
      FeatPanel.error = '';
      FeatPanel.row = null;
      clearNode(box);
      box.appendChild(plainRow('还没有可用数据库：先在「牌谱分析」里建库，或在「牌谱检索」里选择本地数据库文件。', 'muted'));
      return;
    }

    FeatPanel.key = ck;
    FeatPanel.row = null;
    FeatPanel.error = '';
    FeatPanel.loading = true;
    renderFeatPanel();
    var seq = ++FeatPanel.seq;
    var path = '/api/frame-feats';
    var body = { log_id: gameLogId(), round_index: App.roundIndex, frame_index: App.frameIndex, seat: seat };
    /* m03580 修复：命中「检索结果那一行」时也必须带上同一个数据库，
       否则服务会回落到默认库（data/db/paipu.sqlite）而报「数据库文件不存在」。 */
    if (dbq.db) { body.db = dbq.db; } else { body.db_name = dbq.db_name; }
    if (sameItem) {
      path = '/api/detail';
      body = { idx: it.idx };
      if (dbq.db) { body.db = dbq.db; } else { body.db_name = dbq.db_name; }
    }
    api(path, body).then(function (d) {
      if (seq !== FeatPanel.seq) { return; }
      FeatPanel.loading = false;
      FeatPanel.row = d.row || null;
      renderFeatPanel();
    })['catch'](function (e) {
      if (seq !== FeatPanel.seq) { return; }
      FeatPanel.loading = false;
      FeatPanel.error = e.message;
      renderFeatPanel();
    });
  }

  /* ------------------------------------------------------------ 分析进度 */
  var AnTimer = null;

  /* 设置进度条宽度（测试里的假 DOM 元素可能没有 style，这里统一兜住） */
  function setBar(id, pct) {
    var el = $(id);
    if (el && el.style) { el.style.width = pct + '%'; }
  }

  function anProgressText(p) {
    var parts = [];
    parts.push('已完成 ' + (p.files_done || 0) + ' / ' + (p.files_total || 0) + ' 个牌谱');
    if (p.current) { parts.push('当前 ' + p.current); }
    if (p.rounds_total) { parts.push('局 ' + (p.rounds_done || 0) + '/' + p.rounds_total); }
    if (p.skipped) { parts.push('跳过已入库 ' + p.skipped + ' 个'); }
    parts.push(((p.elapsed_ms || 0) / 1000).toFixed(1) + ' s');
    return parts.join(' ｜ ');
  }

  function anProgressStart() {
    var box = $('anProgressBox');
    if (box) { box.classList.remove('hidden'); }
    setBar('anProgressBar', 2);
    var txt = $('anProgressText');
    if (txt) { txt.textContent = '正在启动分析…'; }
    if (AnTimer) { window.clearTimeout(AnTimer); }
    AnTimer = window.setTimeout(anProgressTick, 300);
  }

  function anProgressTick() {
    api('/api/analyze-progress').then(function (d) {
      var p = (d && d.progress) || {};
      var total = p.files_total || 0;
      var pct = total ? Math.max(2, Math.min(100, Math.round((p.files_done || 0) * 100 / total))) : 2;
      setBar('anProgressBar', pct);
      var txt = $('anProgressText');
      if (txt) { txt.textContent = anProgressText(p); }
      if (p.running) { AnTimer = window.setTimeout(anProgressTick, 500); } else { AnTimer = null; }
    })['catch'](function () {
      AnTimer = window.setTimeout(anProgressTick, 1000);
    });
  }

  function anProgressDone(ok, text) {
    if (AnTimer) { window.clearTimeout(AnTimer); AnTimer = null; }
    setBar('anProgressBar', ok ? 100 : 0);
    var txt = $('anProgressText');
    if (txt) { txt.textContent = text || ''; }
  }

  /* ------------------------------------------------------------ 牌谱下载 */
  var Dl = { mode: 'url', fileName: '', fileText: '', running: false, total: 0, dir: '' };

  function dlFillDefaultDir() {
    var el = $('dlSubdir');
    if (!el) { return; }
    var d = new Date();
    function p2(n) { return (n < 10 ? '0' : '') + n; }
    el.value = d.getFullYear() + p2(d.getMonth() + 1) + p2(d.getDate()) + '-'
      + p2(d.getHours()) + p2(d.getMinutes()) + p2(d.getSeconds());
  }

  function dlSetMode(mode) {
    Dl.mode = (mode === 'file') ? 'file' : 'url';
    var ur = $('dlUrlRow'), fr = $('dlFileRow');
    if (ur) { ur.classList.toggle('hidden', Dl.mode !== 'url'); }
    if (fr) { fr.classList.toggle('hidden', Dl.mode !== 'file'); }
  }

  function dlReadFile() {
    var el = $('dlUrlFile');
    var f = el && el.files && el.files[0];
    if (!f) { return; }
    Dl.fileName = f.name || '';
    var fr = new FileReader();
    fr.onload = function () {
      Dl.fileText = String(fr.result || '');
      var lines = Dl.fileText.split(/\r?\n/).filter(function (line) {
        var t = line.replace(/^\uFEFF/, '').trim();
        return t && t.charAt(0) !== '#';
      });
      var nm = $('dlFileName');
      if (nm) { nm.textContent = Dl.fileName + '（' + lines.length + ' 行待下载）'; }
      setMsg('dlMsg', '已选择 ' + Dl.fileName + '：共 ' + lines.length + ' 个待下载 URL。');
    };
    fr.readAsText(f);
    el.value = '';
  }

  function dlStart() {
    if (Dl.running) { setMsg('dlMsg', '正在下载，请稍候…', true); return; }
    if (!valOf('dlSubdir', '')) { dlFillDefaultDir(); }
    var body = { subdir: valOf('dlSubdir', '') };
    if (Dl.mode === 'url') {
      var u = valOf('dlUrl', '');
      if (!u) { setMsg('dlMsg', '请先输入一个牌谱 URL（或裸特征码）。', true); return; }
      body.url = u;
    } else {
      if (!Dl.fileText) { setMsg('dlMsg', '请先选择一个「每行一个 URL」的文本文件。', true); return; }
      body.text = Dl.fileText;
    }
    Dl.running = true;
    setMsg('dlMsg', '正在提交下载任务…');
    var box = $('dlProgressBox');
    if (box) { box.classList.remove('hidden'); }
    var li = $('dlList');
    if (li) { clearNode(li); }
    api('/api/download', body).then(function (d) {
      Dl.total = d.urls || d.total || 0;
      Dl.dir = d.dir || '';
      var cnt = $('dlCounts');
      if (cnt) { cnt.textContent = '待下载 ' + Dl.total + ' 个 ｜ 目录 ' + Dl.dir; }
      dlPoll();
    })['catch'](function (e) {
      Dl.running = false;
      setMsg('dlMsg', '下载失败：' + e.message, true);
    });
  }

  function dlPoll() {
    api('/api/download-progress').then(function (d) {
      var p = (d && d.progress) || {};
      var total = p.total || Dl.total || 0;
      var done = p.done_n || 0;
      var pct = total ? Math.max(0, Math.min(100, Math.round(done * 100 / total))) : 0;
      setBar('dlProgressBar', pct);
      var txt = $('dlProgressText');
      if (txt) {
        txt.textContent = '已下载 ' + done + ' / ' + total + ' ｜ 成功 ' + (p.saved || 0) + ' ｜ 失败 ' + (p.failed || 0)
          + (p.current ? (' ｜ 当前 ' + p.current) : '') + ' ｜ ' + ((p.elapsed_ms || 0) / 1000).toFixed(1) + ' s';
      }
      if (p.done) {
        Dl.running = false;
        var cnt = $('dlCounts');
        if (cnt) {
          cnt.textContent = '待下载 ' + total + ' 个 ｜ 成功 ' + (p.saved || 0) + ' ｜ 失败 ' + (p.failed || 0)
            + ' ｜ 目录 ' + (p.dir || Dl.dir);
        }
        setMsg('dlMsg', '下载完成：成功 ' + (p.saved || 0) + ' / ' + total + '，失败 ' + (p.failed || 0)
          + (p.error ? ('（' + p.error + '）') : '') + '。文件在 ' + (p.dir || Dl.dir), !!p.failed);
        dlListResults(p.dir || Dl.dir);
        return;
      }
      window.setTimeout(dlPoll, 400);
    })['catch'](function (e) {
      Dl.running = false;
      setMsg('dlMsg', '读取下载进度失败：' + e.message, true);
    });
  }

  function dlListResults(dirAbs) {
    var box = $('dlList');
    if (!box) { return; }
    var rel = 'data/paipu/' + valOf('dlSubdir', '');
    api('/api/scan?dir=' + encodeURIComponent(dirAbs || rel) + '&kind=all').then(function (d) {
      clearNode(box);
      box.appendChild(plainRow('目录 ' + d.dir + '：' + d.count + ' 个牌谱', 'muted'));
      /* 分析面板的牌谱目录下拉框跟到刚下载的目录（用户 m01171 第 2 条） */
      if (An.pickerDir !== rel) { An.pickerDir = rel; loadPaipuPicker(rel, true); }
      for (var i = 0; i < d.files.length && i < 300; i++) {
        var r = document.createElement('div');
        r.className = 'item-row static';
        r.textContent = d.files[i];
        box.appendChild(r);
      }
    })['catch'](function (e) { setMsg('dlMsg', '列出下载目录失败：' + e.message, true); });
  }

  /* ------------------------------------------------------ 本地数据管理 */
  /* 用户 m00178 第 9 条：数据目录将来固定在 %LOCALAPPDATA%\<AppName>\data 下，
     用户不方便自己开资源管理器，所以这里直接管 data/paipu（牌谱）与 data/db（数据库）：
     新建目录 / 移动到子目录或上一级目录 / 删除文件 / 删除子目录。 */
  var Dm = {
    root: 'paipu',      /* 当前数据区：'paipu' 牌谱 / 'db' 数据库 */
    rel: '',            /* 当前目录（相对数据根，'' = 数据根） */
    sel: null,          /* 选中的条目：{kind:'dir'|'file', name, path} */
    state: null         /* 最近一次 /api/fs-list 的返回 */
  };

  function dmRelText() { return Dm.rel ? ('/' + Dm.rel) : '/'; }

  function dmMsg(text, warn) { setMsg('dmMsg', text, warn); }

  function dmRootLabel() { return Dm.root === 'db' ? 'data/db' : 'data/paipu'; }

  function dmFmtSize(n) {
    if (n === undefined || n === null) { return ''; }
    if (n < 1024) { return n + ' B'; }
    if (n < 1024 * 1024) { return (n / 1024).toFixed(1) + ' KB'; }
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }

  /* 「移动到」下拉里要排除的目标：选中的目录本身 + 它的子目录（服务端也会拦） */
  function dmSkipDests() {
    var skip = {};
    if (Dm.sel && Dm.sel.kind === 'dir' && Dm.state) {
      skip[Dm.sel.path] = true;
      for (var i = 0; i < Dm.state.all_dirs.length; i++) {
        var p = Dm.state.all_dirs[i];
        if (p && p.indexOf(Dm.sel.path + '/') === 0) { skip[p] = true; }
      }
    }
    return skip;
  }

  function dmFillDest() {
    var sel = $('dmDest');
    if (!sel) { return; }
    var keep = sel.value || '';
    var opts = [{ v: '', t: '（数据根 ' + dmRootLabel() + '）' }];
    var skip = dmSkipDests();
    var all = (Dm.state && Dm.state.all_dirs) || [];
    var i;
    for (i = 0; i < all.length; i++) {
      if (!all[i] || skip[all[i]]) { continue; }
      opts.push({ v: all[i], t: all[i] + '/' });
    }
    clearNode(sel);
    for (i = 0; i < opts.length; i++) {
      var o = document.createElement('option');
      o.value = opts[i].v;
      o.textContent = opts[i].t;
      sel.appendChild(o);
    }
    var has = false;
    for (i = 0; i < opts.length; i++) { if (opts[i].v === keep) { has = true; } }
    sel.value = has ? keep : '';
  }

  function dmSelInfo() {
    var el = $('dmSelInfo');
    if (!el) { return; }
    el.textContent = Dm.sel
      ? ('已选中' + (Dm.sel.kind === 'dir' ? '目录' : '文件') + '：' + Dm.sel.path)
      : '未选中任何条目';
  }

  function dmRow(kind, item) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'item-row dm-row';
    btn.setAttribute('data-kind', kind);
    btn.setAttribute('data-path', item.path);
    if (Dm.sel && Dm.sel.kind === kind && Dm.sel.path === item.path) { btn.className += ' sel'; }
    var nm = document.createElement('span');
    nm.className = 'dm-name';
    nm.textContent = (kind === 'dir' ? '[目录] ' : '[文件] ') + item.name;
    btn.appendChild(nm);
    var meta = document.createElement('span');
    meta.className = 'dm-meta';
    meta.textContent = (kind === 'dir')
      ? ('（' + (item.entries || 0) + ' 项）')
      : (dmFmtSize(item.size) + (item.sqlite ? ' · 数据库' : ''));
    btn.appendChild(meta);
    if (kind === 'dir') {
      var go = document.createElement('span');
      go.className = 'dm-go';
      go.setAttribute('data-act', 'enter');
      go.textContent = '进入';
      btn.appendChild(go);
    }
    return btn;
  }

  function dmFillLists() {
    var d = Dm.state;
    if (!d) { return; }
    var i;
    var box = $('dmDirs');
    if (box) {
      clearNode(box);
      if (!d.dirs.length) { box.appendChild(plainRow('（没有子目录）', 'muted')); }
      for (i = 0; i < d.dirs.length; i++) { box.appendChild(dmRow('dir', d.dirs[i])); }
    }
    var fbox = $('dmFiles');
    if (fbox) {
      clearNode(fbox);
      if (!d.files.length) { fbox.appendChild(plainRow('（没有文件）', 'muted')); }
      for (i = 0; i < d.files.length; i++) { fbox.appendChild(dmRow('file', d.files[i])); }
    }
    var abs = $('dmAbs');
    if (abs) { abs.textContent = d.root_dir || ''; }
    var pth = $('dmPath');
    if (pth) { pth.textContent = dmRelText(); }
  }

  function dmUpdate() {
    dmFillLists();
    dmFillDest();
    dmSelInfo();
  }

  /* 列目录；当前目录被删掉（服务端 400）时自动退回数据根 */
  function dmLoad(rel) {
    if (rel !== undefined && rel !== null) { Dm.rel = rel; }
    var url = '/api/fs-list?root=' + encodeURIComponent(Dm.root) + '&rel=' + encodeURIComponent(Dm.rel);
    return api(url).then(function (d) {
      Dm.state = d;
      Dm.sel = null;
      dmUpdate();
      return d;
    })['catch'](function (e) {
      if (Dm.rel) { Dm.rel = ''; return dmLoad(''); }
      dmMsg('读取数据目录失败：' + e.message, true);
      return null;
    });
  }

  function dmInit() {
    var el = $('dmRoot');
    if (el) { el.value = Dm.root; }
    Dm.rel = '';
    Dm.sel = null;
    dmMsg('');
    return dmLoad('');
  }

  function dmSwitchRoot() {
    var el = $('dmRoot');
    Dm.root = (el && el.value) ? el.value : 'paipu';
    Dm.rel = '';
    Dm.sel = null;
    dmMsg('');
    return dmLoad('');
  }

  function dmUp() {
    if (!Dm.rel) { dmMsg('已经在数据根目录了。', true); return; }
    var parent = (Dm.state && Dm.state.parent !== undefined)
      ? Dm.state.parent : Dm.rel.split('/').slice(0, -1).join('/');
    dmLoad(parent);
  }

  function dmOnListClick(e) {
    var row = (e.target && e.target.closest) ? e.target.closest('.item-row') : null;
    if (!row) { return; }
    var kind = row.getAttribute('data-kind');
    var path = row.getAttribute('data-path');
    var act = (e.target.getAttribute && e.target.getAttribute('data-act')) || '';
    if (act === 'enter' && kind === 'dir') { dmLoad(path); return; }
    if (Dm.sel && Dm.sel.kind === kind && Dm.sel.path === path) {
      Dm.sel = null;
    } else {
      Dm.sel = { kind: kind, name: baseName(path), path: path };
    }
    dmUpdate();
  }

  function dmMkdir() {
    var name = valOf('dmNewName', '');
    if (!name) { dmMsg('请先填「新建目录」的名字。', true); return; }
    api('/api/fs-mkdir', { root: Dm.root, rel: Dm.rel, name: name }).then(function (d) {
      var el = $('dmNewName');
      if (el) { el.value = ''; }
      dmMsg('已新建目录：' + (d.created || name));
      return dmLoad(Dm.rel);
    })['catch'](function (e) { dmMsg('新建目录失败：' + e.message, true); });
  }

  function dmMove() {
    if (!Dm.sel) { dmMsg('请先选中要移动的条目。', true); return; }
    api('/api/fs-move', { root: Dm.root, rel: Dm.sel.path, dest: valOf('dmDest', '') }).then(function (d) {
      dmMsg('已移动到：' + (d.to ? ('/' + d.to) : (dmRootLabel() + ' 根目录')));
      return dmLoad(Dm.rel);
    })['catch'](function (e) { dmMsg('移动失败：' + e.message, true); });
  }

  function dmAsk(text) {
    return (typeof window.confirm !== 'function') || window.confirm(text);
  }

  function dmDelete() {
    if (!Dm.sel) { dmMsg('请先选中要删除的文件。', true); return; }
    var it = Dm.sel;
    if (it.kind !== 'file') { dmMsg('「' + it.path + '」是目录，请用「删除选中子目录」。', true); return; }
    if (!dmAsk('确定删除文件？' + '\n' + it.path + '\n' + '删除后不可恢复。')) { return; }
    api('/api/fs-delete', { root: Dm.root, rel: it.path }).then(function (d) {
      dmMsg('已删除文件：' + (d.deleted || it.path));
      return dmLoad(Dm.rel);
    })['catch'](function (e) { dmMsg('删除失败：' + e.message, true); });
  }

  function dmRmdir() {
    if (!Dm.sel) { dmMsg('请先选中要删除的子目录。', true); return; }
    var it = Dm.sel;
    if (it.kind !== 'dir') { dmMsg('「' + it.path + '」是文件，请用「删除选中文件」。', true); return; }
    if (!dmAsk('确定删除子目录（连同里面的全部内容）？' + '\n' + it.path + '\n' + '删除后不可恢复。')) { return; }
    api('/api/fs-rmdir', { root: Dm.root, rel: it.path }).then(function (d) {
      dmMsg('已删除子目录：' + (d.deleted || it.path));
      return dmLoad(Dm.rel);
    })['catch'](function (e) { dmMsg('删除子目录失败：' + e.message, true); });
  }

  /* -------------------------------------------------------- 初始化 */
  function baseName(p) {
    var s = String(p === undefined || p === null ? '' : p).replace(/\\/g, '/');
    var i = s.lastIndexOf('/');
    return i < 0 ? s : s.slice(i + 1);
  }

  /* 用户数据目录（来自 /api/health）：牌谱在 paipu_dir，分析库在 db_dir。
     用户 m03175 ③ 删掉「示例牌谱」下拉后，这里只保留目录信息 —— 「浏览选择」的原生对话框
     默认目录与「按特征码搜索」的扫描目录都要用它。 */
  function loadHealth() {
    return api('/api/health').then(function (h) {
      App.dataRoot = h.data_root || '';
      App.dbDir = h.db_dir || '';
      App.paipuDir = h.paipu_dir || '';
      return App.paipuDir;
    })['catch'](function () { return ''; });
  }

  /* 拖放区覆盖整个牌桌区域（用户 m03175 ⑥）：事件绑在 .board-box 上，
     #dropZone 用 pointer-events:none 只负责显示边框与提示文字。 */
  function initDrop() {
    var box = $('boardBox');
    var dz = $('dropZone');
    ['dragenter', 'dragover'].forEach(function (t) {
      box.addEventListener(t, function (e) {
        e.preventDefault();
        if (dz) { dz.classList.add('over'); }
      });
    });
    ['dragleave', 'drop'].forEach(function (t) {
      box.addEventListener(t, function (e) {
        e.preventDefault();
        if (dz) { dz.classList.remove('over'); }
      });
    });
    box.addEventListener('drop', function (e) {
      var fs = e.dataTransfer && e.dataTransfer.files;
      if (fs && fs.length) { readFile(fs[0]); }
    });
    /* 防止拖到页面其它位置时浏览器直接打开该文件 */
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('drop', function (e) { e.preventDefault(); });
  }

  function init() {
    loadHealth();
    initDrop();

    $('btnPickFile').addEventListener('click', pickPaipuFile);
    $('fileInput').addEventListener('change', function () {
      var f = this.files && this.files[0];
      this.value = '';
      readFile(f);
    });
    $('btnGoSearch').addEventListener('click', function () { setView('search'); });
    /* 首页卡片的「牌谱播放」与顶部页签走同一条入口逻辑（用户 m04285 ①） */
    bind('btnGoReplay', openReplayView);
    bind('btnOpenPicker', function () { $('rpOpenBar').classList.toggle('hidden'); });

    /* 浏览选择 / 按特征码搜索 两种互斥方式（用户 m03175 ④⑤）：
       按 id 绑定（而不是按 name 查），浏览器与测试环境都拿得到元素。 */
    $('rpModeBrowse').addEventListener('change', function () { syncOpenMode('browse'); });
    $('rpModeSearch').addEventListener('change', function () { syncOpenMode('search'); });
    $('codeInput').addEventListener('input', function () { renderCodeResults(this.value); });
    $('codeResults').addEventListener('click', function (e) {
      var row = e.target && e.target.closest ? e.target.closest('.code-row') : null;
      if (row) { openPaipuPath(row.getAttribute('data-path')); }
    });
    syncOpenMode();

    /* 切换主视角上拉框（用户 m03343 ②）：点一行 = 把那一家的座位转到主视角 */
    $('viewMenu').addEventListener('click', function (e) {
      var row = e.target && e.target.closest ? e.target.closest('.view-row') : null;
      if (!row) { return; }
      setViewSeat(parseInt(row.getAttribute('data-seat'), 10));
      toggleViewMenu(false);
      render();
    });
    bind('btnGoAnalyze', function () { setView('analyze'); });

    /* 牌谱分析 */
    bind('btnScan', scanFiles);
    var anDir = $('anSourceDir');
    if (anDir && anDir.addEventListener) { anDir.addEventListener('change', anDirChanged); }
    var anFile = $('anSourceFile');
    if (anFile && anFile.addEventListener) { anFile.addEventListener('change', anFileChanged); }
    loadPaipuPicker('data/paipu', true);   /* 目录树固定 data/paipu（服务没起时静默） */
    bind('btnSelAll', function () { setAllFiles(true); });
    bind('btnSelNone', function () { setAllFiles(false); });
    bind('btnAnalyze', doAnalyze);
    bind('btnRefreshDb', function () { refreshDbs(); });
    var modes = document.querySelectorAll('input[name="anMode"]');
    for (var ai = 0; ai < modes.length; ai++) {
      modes[ai].addEventListener('change', function () { anSetMode(this.value); });
    }
    anSetMode('new');
    bind('btnFullHelp', function () {
      var d = $('anFullHelp');
      if (d) { d.open = !d.open; }
    });
    loadMeta();

    /* 牌谱检索 */
    bind('btnScRefresh', function () { refreshDbs(); });
    bind('btnAddFeat', addFeat);
    bind('btnClearConds', clearConds);
    bind('btnRunQuery', runQuery);
    bind('btnBrowseAll', browseAll);
    bind('btnAiClear', clearAiPlan);
    var waitModes = document.querySelectorAll('input[name="waitMode"]');
    for (var wmi = 0; wmi < waitModes.length; wmi++) {
      waitModes[wmi].addEventListener('change', function () { setWait(this.value); });
    }
    bind('nagaModelBtn', function () { toggleAiModelMenu(); });
    var mmBox = $('nagaModelMenu');
    if (mmBox) {
      mmBox.addEventListener('click', function (e) {
        var row = (e.target && e.target.closest) ? e.target.closest('.ai-row') : null;
        if (!row || row.classList.contains('disabled')) { return; }
        setAiModel(parseInt(row.getAttribute('data-index'), 10));
      });
    }

    /* 条目导航 + 特征串复制 */
    bind('btnPrevItem', function () { stepItem(-1); });
    bind('btnNextItem', function () { stepItem(1); });
    bind('frameKey', copyFrameKey);
    bind('btnCopyUrl', copyUrl);

    /* 牌谱下载 */
    bind('btnGoDownload', function () { setView('download'); });
    bind('btnDlDefaultDir', dlFillDefaultDir);
    bind('btnDownload', dlStart);
    bind('btnDlPickFile', function () { var el = $('dlUrlFile'); if (el) { el.click(); } });
    var dlFile = $('dlUrlFile');
    if (dlFile) { dlFile.addEventListener('change', dlReadFile); }
    var dlModes = document.querySelectorAll('input[name="dlMode"]');
    for (var mi = 0; mi < dlModes.length; mi++) {
      dlModes[mi].addEventListener('change', function () { dlSetMode(this.value); });
    }
    dlFillDefaultDir();
    dlSetMode('url');

    renderFeatSelect();
    renderConds();
    renderAiPlan();
    syncWaitRadios();
    markUsedFeatures();
    $('btnBackHome').addEventListener('click', function () { setView('home'); });

    /* 本地数据管理（用户 m00178 第 9 条） */
    bind('btnGoData', function () { setView('data'); });
    bind('btnDmHome', function () { setView('home'); });
    bind('dmRefresh', function () { dmLoad(); });
    bind('dmUp', dmUp);
    bind('dmMkdir', dmMkdir);
    bind('dmMove', dmMove);
    bind('dmDelete', dmDelete);
    bind('dmRmdir', dmRmdir);
    var dmRootSel = $('dmRoot');
    if (dmRootSel) { dmRootSel.addEventListener('change', dmSwitchRoot); }
    var dmDirsBox = $('dmDirs');
    if (dmDirsBox) { dmDirsBox.addEventListener('click', dmOnListClick); }
    var dmFilesBox = $('dmFiles');
    if (dmFilesBox) { dmFilesBox.addEventListener('click', dmOnListClick); }

    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener('click', function () {
        var v = this.getAttribute('data-view');
        /* 没载入牌谱也允许进播放视图：入口（浏览选择 / 按特征码搜索 / 拖入）就在那里。
           静态帧（牌谱检索 / 全部浏览）不算「牌谱播放」状态，先卸载回等待选择的界面（用户 m04285 ①）。 */
        if (v === 'replay') { openReplayView(); return; }
        setView(v);
      });
    }

    $('controls').addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('button[data-act]') : null;
      if (b && App.itemIndex < 0) { onAct(b.getAttribute('data-act')); }
    });

    $('roundSelect').addEventListener('change', function () {
      setRound(parseInt(this.value, 10), 0);
    });

    $('eventListBody').addEventListener('click', function (e) {
      var row = e.target && e.target.closest ? e.target.closest('.ev-row') : null;
      if (row) { setFrame(parseInt(row.getAttribute('data-idx'), 10)); }
    });

    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', fitBoard);
    /* 上拉框开着时跟着按钮走（窗口缩放 / 控制条横向滚动，用户 m03498） */
    window.addEventListener('resize', placeViewMenuIfOpen);
    $('controls').addEventListener('scroll', placeViewMenuIfOpen);

    syncOthers();
    syncViewBtn();
    setView('home');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* 调试入口 */
  window.App = App;
  window.App.loadText = loadText;
  window.App.isNagaFileName = isNagaFileName;
  window.App.loadPaipuPicker = loadPaipuPicker;
  window.App.api = api;
  window.App.refreshDbs = refreshDbs;
  window.App.frameKeyText = frameKeyText;
  window.App.paipuUrl = paipuUrl;
  window.App.copyUrl = copyUrl;
  window.App.openItem = openItem;
  window.App.loadSegment = loadSegment;      /* 用户 m09339 ②：分段载入（测试用） */
  window.App.openItemGlobal = openItemGlobal;
  window.App.syncItemNav = syncItemNav;
  window.App.setRound = setRound;
  window.App.setFrame = setFrame;
  window.App.atGameEnd = atGameEnd;
  window.App.nextFallback = nextFallback;
  window.App.showGameEnd = showGameEnd;
  window.App.seatOfFrame = seatOfFrame;
  window.App.decisionSeats = decisionSeats;
  window.App.stepSelfKey = stepSelfKey;
  window.App.finalBoxRows = finalBoxRows;
  window.App.renderFinalBox = renderFinalBox;
  window.App.features = FEATURES;
  window.App.searchState = Sc;
  window.App.analyzeState = An;
  window.App.loadMeta = loadMeta;
  window.App.anSetMode = anSetMode;
  window.App.anTargetDb = anTargetDb;
  window.App.fillExtendSelect = fillExtendSelect;
  window.App.featPanelState = FeatPanel;
  window.App.frameSeatOf = frameSeatOf;
  window.App.redMarkOf = redMarkOf;
  window.App.nagaFrameOf = nagaFrameOf;
  window.App.setAiModel = setAiModel;
  window.App.resetAiModel = resetAiModel;
  window.App.aiModelList = aiModelList;
  window.App.aiChoiceOf = aiChoiceOf;
  window.App.aiNormalize = aiNormalize;
  window.App.aiFrame = aiFrame;
  window.App.aiFrameKeys = aiFrameKeys;
  window.App.aiFrameHasData = aiFrameHasData;
  window.App.syncAiModel = syncAiModel;
  window.App.setAiPref = setAiPref;
  window.App.aiFoldFrame = aiFoldFrame;
  window.App.syncAiModelBtn = syncAiModelBtn;
  window.App.toggleAiModelMenu = toggleAiModelMenu;
  window.App.setWait = setWait;
  window.App.waitPayload = waitPayload;
  window.App.setAiMode = setAiMode;
  window.App.setAiPick = setAiPick;
  window.App.clearAiPlan = clearAiPlan;
  window.App.aiPayload = aiPayload;
  window.App.renderAiPlan = renderAiPlan;
  window.App.vocalTextOf = vocalTextOf;
  window.App.vocalForFrame = vocalForFrame;
  window.App.setViewSeat = setViewSeat;
  window.App.viewMenuRows = viewMenuRows;
  window.App.toggleViewMenu = toggleViewMenu;
  window.App.syncViewBtn = syncViewBtn;
  window.App.placeViewMenu = placeViewMenu;
  window.App.isKeyFrame = isKeyFrame;
  window.App.nagaFrameChoices = nagaFrameChoices;
  window.App.nagaKindOfName = nagaKindOfName;
  window.App.nagaChiPair = nagaChiPair;
  window.App.nagaOptions = nagaOptions;
  window.App.renderNagaPanel = renderNagaPanel;
  window.App.syncFeatPanel = syncFeatPanel;
  window.App.renderFeatMode = renderFeatMode;
  window.App.markUsedFeatures = markUsedFeatures;
  window.App.anProgressStart = anProgressStart;
  window.App.anProgressTick = anProgressTick;
  window.App.anProgressText = anProgressText;
  window.App.anProgressDone = anProgressDone;
  window.App.downloadState = Dl;
  window.App.dlSetMode = dlSetMode;
  window.App.dlFillDefaultDir = dlFillDefaultDir;
  window.App.dlReadFile = dlReadFile;
  window.App.dlStart = dlStart;
  window.App.dlPoll = dlPoll;
  window.App.baseName = baseName;
  window.App.loadHealth = loadHealth;
  window.App.syncOpenMode = syncOpenMode;
  window.App.loadCodeIndex = loadCodeIndex;
  window.App.renderCodeResults = renderCodeResults;
  window.App.openPaipuPath = openPaipuPath;
  window.App.openReplayView = openReplayView;
  window.App.resetReplay = resetReplay;
  window.App.showDropZone = showDropZone;
  window.App.dataManagerState = Dm;
  window.App.dmInit = dmInit;
  window.App.dmLoad = dmLoad;
  window.App.dmSwitchRoot = dmSwitchRoot;
  window.App.dmUp = dmUp;
  window.App.dmUpdate = dmUpdate;
  window.App.dmMkdir = dmMkdir;
  window.App.dmMove = dmMove;
  window.App.dmDelete = dmDelete;
  window.App.dmRmdir = dmRmdir;
  window.App.dmSelect = function (kind, path) {
    Dm.sel = (kind && path) ? { kind: kind, name: baseName(path), path: path } : null;
    dmUpdate();
  };
})();
