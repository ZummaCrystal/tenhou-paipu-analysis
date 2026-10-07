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

  /* 首页「载入示例牌谱」优先列出这些牌谱（第 1 轮下载所得，按 log_id 匹配）；
     数据目录里找不到时退化为目录里的前 5 个；服务没启动时只列清单（点选会给提示）。 */
  var SAMPLE_IDS = [
    '2026082919gm-00a9-0000-4e40cd3e',
    '2026082920gm-00a9-0000-5db954e6',
    '2026082921gm-00a9-0000-d2e544e6',
    '2026083020gm-00a9-0000-e9ce1efe',
    '2026083021gm-00a9-0000-d0810acf'
  ];

  /* 视为「关键事件」的动作：出牌 / 吃碰杠 / 立直 / 新宝牌 / 和了 / 流局 */
  var KEY = { discard: 1, call: 1, reach: 1, dora: 1, agari: 1, ryuukyoku: 1 };

  var AUTO_MS = 500;

  /* ---------------------------------------------------- 牌桌自适应缩放 */
  /* 为了让不同分辨率的显示器上观感一致，牌桌内部所有尺寸都以「一张牌的宽度 --tile-w」为单位。
     这里先把单位设成基准值量出牌桌的自然尺寸，再按可用空间等比缩放这个单位。
     面板里有几处固定像素的间隙，所以迭代两次逼近。 */
  var BASE_U = 30, MIN_U = 9, MAX_U = 34;

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
    version: '',         /* 软件版本号，来自 GET /api/features（m03580：界面显示 v0.1.0）*/
    schemaVersion: 0,    /* 数据库结构版本 */
    fileName: '',
    game: null,
    rounds: [],        /* rounds[i] = frames[] */
    roundIndex: 0,
    frameIndex: 0,
    selfSeat: 0,       /* 目前固定把玩家 0 放在下方（自家） */
    hideOthers: false,
    showList: true,
    auto: false,
    timer: null,
    /* 牌谱分析 / 牌谱检索相关状态 */
    dbName: '',        /* 当前选中的本地数据库名 */
    dbList: [],        /* 服务端 data/db 下的库 */
    items: [],         /* 当前条目列表（检索结果 或 全部浏览） */
    itemIndex: -1,     /* 当前正在查看的条目下标，-1 = 不在条目模式 */
    itemSource: '',    /* 'query' | 'browse' */
    cache: {},         /* log_id -> 牌谱文本，切换条目时避免重复下载 */
    /* 首页示例牌谱 / 用户数据目录（来自 /api/health 与 /api/scan；用户 m00178 第 8、9 条） */
    samples: [],       /* 示例牌谱的绝对路径列表（数据目录可能不在项目里，必须用绝对路径） */
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
    if (name !== 'replay') { stopAuto(); } else { fitBoard(); }
    if (name === 'analyze' || name === 'search') { refreshDbs(); }
    if (name === 'data') { dmInit(); }
  }

  function setFileInfo(text) { $('fileInfo').textContent = text; }

  function homeMsg(text, warn) {
    var m = $('homeMsg');
    m.textContent = text || '';
    m.classList.toggle('warn', !!warn);
  }

  /* -------------------------------------------------------- 载入牌谱 */
  function loadText(text, name) {
    stopAuto();
    var game;
    try {
      game = MJLOG.parse(text);
    } catch (err) {
      homeMsg('牌谱解析失败：' + (err && err.message ? err.message : err), true);
      setFileInfo('解析失败');
      return false;
    }
    if (!game || !game.rounds || !game.rounds.length) {
      homeMsg('牌谱里没有找到任何对局（缺少 INIT 标签）。', true);
      setFileInfo('未载入牌谱');
      return false;
    }

    App.game = game;
    App.fileName = name || '(未命名)';
    App.rounds = REPLAY.buildGame(game);
    App.roundIndex = 0;
    App.frameIndex = 0;

    buildRoundSelect();
    setFileInfo(App.fileName + ' · 共 ' + game.rounds.length + ' 局');
    $('rpFile').textContent = App.fileName;
    $('rpOpenBar').classList.add('hidden');   /* 载入牌谱后收起「选择牌谱文件」栏 */
    homeMsg('');
    setView('replay');
    render();
    fitBoard();
    return true;
  }

  function readFile(file) {
    if (!file) { return; }
    setFileInfo('读取中… ' + file.name);
    var fr = new FileReader();
    fr.onload = function () { loadText(String(fr.result), file.name); };
    fr.onerror = function () {
      homeMsg('读取文件失败：' + file.name, true);
      setFileInfo('未载入牌谱');
    };
    fr.readAsText(file, 'utf-8');
  }

  /* 载入首页下拉框里选中的示例牌谱：走服务端接口读绝对路径。用户 m00178 第 8 条：
     数据目录固定到 %LOCALAPPDATA% 之后，fetch('data/xxx.xml') 这种相对路径必然 404
     （页面在 /web/ 下，实际请求 /web/data/xxx.xml，而 web/data 根本不存在）。 */
  function loadSample() {
    var sel = $('sampleSelect');
    var path = sel ? sel.value : '';
    if (!path) {
      homeMsg('示例牌谱不可用（数据目录里没有牌谱，或本地服务没启动）。'
        + '可以在播放视图里用「选择牌谱文件」。', true);
      return;
    }
    homeMsg('正在载入 ' + baseName(path) + ' …');
    api('/api/read?path=' + encodeURIComponent(path)).then(function (d) {
      loadText(d.text || '', baseName(path));
    })['catch'](function (err) {
      homeMsg('载入示例失败（' + (err && err.message ? err.message : err) + '）。'
        + '请确认本地服务已启动（python server.py），或改用「选择牌谱文件」。', true);
      setFileInfo('未载入牌谱');
    });
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
    if (i < 0) { i = 0; }
    if (i > frames.length - 1) { i = frames.length - 1; }
    App.frameIndex = i;
    render();
  }

  function stepKey(dir) {
    var frames = App.rounds[App.roundIndex];
    if (!frames) { return; }
    var i = App.frameIndex + dir;
    if (dir < 0) {
      for (; i > 0; i--) { if (frames[i].ev && KEY[frames[i].ev.type]) { break; } }
    } else {
      for (; i < frames.length; i++) { if (frames[i].ev && KEY[frames[i].ev.type]) { break; } }
      if (i > frames.length - 1) { i = frames.length - 1; }
    }
    setFrame(i);
  }

  function onAct(act) {
    var frames = App.rounds[App.roundIndex] || [];
    switch (act) {
      case 'first':     setFrame(0); break;
      case 'prev':      setFrame(App.frameIndex - 1); break;
      case 'next':      setFrame(App.frameIndex + 1); break;
      case 'last':      setFrame(frames.length - 1); break;
      case 'prevKey':   stepKey(-1); break;
      case 'nextKey':   stepKey(1); break;
      case 'prevRound': setRound(App.roundIndex - 1, 0); break;
      case 'nextRound': setRound(App.roundIndex + 1, 0); break;
      case 'auto':      if (App.auto) { stopAuto(); } else { startAuto(); } break;
      case 'others':    App.hideOthers = !App.hideOthers; syncOthers(); render(); break;
    }
  }

  /* -------------------------------------------------------- 自动播放 */
  function autoBtn() { return document.querySelector('#controls button[data-act="auto"]'); }

  function startAuto() {
    stopAuto();
    App.auto = true;
    var b = autoBtn();
    if (b) { b.classList.add('on'); b.textContent = '⏸ 暂停'; }
    App.timer = setInterval(function () {
      var frames = App.rounds[App.roundIndex];
      if (!frames) { stopAuto(); return; }
      if (App.frameIndex >= frames.length - 1) {
        if (App.roundIndex < App.rounds.length - 1) { setRound(App.roundIndex + 1, 0); }
        else { stopAuto(); }
        return;
      }
      setFrame(App.frameIndex + 1);
    }, AUTO_MS);
  }

  function stopAuto() {
    if (App.timer) { clearInterval(App.timer); App.timer = null; }
    App.auto = false;
    var b = autoBtn();
    if (b) { b.classList.remove('on'); b.textContent = '▶ 自动播放'; }
  }

  /* -------------------------------------------------------- 渲染 */
  /* ① 显示/隐藏他家手牌：按钮文字随状态切换，隐藏时按钮高亮 */
  function othersBtn() { return $('btnOthers'); }
  function syncOthers() {
    var b = othersBtn();
    if (!b) { return; }
    b.classList.toggle('on', App.hideOthers);
    b.textContent = App.hideOthers ? '显示他家手牌' : '隐藏他家手牌';
    b.title = App.hideOthers ? '当前：他家手牌已隐藏' : '当前：他家手牌可见';
  }

  function setDisabled(act, off) {
    var b = document.querySelector('#controls button[data-act="' + act + '"]');
    if (b) { b.disabled = !!off; }
  }

  function syncButtons() {
    var frames = App.rounds[App.roundIndex] || [];
    var last = frames.length - 1;
    var first = App.frameIndex <= 0;
    var end = App.frameIndex >= last;
    setDisabled('first', first);
    setDisabled('prev', first);
    setDisabled('prevKey', first);
    setDisabled('next', end);
    setDisabled('nextKey', end);
    setDisabled('last', end);
    setDisabled('auto', last <= 0);
    setDisabled('prevRound', App.roundIndex <= 0);
    setDisabled('nextRound', App.roundIndex >= App.rounds.length - 1);
  }

  function render() {
    if (!App.game) { return; }
    var frames = App.rounds[App.roundIndex];
    if (!frames) { return; }
    var st = frames[App.frameIndex].state;

    UI.renderBoard($('board'), st, { selfSeat: App.selfSeat, hideOthers: App.hideOthers });

    $('rpFrame').textContent = App.frameIndex + ' / ' + (frames.length - 1) + ' 步';
    $('rpDesc').textContent = st.desc || '';

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

    $('eventList').classList.toggle('off', !App.showList);
    if (App.showList) { UI.renderEventList($('eventListBody'), frames, App.frameIndex); }

    syncButtons();
    syncOthers();
    syncFeatPanel();
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
  var An = { files: [] };

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
      if (!An.files.length) { box.appendChild(plainRow('（这个目录里没有 .xml 牌谱文件）', 'muted')); }
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
    var dir = valOf('anSourceDir', 'data');
    setMsg('anMsg', '正在扫描 ' + dir + ' …');
    api('/api/scan?dir=' + encodeURIComponent(dir)).then(function (d) {
      renderFileList(d.files);
      setMsg('anMsg', '找到 ' + d.count + ' 个牌谱文件：（' + d.dir + '）');
    })['catch'](function (e) { setMsg('anMsg', '扫描失败：' + e.message, true); });
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
        + (dbs[i].compatible === false ? ' ⚠ 版本不匹配' : '') + '）';
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
      + (db.compatible === false ? ' · ⚠ 版本不匹配，不能扩充，请删除后重新分析' : ' · 可扩充');
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
      + (db.compatible === false ? ' ⚠ 版本不匹配（不能扩充 / 加载）' : '');
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
  var Sc = { conds: [], pageSize: 100 };

  function scDbPayload() {
    var custom = valOf('scDbPath', '');
    if (custom) { return { db: custom }; }
    var sel = $('scDbSelect');
    var name = (sel && sel.value) || App.dbName || '';
    return name ? { db_name: name } : {};
  }

  function renderFeatSelect() {
    var sel = $('scFeatSelect');
    if (!sel) { return; }
    clearNode(sel);
    var used = {};
    for (var i = 0; i < Sc.conds.length; i++) { used[Sc.conds[i].key] = 1; }
    for (var j = 0; j < FEATURES.length; j++) {
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
    if (!Sc.conds.length) { setMsg('scMsg', '「牌谱特征」框还是空的：请先添加至少一条特征。', true); return null; }
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
    if (info) { info.textContent = rows.length ? ('显示 ' + rows.length + ' 条') : ''; }
  }

  function runQuery() {
    var conds = checkConds();
    if (!conds) { return; }
    markUsedFeatures();
    var dbq = scDbPayload();
    if (!dbq.db && !dbq.db_name) { setMsg('scMsg', '请先选择（或填写）要检索的本地数据库文件。', true); return; }
    var body = { conds: conds, limit: Sc.pageSize, offset: 0 };
    body.db = dbq.db || null;
    body.db_name = dbq.db || null ? null : dbq.db_name;
    setMsg('scMsg', '检索中…');
    api('/api/query', body).then(function (d) {
      App.items = d.rows || [];
      App.itemIndex = -1;
      App.itemSource = 'query';
      renderResults(App.items);
      syncItemNav();
      setMsg('scMsg', '命中 ' + d.total + ' 个打点帧（条件：' + (d.used || []).join('、')
        + '）。点条目跳转到对应帧；条目名＝牌谱特征码 + 局况 + 本场 + 巡目 + 风位。');
    })['catch'](function (e) { setMsg('scMsg', '检索失败：' + e.message, true); });
  }

  function browseAll() {
    var dbq = scDbPayload();
    if (!dbq.db && !dbq.db_name) { setMsg('scMsg', '请先选择（或填写）要浏览的本地数据库文件。', true); return; }
    var body = { limit: 0, offset: 0 };
    body.db = dbq.db || null;
    body.db_name = dbq.db || null ? null : dbq.db_name;
    setMsg('scMsg', '正在读取全部条目…');
    api('/api/browse', body).then(function (d) {
      App.items = d.rows || [];
      App.itemIndex = -1;
      App.itemSource = 'browse';
      renderResults(App.items);
      syncItemNav();
      setMsg('scMsg', '全部浏览：共 ' + d.total + ' 个打点帧（按牌谱特征码顺序）。点任意条目进入阅图模式，'
        + '再用「上一条目 / 下一条目」切换。');
    })['catch'](function (e) { setMsg('scMsg', '读取失败：' + e.message, true); });
  }

  /* --------------------------------------------------- 条目导航 / 跳转 */
  function syncItemNav() {
    var info = $('itemInfo'), p = $('btnPrevItem'), n = $('btnNextItem');
    var on = App.itemIndex >= 0 && App.items.length > 0;
    if (info) {
      info.classList.toggle('hidden', !on);
      var kindName = '';
      if (on) {
        var k = String(App.items[App.itemIndex].kind || 'draw');
        kindName = '｜ ' + (k === 'chi' ? '吃后帧' : (k === 'pon' ? '碰后帧' : '摸牌帧'));
      }
      info.textContent = on ? ('条目 ' + (App.itemIndex + 1) + ' / ' + App.items.length
        + '（' + (App.itemSource === 'browse' ? '全部浏览' : '检索结果') + '）' + kindName) : '';
    }
    if (p) { p.classList.toggle('hidden', !on); p.disabled = !on || App.itemIndex <= 0; }
    if (n) { n.classList.toggle('hidden', !on); n.disabled = !on || App.itemIndex >= App.items.length - 1; }
  }

  function installGame(text, logId) {
    loadText(text, logId + '.xml');
  }

  function jumpRow(it) {
    var ri = parseInt(it.round_index, 10);
    if (!(ri >= 0) || ri >= App.rounds.length) { setMsg('scMsg', '这个条目所在的对局不在牌谱里。', true); return; }
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
    api('/api/read?path=' + encodeURIComponent(it.log_path || ('data/' + logId + '.xml'))).then(function (d) {
      App.cache[logId] = d.text;
      installGame(d.text, logId);
      jumpRow(it);
      setMsg('scMsg', '');
    })['catch'](function (e) { setMsg('scMsg', '载入牌谱失败：' + e.message, true); });
  }

  function stepItem(dir) {
    if (App.itemIndex < 0) { return; }
    openItem(App.itemIndex + dir);
  }

  /* ------------------------------------------------ 静态帧的特征串 */
  function gameLogId() {
    var n = String(App.fileName || '');
    return n.replace(/\.(xml|mjlog)$/i, '') || '(未命名)';
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

  function copyFrameKey() {
    var el = $('frameKey');
    if (!el) { return; }
    var text = el.textContent || '';
    if (!text) { return; }
    var done = function () {
      el.classList.add('copied');
      window.setTimeout(function () { el.classList.remove('copied'); }, 700);
    };
    var fallback = function () {
      var ta = document.createElement('textarea');
      ta.value = text;
      el.appendChild(ta);
      if (ta.select) { ta.select(); }
      try { if (document.execCommand) { document.execCommand('copy'); } } catch (e) { /* 忽略 */ }
      el.removeChild(ta);
      done();
    };
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  }


  /* ------------------------------------------- 帧特征面板（33 个特征） */
  /* 当前帧的「打点视角」座位：摸牌帧 = 摸牌者；吃/碰后等待出牌的帧 = 鸣牌者；其他帧 = null */
  function frameSeatOf(st) {
    if (!st) { return null; }
    if (st.drawn) { return st.drawn.player; }
    var rnd = App.game && App.game.rounds[App.roundIndex];
    var ev = rnd && rnd.events[App.frameIndex - 1];
    if (ev && ev.type === 'call' && (ev.callType === 'chi' || ev.callType === 'pon')) { return ev.player; }
    return null;
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
    clearNode(box);
    if (FeatPanel.loading) { box.appendChild(plainRow('正在读取这一帧的特征…', 'muted')); return; }
    if (FeatPanel.error) { box.appendChild(plainRow('读取失败：' + FeatPanel.error, 'warn')); return; }
    var row = FeatPanel.row;
    if (!row) {
      box.appendChild(plainRow(App.game
        ? '当前帧没有打点行：只有「非自摸的摸牌帧」与「吃/碰后等待出牌的帧」才有特征值。'
        : '（未载入牌谱）', 'muted'));
      return;
    }
    var feats = row.feats || {}, used = 0;
    for (var i = 0; i < FEATURES.length; i++) {
      var f = FEATURES[i];
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
    box.appendChild(plainRow('共 ' + FEATURES.length + ' 个特征'
      + (used ? ('（高亮 ' + used + ' 条 = 当前检索用到的）') : ''), 'muted'));
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
      if (info) { info.textContent = ''; }
      renderFeatPanel();
      return;
    }
    if (info) { info.textContent = frameKeyText(); }

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
    api('/api/scan?dir=' + encodeURIComponent(dirAbs || rel)).then(function (d) {
      clearNode(box);
      box.appendChild(plainRow('目录 ' + d.dir + '：' + d.count + ' 个牌谱', 'muted'));
      var src = $('anSourceDir');
      if (src && (!src.value || src.value === 'data')) { src.value = rel; }
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

  function fillSamples() {
    var sel = $('sampleSelect');
    if (!sel) { return; }
    var rows = App.samples || [];
    clearNode(sel);
    if (!rows.length) {
      /* 服务没启动 / 数据目录里还没有牌谱：仍然列出固定清单，保证首页结构稳定 */
      for (var i = 0; i < SAMPLE_IDS.length; i++) {
        var o = document.createElement('option');
        o.value = '';
        o.textContent = SAMPLE_IDS[i] + '.xml';
        sel.appendChild(o);
      }
      return;
    }
    for (var j = 0; j < rows.length; j++) {
      var op = document.createElement('option');
      op.value = rows[j];
      op.textContent = baseName(rows[j]);
      sel.appendChild(op);
    }
  }

  /* 示例牌谱清单 = /api/health 的 paipu_dir（数据目录）+ /api/scan 的文件列表。
     用户 m00178 第 8 条：数据目录将来固定在 %LOCALAPPDATA% 下，必须用服务端给的绝对路径。 */
  function loadSamples() {
    return api('/api/health').then(function (h) {
      App.dataRoot = h.data_root || '';
      App.dbDir = h.db_dir || '';
      App.paipuDir = h.paipu_dir || '';
      if (!App.paipuDir) { return []; }
      return api('/api/scan?dir=' + encodeURIComponent(App.paipuDir)).then(function (d) {
        return (d && d.files) || [];
      });
    })['catch'](function () {
      return [];
    }).then(function (files) {
      var list = files || [];
      var seen = {}, i;
      for (i = 0; i < list.length; i++) { seen[baseName(list[i]).replace(/\.xml$/i, '')] = list[i]; }
      var picked = [];
      for (i = 0; i < SAMPLE_IDS.length; i++) {
        if (seen[SAMPLE_IDS[i]]) { picked.push(seen[SAMPLE_IDS[i]]); }
      }
      for (i = 0; i < list.length && picked.length < SAMPLE_IDS.length; i++) {
        if (picked.indexOf(list[i]) < 0) { picked.push(list[i]); }
      }
      App.samples = picked;
      fillSamples();
      return picked;
    });
  }

  function initDrop() {
    var dz = $('dropZone');
    ['dragenter', 'dragover'].forEach(function (t) {
      dz.addEventListener(t, function (e) { e.preventDefault(); dz.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (t) {
      dz.addEventListener(t, function (e) { e.preventDefault(); dz.classList.remove('over'); });
    });
    dz.addEventListener('drop', function (e) {
      var fs = e.dataTransfer && e.dataTransfer.files;
      if (fs && fs.length) { readFile(fs[0]); }
    });
    /* 防止拖到页面其它位置时浏览器直接打开该文件 */
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('drop', function (e) { e.preventDefault(); });
  }

  function init() {
    fillSamples();
    loadSamples();
    initDrop();

    $('btnPickFile').addEventListener('click', function () { $('fileInput').click(); });
    $('fileInput').addEventListener('change', function () {
      var f = this.files && this.files[0];
      this.value = '';
      readFile(f);
    });
    $('btnLoadSample').addEventListener('click', loadSample);
    $('btnGoSearch').addEventListener('click', function () { setView('search'); });
    bind('btnGoReplay', function () {
      $('rpOpenBar').classList.remove('hidden');
      homeMsg('请选择一个牌谱文件，或载入示例牌谱。');
      setView('replay');
    });
    bind('btnOpenPicker', function () { $('rpOpenBar').classList.toggle('hidden'); });
    bind('btnGoAnalyze', function () { setView('analyze'); });

    /* 牌谱分析 */
    bind('btnScan', scanFiles);
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

    /* 条目导航 + 特征串复制 */
    bind('btnPrevItem', function () { stepItem(-1); });
    bind('btnNextItem', function () { stepItem(1); });
    bind('frameKey', copyFrameKey);

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
        if (v === 'replay' && !App.game) {
          /* 没载入牌谱也允许进播放视图：入口（选择文件 / 载入示例）就在那里 */
          $('rpOpenBar').classList.remove('hidden');
          homeMsg('请选择一个牌谱文件，或载入示例牌谱。');
        }
        setView(v);
      });
    }

    $('controls').addEventListener('click', function (e) {
      var b = e.target && e.target.closest ? e.target.closest('button[data-act]') : null;
      if (b) { onAct(b.getAttribute('data-act')); }
    });

    $('roundSelect').addEventListener('change', function () {
      setRound(parseInt(this.value, 10), 0);
    });

    $('eventListBody').addEventListener('click', function (e) {
      var row = e.target && e.target.closest ? e.target.closest('.ev-row') : null;
      if (row) { setFrame(parseInt(row.getAttribute('data-idx'), 10)); }
    });

    $('chkList').addEventListener('change', function () {
      App.showList = !!this.checked;
      render();
      fitBoard();
    });

    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', fitBoard);

    syncOthers();
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
  window.App.api = api;
  window.App.refreshDbs = refreshDbs;
  window.App.frameKeyText = frameKeyText;
  window.App.openItem = openItem;
  window.App.setRound = setRound;
  window.App.setFrame = setFrame;
  window.App.features = FEATURES;
  window.App.searchState = Sc;
  window.App.analyzeState = An;
  window.App.loadMeta = loadMeta;
  window.App.anSetMode = anSetMode;
  window.App.anTargetDb = anTargetDb;
  window.App.fillExtendSelect = fillExtendSelect;
  window.App.featPanelState = FeatPanel;
  window.App.frameSeatOf = frameSeatOf;
  window.App.syncFeatPanel = syncFeatPanel;
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
  window.App.fillSamples = fillSamples;
  window.App.loadSamples = loadSamples;
  window.App.loadSample = loadSample;
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
