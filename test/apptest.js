/* apptest.js — 用「极简假 DOM + 从 web/index.html 抽出的真实 id/按钮名」驱动 web/js/app.js，
 * 在没有浏览器的环境下验证整套交互：载入 -> 渲染 -> 步进 -> 局切换 -> 事件列表 -> 键盘 -> 自动播放。
 */
'use strict';
var fs = require('fs');
var base = 'D:/coding/dsh_workspace/simple/tenhou-paipu-analysis';

/* ============================================================ 假 DOM */
function El(tag) {
  this.tagName = String(tag).toUpperCase();
  this.childNodes = [];
  this._cls = [];
  this.attrs = {};
  this._text = '';
  this.parent = null;
  this.listeners = {};
  this.disabled = false;
  this.checked = false;
  this.value = '';
  this.src = '';
  this.style = {};
  this.scrollTop = 0;
  this.offsetTop = 0;
  this.offsetHeight = 20;
  this.clientHeight = 1000;
  this.files = [];
}
Object.defineProperty(El.prototype, 'className', {
  get: function () { return this._cls.join(' '); },
  set: function (v) { this._cls = String(v).split(/\s+/).filter(Boolean); }
});
Object.defineProperty(El.prototype, 'id', {
  get: function () { return this.attrs.id || ''; },
  set: function (v) { this.attrs.id = String(v); }
});
Object.defineProperty(El.prototype, 'classList', {
  get: function () {
    var self = this;
    return {
      add: function () { for (var i = 0; i < arguments.length; i++) { if (self._cls.indexOf(arguments[i]) < 0) { self._cls.push(arguments[i]); } } },
      remove: function () { for (var i = 0; i < arguments.length; i++) { var k = self._cls.indexOf(arguments[i]); if (k >= 0) { self._cls.splice(k, 1); } } },
      toggle: function (c, on) { if (on === undefined) { on = self._cls.indexOf(c) < 0; } if (on) { this.add(c); } else { this.remove(c); } return !!on; },
      contains: function (c) { return self._cls.indexOf(c) >= 0; }
    };
  }
});
Object.defineProperty(El.prototype, 'firstChild', { get: function () { return this.childNodes[0] || null; } });
Object.defineProperty(El.prototype, 'textContent', {
  get: function () { var s = this._text; for (var i = 0; i < this.childNodes.length; i++) { s += this.childNodes[i].textContent; } return s; },
  set: function (v) { this._text = String(v); this.childNodes = []; }
});
/* 假 DOM 的尺寸桩：真实浏览器里 placeViewMenu() 用 getBoundingClientRect 定位上拉框 */
El.prototype.getBoundingClientRect = function () {
  var l = this.offsetLeft || 0, t = this.offsetTop || 0;
  var w = this.offsetWidth || 0, h = this.offsetHeight || 0;
  return { left: l, top: t, width: w, height: h, right: l + w, bottom: t + h };
};
El.prototype.appendChild = function (c) { c.parent = this; this.childNodes.push(c); return c; };
El.prototype.removeChild = function (c) { var i = this.childNodes.indexOf(c); if (i >= 0) { this.childNodes.splice(i, 1); c.parent = null; } return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return (k in this.attrs) ? this.attrs[k] : null; };
El.prototype.hasAttribute = function (k) { return k in this.attrs; };
El.prototype.addEventListener = function (t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); };
El.prototype.fire = function (t, ev) {
  ev = ev || {};
  ev.type = t;
  if (!ev.target) { ev.target = this; }
  if (!ev.preventDefault) { ev.preventDefault = function () {}; }
  var ls = this.listeners[t] || [];
  for (var i = 0; i < ls.length; i++) { ls[i].call(this, ev); }
  /* 冒泡 */
  var n = this.parent;
  while (n) { var l2 = n.listeners[t] || []; for (var j = 0; j < l2.length; j++) { l2[j].call(n, ev); } n = n.parent; }
  return ev;
};
El.prototype.closest = function (sel) { var n = this; while (n) { if (matchPart(n, sel)) { return n; } n = n.parent; } return null; };
El.prototype.querySelector = function (sel) { var all = walk(this, []); for (var i = 0; i < all.length; i++) { if (matches(all[i], sel)) { return all[i]; } } return null; };
El.prototype.querySelectorAll = function (sel) { var all = walk(this, []), out = []; for (var i = 0; i < all.length; i++) { if (matches(all[i], sel)) { out.push(all[i]); } } return out; };

/* 选择器：支持 '#id' / '.cls' / 'tag' / 'tag[attr]' / 'tag[attr="v"]' / '.a.b'，空格为后代组合 */
function matchPart(node, part) {
  if (!node || !node.tagName) { return false; }
  var m = /^([a-zA-Z]*)((?:[.#][A-Za-z0-9_-]*|\[[A-Za-z0-9_-]+(?:="[^"]*")?\])*)$/.exec(part);
  if (!m) { return false; }
  if (m[1] && node.tagName !== m[1].toUpperCase()) { return false; }
  var rest = m[2], re = /([.#])([A-Za-z0-9_-]+)|\[([A-Za-z0-9_-]+)(?:="([^"]*)")?\]/g, t;
  while ((t = re.exec(rest))) {
    if (t[1] === '.') { if (!node.classList.contains(t[2])) { return false; } }
    else if (t[1] === '#') { if (node.id !== t[2]) { return false; } }
    else {
      if (!node.hasAttribute(t[3])) { return false; }
      if (t[4] !== undefined && node.getAttribute(t[3]) !== t[4]) { return false; }
    }
  }
  return true;
}
function matches(node, sel) {
  var parts = String(sel).trim().split(/\s+/);
  if (!matchPart(node, parts[parts.length - 1])) { return false; }
  var n = node.parent;
  for (var i = parts.length - 2; i >= 0; i--) {
    while (n && !matchPart(n, parts[i])) { n = n.parent; }
    if (!n) { return false; }
    n = n.parent;
  }
  return true;
}
function walk(node, out) { for (var i = 0; i < node.childNodes.length; i++) { out.push(node.childNodes[i]); walk(node.childNodes[i], out); } return out; }

/* =============================================== 从 index.html 抽出 id / 按钮 */
var html = fs.readFileSync(base + '/web/index.html', 'utf8');
/* 抽出 index.html 里带 id 的元素（连标签名一起，否则 button 选择器匹配不上） */
var IDS = [];
(html.match(/<([A-Za-z][A-Za-z0-9]*)[^>]*\sid="([A-Za-z0-9_-]+)"/g) || []).forEach(function (s) {
  var m = /^<([A-Za-z][A-Za-z0-9]*)/.exec(s);
  var i2 = /id="([A-Za-z0-9_-]+)"/.exec(s);
  IDS.push({ tag: m[1], id: i2[1] });
});
/* 抽出所有带 data-act 的按钮（含它在 index.html 里的 id） */
var BTNS = [];
(html.match(/<button[^>]*>/g) || []).forEach(function (tag) {
  var a = /data-act="([A-Za-z]+)"/.exec(tag);
  if (!a) { return; }
  var i2 = /id="([A-Za-z0-9_-]+)"/.exec(tag);
  BTNS.push({ act: a[1], id: i2 ? i2[1] : '' });
});
var VIEWS_ATTR = [];
(html.match(/data-view="([A-Za-z]+)"/g) || []).forEach(function (s) { VIEWS_ATTR.push(s.slice(11, -1)); });

var root = new El('body');
var byId = {};
IDS.forEach(function (d) {
  var e = new El(d.tag);
  e.id = d.id;
  byId[d.id] = e;
  root.appendChild(e);
});
/* #controls 的子按钮：复用同 id 的元素，并把它挪进 #controls（app.js 靠 #controls 事件代理） */
BTNS.forEach(function (b) {
  var e = (b.id && byId[b.id]) ? byId[b.id] : new El('button');
  if (e.parent === root) { root.removeChild(e); }
  if (b.id && !byId[b.id]) { byId[b.id] = e; e.id = b.id; }
  e.setAttribute('data-act', b.act);
  byId.controls.appendChild(e);
});
/* .tab 页签 */
VIEWS_ATTR.forEach(function (v) {
  var t = new El('button');
  t.className = 'tab';
  t.setAttribute('data-view', v);
  root.appendChild(t);
});

var documentListeners = {};
global.document = {
  readyState: 'complete',
  body: root,
  createElement: function (t) { return new El(t); },
  getElementById: function (id) { return byId[id] || null; },
  querySelector: function (sel) { var all = walk(root, []); for (var i = 0; i < all.length; i++) { if (matches(all[i], sel)) { return all[i]; } } return null; },
  querySelectorAll: function (sel) { var all = walk(root, []), out = []; for (var i = 0; i < all.length; i++) { if (matches(all[i], sel)) { out.push(all[i]); } } return out; },
  addEventListener: function (t, fn) { (documentListeners[t] = documentListeners[t] || []).push(fn); }
};
global.window = global;
global.window.addEventListener = function () {};
global.FileReader = function () {};
global.fetch = function () { return Promise.reject(new Error('no network in test')); };

/* ============================================================ 加载被测代码 */
global.Tiles = require(base + '/web/js/tiles.js');
global.MJLOG = require(base + '/web/js/mjlog.js');
global.REPLAY = require(base + '/web/js/replay.js');
global.MJSFEAT = require(base + '/web/js/mjsfeat.js');
global.UI = require(base + '/web/js/ui.js');
require(base + '/web/js/app.js');

var App = global.App;

/* 第 22 轮：用户把全部牌谱移到了 data/paipu/<时间戳>/ ⇒ 递归收集，按特征码定位 */
var pathMod = require('path');
function walkXml(dir, out) {
  var ents = [];
  try { ents = fs.readdirSync(dir); } catch (e) { return out; }
  ents.forEach(function (n) {
    var p = pathMod.join(dir, n), st = null;
    try { st = fs.statSync(p); } catch (e) { return; }
    if (st.isDirectory()) { walkXml(p, out); }
    else if (/\.(tenhou|xml|mjlog)$/i.test(n)) { out.push(p); }   /* 用户 m05545 ② 后本地牌谱是 .tenhou */
  });
  return out;
}
var CORPUS = walkXml(base + '/data', []).sort();
function xmlPath(id) {
  /* id 可以带后缀（.tenhou / .xml / .mjlog）也可以不带：两边都剥掉后缀再比（用户 m05545 ②） */
  var key = id.replace(/\.(tenhou|xml|mjlog)$/i, '');
  for (var xi = 0; xi < CORPUS.length; xi++) {
    var n = CORPUS[xi].split(/[\\/]/).pop().replace(/\.(tenhou|xml|mjlog)$/i, '');
    if (n === key) { return CORPUS[xi]; }
  }
  throw new Error('data 下找不到 ' + key + ' 的牌谱（共 ' + CORPUS.length + ' 个）');
}
function xmlNames() { return CORPUS.map(function (p) { return p.split(/[\\/]/).pop(); }); }

/* ============================================================ 断言 */
var problems = [];
function check(ok, msg) { if (!ok) { problems.push(msg); } console.log((ok ? '  OK   ' : '  FAIL ') + msg); }
function countTiles(node) {
  var n = 0;
  (function w(x) { if (x._cls && x._cls.indexOf('tile') >= 0) { n++; } for (var i = 0; i < x.childNodes.length; i++) { w(x.childNodes[i]); } })(node);
  return n;
}
function countCls(node, cls) {
  var n = 0;
  (function w(x) { if (x._cls && x._cls.indexOf(cls) >= 0) { n++; } for (var i = 0; i < x.childNodes.length; i++) { w(x.childNodes[i]); } })(node);
  return n;
}
function curFrame() { return App.rounds[App.roundIndex][App.frameIndex]; }
function boardPlayer(seat) {
  var areas = ['bottom', 'right', 'top', 'left'];
  var cell = byId.board.querySelector('.cell-' + areas[seat]);
  return cell ? cell.querySelector('.p-rot') : null;
}

/* ============================================================ 1. 首页 */
console.log('=== 1. 初始状态 ===');
check(App && App.view === 'home', 'App 已初始化，当前视图 = ' + App.view);
check(byId['view-replay'].classList.contains('hidden'), '播放视图初始隐藏');
check(!byId['view-home'].classList.contains('hidden'), '首页初始可见');
/* 用户 m03175 ①③④⑤⑥：删掉「事件列表」勾选项与「示例牌谱」，改成浏览选择 / 按特征码搜索 */
check(!byId.chkList, '工具栏不再有「事件列表」勾选项（用户 m03175 ①）');
check(!byId.sampleSelect && !byId.btnLoadSample, '示例牌谱下拉与「载入」按钮已删除（用户 m03175 ③）');
check(byId.rpModeBrowse && byId.rpModeSearch && byId.codeInput && byId.codeResults,
      '打开牌谱栏有「浏览选择 / 按特征码搜索」两种互斥方式与结果框（用户 m03175 ④⑤）');
check(byId.btnPickFile.disabled === false && byId.codeInput.disabled === true,
      '默认是「浏览选择」：按钮可用、特征码输入框禁用（互斥）');
check(!byId.dropZone.classList.contains('hidden'), '没载入牌谱时拖放提示显示在牌桌区域（用户 m03175 ⑥）');
byId.boardBox.fire('dragover', { target: byId.boardBox });
check(byId.dropZone.classList.contains('over'), '拖到牌桌区域时拖放框高亮');
byId.boardBox.fire('dragleave', { target: byId.boardBox });
check(!byId.dropZone.classList.contains('over'), '拖出后取消高亮');
var tabs = document.querySelectorAll('.tab');
check(tabs.filter(function (t) { return t.classList.contains('active'); }).length === 1, '恰好 1 个页签高亮');

/* ============================================================ 2. 载入 */
console.log('\n=== 2. 载入牌谱 ===');
var f = '2026083020gm-00a9-0000-e9ce1efe.xml';
var ok = App.loadText(fs.readFileSync(xmlPath(f.replace(/\.xml$/, '')), 'utf8'), f);
check(ok === true, 'loadText 返回 true');
check(App.view === 'replay', '自动切到播放视图');
check(App.rounds.length === 9, '解析出 ' + App.rounds.length + ' 局（期望 9）');
check(App.frameIndex === 0 && App.roundIndex === 0, '起始位于第 1 局第 0 帧');
check(byId.roundSelect.childNodes.length === 9, '局下拉框 ' + byId.roundSelect.childNodes.length + ' 项');
check(byId.roundSelect.childNodes[0].textContent.indexOf('東1局') >= 0, '第 1 项文本 = "' + byId.roundSelect.childNodes[0].textContent + '"');
check(byId['view-replay'].classList.contains('hidden') === false, '播放视图已显示');
check(countTiles(byId.board) > 0, '牌桌渲染出 ' + countTiles(byId.board) + ' 张牌');
check(byId.dropZone.classList.contains('hidden'), '载入牌谱后拖放提示隐藏（用户 m03175 ⑥）');
check(byId.eventListBody.childNodes.length === App.rounds[0].length, '事件列表行数 ' + byId.eventListBody.childNodes.length + ' = 帧数 ' + App.rounds[0].length);
check(byId.rpDesc === undefined, '描述条已删除（用户 m05131 ④）');
var cbtn0 = byId.controls.querySelectorAll('button');
check(cbtn0.length === 14, '控制面板 14 个按钮 = 两行七列（实际 ' + cbtn0.length + '）');
check(byId.controls.querySelector('button[data-act="auto"]') === null, '「自动播放」按钮已删除（用户 m05131 ④）');
var actsNew = ['allFirst', 'allLast', 'prevSelf', 'nextSelf'];
var actsOk = true;
for (var an = 0; an < actsNew.length; an++) {
  if (byId.controls.querySelector('button[data-act="' + actsNew[an] + '"]') === null) { actsOk = false; }
}
check(actsOk, '新增「开局 / 完场 / 上一自家决策 / 下一自家决策」四个按钮（用户 m05131 ④）');
/* 假 DOM 不解析按钮里的静态文字，改从 index.html 源码断言（用户 m05131 ③④） */
check(html.indexOf('上一决策') >= 0 && html.indexOf('下一决策') >= 0,
  '「上一/下一关键」已改名「上一/下一决策」（用户 m05131 ④）');
check(html.indexOf('本局开始') >= 0 && html.indexOf('本局结算') >= 0,
  '「开局/本局结束」已改名「本局开始/本局结算」（用户 m05131 ④）');
check(html.indexOf('\u2016\u25c0 开局') >= 0 && html.indexOf('\u2016\u25b6 完场') >= 0,
  '「开局 / 完场」= 双竖线 + 三角形（用户 m05131 ③④）');
check(html.indexOf('\u23ae\u25c0') < 0 && html.indexOf('\u23ae\u25b6') < 0,
  '按钮上不再用 \u23ae（积分延长符，字形偏高 ⇒ 竖线看起来上移；用户 m05131 ③）');
check(boardPlayer(0).querySelector('.tiles') !== null, '自家面板存在手牌区');

/* ============================================================ 2a. 天凤谱：AI 面板恒为空（用户 m09161）*/
console.log('\n=== 2a. 天凤谱：AI 决策面板恒为空、关键帧判定与 AI 无关 ===');
var nfTotal = 0, nfNull = 0;
for (var nri = 0; nri < App.rounds.length; nri++) {
  for (var nfi = 0; nfi < App.rounds[nri].length; nfi++) {
    App.roundIndex = nri; App.frameIndex = nfi; nfTotal++;
    if (App.aiFrame() === null) { nfNull++; }
  }
}
check(nfTotal > 0 && nfNull === nfTotal, '天凤谱 ' + nfTotal + ' 帧全部没有 AI 数据（aiFrame() = null，' + nfNull + ' 帧）');
App.roundIndex = 0;
var panelFrames = 0, panelEmpty = true;
for (var pfi = 0; pfi < App.rounds[0].length; pfi++) {
  App.frameIndex = pfi; App.renderNagaPanel(); panelFrames++;
  if (byId.nagaOptions.childNodes.length !== 0 || byId.nagaWho.textContent !== '' || byId.nagaHud.childNodes.length !== 0) { panelEmpty = false; }
}
check(panelEmpty, '天凤谱第 1 局 ' + panelFrames + ' 帧逐帧渲染后 AI 面板三块全空（用户 m00198 ⑤ / m09161）');
var fr0a = App.rounds[0], kfCount = 0, kfBad = 0, decOk = true;
for (var kfi = 1; kfi < fr0a.length; kfi++) {
  var kEv = fr0a[kfi].ev, kNext = fr0a[kfi + 1] ? fr0a[kfi + 1].ev : null, want = false;
  if (kEv.type === 'draw') {
    want = !(kNext && kNext.type === 'agari' && kNext.winner === kEv.player && kNext.fromWho === kEv.player);
  } else if (kEv.type === 'call') {
    want = (kEv.callType === 'chi' || kEv.callType === 'pon');
  } else if (kEv.type === 'discard') {
    want = MJSFEAT.responders(fr0a[kfi].state, kEv.player, MJLOG.kindOf(kEv.tile)).length > 0;
  }
  if (App.isKeyFrame(fr0a, kfi) !== want) { kfBad++; }
  if (want) { kfCount++; if (App.decisionSeats(fr0a, kfi).length === 0) { decOk = false; } }
  else if (App.decisionSeats(fr0a, kfi).length !== 0) { decOk = false; }
}
check(kfBad === 0 && kfCount > 0, '天凤谱关键帧判定只由牌局决定（' + kfCount + ' 个关键帧，' + kfBad + ' 处与期望不符）');
check(decOk, '天凤谱关键帧都有决策者、非关键帧没有（判定与 AI 数据无关）');
App.setFrame(0); App.stepSelfKey(1);
check(App.frameIndex > 0 && App.decisionSeats(App.rounds[App.roundIndex], App.frameIndex).indexOf(App.selfSeat) >= 0,
      '天凤谱「下一自家决策」照常可用（停在第 ' + App.frameIndex + ' 帧，自家 ' + App.selfSeat + ' 是决策者）');
App.setFrame(0);
/* ============================================================ 2b. NAGA 报告 */
console.log('\n=== 2b. 载入 NAGA 报告（服务端转出的内部 JSON） ===');
/* naga / ricochet 的报告是 gzip 压的 JSON（.json.gz），前端解析不了：/api/read 会先用
   mjscore/naga.py 转成与天凤 xml 同构的结构，再带一个 naga 段返回；前端只多一步
   JSON.parse + 记住 App.naga（用户 m00080 目标 2）。这里用最小合成样本走一遍前端链路。 */
var NAGA_HANDS = [];
for (var nh = 0; nh < 4; nh++) {
  var oneHand = [];
  for (var nt = 0; nt < 13; nt++) { oneHand.push(nh + nt * 4); }
  NAGA_HANDS.push(oneHand);
}
/* 合成 NAGA 帧数据（用户 m00198 ③ / m01518 ③）：打牌预测 = 34 项万分比，危险牌 = [4][34]，
   end_type / game_rank = 4×4。选项里放一个 5% 的，用来验证「只显示 >10%」。 */
var NAGA_DP = [];
for (var nd = 0; nd < 34; nd++) { NAGA_DP.push(0); }
NAGA_DP[0] = 6000;                    // 打 1m 60%
NAGA_DP[1] = 4500;                    // 打 2m 45%
NAGA_DP[2] = 500;                     // 打 3m  5% —— 应当被过滤掉
function nagaZeroM() { var a = []; for (var i = 0; i < 34; i++) { a.push(0); } return a; }
var NAGA_DS = [nagaZeroM(), nagaZeroM(), nagaZeroM(), nagaZeroM()];   // danger_s：下家
var NAGA_DT = [nagaZeroM(), nagaZeroM(), nagaZeroM(), nagaZeroM()];   // danger_t：対面
var NAGA_DK = [nagaZeroM(), nagaZeroM(), nagaZeroM(), nagaZeroM()];   // danger_k：上家
NAGA_DS[0][1] = 2000;                 // 自家 2m：下家危险 20%
NAGA_DT[0][0] = 4500;                 // 自家 1m：対面危险 45%
NAGA_DK[0][0] = 8000;                 // 自家 1m：上家危险 80%
var NAGA_ET = [[1221, 617, 3255, 1359], [1681, 1028, 1671, 1546],
  [6089, 7022, 4280, 6032], [1009, 1333, 794, 1063]];                 // 行 = 和了/放銃/横移/流局
var NAGA_GR = [[2208, 2474, 2609, 2706], [2155, 2538, 2674, 2631],
  [3068, 2476, 2242, 2212], [2697, 2362, 2474, 2465]];                 // 行 = 最终顺位 1..4 的概率
/* 危险牌的「座位 1 那一行」数据：验证轮到别家决策时条文跟着那一家（用户 m03710 ①） */
var NAGA_DS1 = [nagaZeroM(), nagaZeroM(), nagaZeroM(), nagaZeroM()];
var NAGA_DT1 = [nagaZeroM(), nagaZeroM(), nagaZeroM(), nagaZeroM()];
var NAGA_DK1 = [nagaZeroM(), nagaZeroM(), nagaZeroM(), nagaZeroM()];
NAGA_DK1[1][0] = 6000;               // 座位 1 的 1m：上家危险 60%
NAGA_DT1[1][0] = 3000;               // 座位 1 的 1m：対面危险 30%
NAGA_DS1[1][1] = 4000;               // 座位 1 的 2m：下家危险 40%
var NAGA_GAME = {
  meta: { names: ['A', 'B', 'C', 'D'], oya: 0, naga: true },
  rounds: [{
    init: { round: 0, combo: 0, kyotaku: 0, dices: [1, 1], dora: 0,
      scores: [25000, 25000, 25000, 25000], oya: 0, hands: NAGA_HANDS },
    events: [
      { type: 'draw', player: 0, tile: 52 },
      { type: 'discard', player: 0, tile: 52 },
      { type: 'draw', player: 1, tile: 53 },
      { type: 'discard', player: 1, tile: 53 }
    ]
  }],
  naga: {
    report_id: 'abc', types: { '0': 'ニシキ' }, version: [2, 2], model: 'ニシキ', model_index: 0,
    // 真实契约：naga 帧数 == 该局事件数（报告帧 j ↔ 我们的帧 j；我们末尾那一帧没有 naga 数据）
    rounds: [[
      { msg: 'start_kyoku', end_type: NAGA_ET, game_rank: NAGA_GR },
      { msg: 'tsumo', actor: 0, pai: '4s', reach: 500, dahai_pred: NAGA_DP, danger_s: NAGA_DS, danger_t: NAGA_DT,
        danger_k: NAGA_DK, end_type: NAGA_ET, game_rank: NAGA_GR },
      { msg: 'dahai', actor: 0, pai: '1m', huro: { '2': { '0': 2000, '4': 7500 } },
        end_type: NAGA_ET, game_rank: NAGA_GR },
      { msg: 'tsumo', actor: 1, pai: '8m', dahai_pred: NAGA_DP,
        danger_s: NAGA_DS1, danger_t: NAGA_DT1, danger_k: NAGA_DK1,
        end_type: NAGA_ET, game_rank: NAGA_GR }
    ]]
  }
};
var nagaOk = App.loadText(JSON.stringify(NAGA_GAME), 'abc.json.gz');
check(nagaOk === true, 'NAGA 报告 JSON 能直接载入（loadText 返回 true）');
check(!!App.naga && App.naga.model_index === 0 && App.naga.model === 'ニシキ',
  'App.naga 记录平衡形那一档模型：' + JSON.stringify(App.naga && App.naga.model));
check(App.rounds.length === 1 && App.rounds[0].length === 5,
  'NAGA 报告解析出 ' + App.rounds.length + ' 局 / 首局 ' + (App.rounds && App.rounds[0] ? App.rounds[0].length : 0) + ' 帧（4 事件 + 配牌帧）');
check(App.naga && App.naga.rounds[0].length === App.rounds[0].length - 1,
  'NAGA 帧数 == 该局事件数（' + (App.naga && App.naga.rounds[0] ? App.naga.rounds[0].length : -1) + ' == ' + (App.rounds[0].length - 1) + '）');
check(byId.roundSelect.childNodes[0].textContent.indexOf('東1局') >= 0,
  'NAGA 报告的局标签 = ' + byId.roundSelect.childNodes[0].textContent);
check(byId.fileInfo.textContent === 'abc.json.gz · 共 1 局', '文件信息 = ' + byId.fileInfo.textContent);
clickAct('next');
check(App.frameIndex === 1 && curFrame().ev.type === 'draw', 'NAGA 报告也能步进：帧 ' + App.frameIndex + ' 事件 ' + curFrame().ev.type);
check(byId.frameKey.textContent === 'abc 東一局 0本場 1巡目 東家',
  '特征串把 .json.gz 剥成特征码：' + byId.frameKey.textContent);
/* --- AI 决策模型切换（用户 m04556 ①）：标题按钮 + 向下生长的菜单，默认「无AI决策」 --- */
check(App.aiModel === -1 && byId.nagaModelBtn.textContent === '无AI决策',
  '默认「无AI决策」（天凤式展示）= ' + byId.nagaModelBtn.textContent + '（aiModel=' + App.aiModel + '）');
check(byId.nagaModelMenu.classList.contains('hidden'), '模型菜单默认收起');
check(countCls(byId.board, 'tbar') === 0 && byId.nagaOptions.childNodes.length === 0
  && byId.nagaHud.childNodes.length === 0 && byId.nagaWho.textContent === '',
  '「无AI决策」时概率条 / 决策表 / 右下 5 个数据全不画（= 天凤牌谱的展示方式，用户 m04556 ①）');
byId.nagaModelBtn.fire('click');
check(!byId.nagaModelMenu.classList.contains('hidden'), '点标题按钮展开模型菜单（向下生长）');
check(byId.nagaModelMenu.childNodes.length === 8 && byId.nagaModelMenu.textContent.indexOf('无AI决策') >= 0,
  '菜单 ' + byId.nagaModelMenu.childNodes.length + ' 行 = 无AI决策 + 7 个 AI 模型（第零类 7 项，用户 m05937 ② / m09507）');
check(byId.nagaModelMenu.childNodes[0].textContent === '无AI决策'
  && byId.nagaModelMenu.childNodes[1].textContent === 'NAGA-平衡 决策'
  && byId.nagaModelMenu.childNodes[2].textContent === 'NAGA-超副露 决策'
  && byId.nagaModelMenu.childNodes[3].textContent === 'NAGA-避四 决策'
  && byId.nagaModelMenu.childNodes[4].textContent === 'NAGA-争一 决策'
  && byId.nagaModelMenu.childNodes[5].textContent === 'Mortal-4.1-避四 决策'
  && byId.nagaModelMenu.childNodes[6].textContent === 'Mortal-4.1-平衡 决策'
  && byId.nagaModelMenu.childNodes[7].textContent === 'Mortal-4.1-争一 决策',
  '菜单行文本：无AI决策 / NAGA-平衡 / NAGA-超副露 / NAGA-避四 / NAGA-争一 / Mortal-4.1-避四 / Mortal-4.1-平衡 / Mortal-4.1-争一 决策');
check(byId.nagaModelMenu.childNodes[0].classList.contains('cur'), '当前项「无AI决策」带 .cur');
check(byId.nagaModelMenu.childNodes[2].classList.contains('disabled')
  && byId.nagaModelMenu.childNodes[3].classList.contains('disabled')
  && byId.nagaModelMenu.childNodes[4].classList.contains('disabled')
  && byId.nagaModelMenu.childNodes[5].classList.contains('disabled')
  && byId.nagaModelMenu.childNodes[6].classList.contains('disabled')
  && byId.nagaModelMenu.childNodes[7].classList.contains('disabled'),
  '本报告只有ニシキ ⇒ 其余 6 个模型行灰显不可点（用户 m04556 ① / m05937 ② / m09507）');
check(!byId.nagaModelMenu.childNodes[1].classList.contains('disabled'), '有数据的模型行可点');
byId.nagaModelMenu.childNodes[1].fire('click', { target: byId.nagaModelMenu.childNodes[1] });
check(App.aiModel === 0 && byId.nagaModelBtn.textContent === 'NAGA-平衡 决策'
  && byId.nagaModelMenu.classList.contains('hidden'),
  '点「NAGA-平衡 决策」后数据源切换到该模型 + 菜单收起（aiModel=' + App.aiModel + '）');
/* --- AI 决策偏好（用户 m06323 ③）：偏好跨帧保留；本帧没有决策概率表就临时「无AI决策」 --- */
App.setFrame(1);
App.setAiModel(0);
check(App.aiPref === 'ai_balance' && App.aiModel === 0
  && byId.nagaModelBtn.textContent === 'NAGA-平衡 决策',
  '选择模型会记成偏好（aiPref=' + App.aiPref + ' / aiModel=' + App.aiModel + '）');
check(App.aiFrameKeys(App.naga.rounds[0][1]).join() === 'ai_balance'
  && App.aiFrameKeys(App.naga.rounds[0][0]).length === 0,
  'aiFrameKeys：摸牌决策帧有该模型的数据 / 配牌帧没有（与后端按帧判定同口径，用户 m06323 ①）');
App.setFrame(0);
check(App.aiPref === 'ai_balance' && App.aiModel === -1
  && byId.nagaModelBtn.textContent === '无AI决策',
  '本帧没有决策概率表 ⇒ 临时显示「无AI决策」（偏好仍保留，用户 m06323 ③）');
byId.nagaModelBtn.fire('click');
check(byId.nagaModelMenu.childNodes[1].classList.contains('cur'),
  '菜单高亮的是「偏好」而不是本帧生效值（偏好行带 .cur）');
check(byId.nagaModelMenu.childNodes[1].title.indexOf('本帧没有') >= 0,
  '本帧没有数据的模型行给出提示：' + byId.nagaModelMenu.childNodes[1].title);
byId.nagaModelMenu.childNodes[0].fire('click', { target: byId.nagaModelMenu.childNodes[0] });
check(App.aiPref === '' && App.aiModel === -1, '选「无AI决策」后偏好清空（aiPref=「' + App.aiPref + '」）');
byId.nagaModelBtn.fire('click');
byId.nagaModelMenu.childNodes[1].fire('click', { target: byId.nagaModelMenu.childNodes[1] });
check(App.aiPref === 'ai_balance', '再选回「NAGA-平衡 决策」：偏好被记住（aiPref=' + App.aiPref + '）');
App.setFrame(1);
check(App.aiModel === 0 && byId.nagaModelBtn.textContent === 'NAGA-平衡 决策',
  '有数据的帧自动切回偏好模型（用户 m06323 ③）');
/* ② 静态帧（牌谱检索 / 全部浏览）里也能选 AI 决策：模型按钮在 #nagaPanel 内、不在 #controls，
   所以 lockControls() 禁用控制面板不影响它（用户 m06323 ②）。 */
var itemAi = { log_id: 'abc', round_index: 0, frame_index: 1, kind: 'draw',
  label: 'abc 東一局 0本場 1巡目 東家' };
App.items = [itemAi];
App.itemIndex = 0;
App.setFrame(1);
check(App.itemIndex === 0 && byId.nagaModelBtn.disabled !== true,
  '静态帧里「选择AI决策」按钮仍可用（用户 m06323 ②）');
byId.nagaModelBtn.fire('click');
check(!byId.nagaModelMenu.classList.contains('hidden')
  && !byId.nagaModelMenu.childNodes[1].classList.contains('disabled'),
  '静态帧里能展开模型菜单并选中本牌谱已有的模型');
byId.nagaModelMenu.childNodes[1].fire('click', { target: byId.nagaModelMenu.childNodes[1] });
check(App.aiModel === 0 && App.aiPref === 'ai_balance',
  '静态帧里选中的模型同样记成偏好（正常播放 / 静态帧共用，用户 m06323 ③）');
App.itemIndex = -1;
App.items = [];
App.itemSource = '';
App.setFrame(1);
/* 用户 m06560：第零类数据属于「这一帧的决策者」—— 帧级 dahai_pred / reach / kan 只算在 actor 头上，
   huro 只看决策者自己那一格（前端与后端 mjscore/feats.py 的 _model_has_data() 同口径）。 */
var owFr = App.naga.rounds[0][2];            /* dahai actor = 0，但 huro 的数据在 2 号家那一格 */
check(App.aiFrameHasData(owFr, 0, App.aiModelList()) === true,
  'huro 里那一名决策者有值 ⇒ 判「有」（用户 m06560）');
/* 第 64 轮（用户 m07820 ①，口径 (a)）：huro 那一格只有 PASS 概率也算「有数据」——
   后端 mjscore/feats.py 的 _model_has_data() 一直认这一格（「存在该模型的决策信息」就算有），
   前端从本节起同口径；AI 决策信息是辅助，本软件的核心是纯牌谱特征的计算入库与检索。 */
check(App.aiFrameHasData({ msg: 'dahai', actor: 0, huro: { '1': [ { '0': 9000, '4': 0 } ] } },
  0, App.aiModelList()) === true,
  'huro 那一格只有 PASS 概率、actor 也不是他 ⇒ 仍判「有」（口径 (a)，用户 m07820 ①）');
/* --- NAGA 决策概率展示（用户 m00198 ③ / m01518 ③）：当前帧 = 自家打牌决策 --- */
check(countCls(byId.board, 'up') === 3 && countCls(byId.board, 'down') === 3,
  '牌上预测柱 3 条 + 决策者手牌下方铳率条 3 条（up=' + countCls(byId.board, 'up')
  + ' / down=' + countCls(byId.board, 'down') + '）');
check(countCls(byId.board, 'tbar') === 6 && byId.board.querySelector('.p-dangers') === null,
  '两条都画在牌上（.tbar 共 ' + countCls(byId.board, 'tbar') + ' 条），第 43 轮的竖条形态已回滚（用户 m03799 ①）');
check(countCls(byId.board, 'max') === 0,
  '概率条统一配色：不再有 argmax 高亮（.max 已取消，用户 m10014）');
check(byId.nagaOptions.childNodes.length === 3,
  '打牌选项只显示 >10% + 立直特例：' + byId.nagaOptions.childNodes.length + ' 项（5% 的打 3m 已过滤，5% 的立直保留）');
check(byId.nagaOptions.childNodes[0].textContent.indexOf('立直') === 0
  && byId.nagaOptions.childNodes[0].textContent.indexOf('5.0%') >= 0,
  '立直行永远排第一 + 低于 10% 也显示（一位小数）= ' + byId.nagaOptions.childNodes[0].textContent);
check(countCls(byId.nagaOptions, 'reach') === 1, '立直行带 .reach 标记（用不同颜色与打牌选项区分）');
check(byId.nagaOptions.childNodes[1].textContent.indexOf('60.0%') >= 0
  && byId.nagaOptions.childNodes[2].textContent.indexOf('45.0%') >= 0,
  '打牌选项按概率降序 + 文本格式 = ' + byId.nagaOptions.textContent);
/* 用户 m02227 ①：naga 决策概率统一保留一位小数（38% 不能简写成 38%）。 */
check(byId.nagaOptions.textContent.indexOf('60.0%') >= 0
  && byId.nagaOptions.textContent.indexOf('45.0%') >= 0
  && byId.nagaOptions.textContent.indexOf('立直5.0%') === 0
  && byId.nagaOptions.textContent.indexOf('60%') < 0,
  '概率统一保留一位小数（60.0% / 45.0% / 立直5.0%，不出现 60%）= ' + byId.nagaOptions.textContent);
check(countCls(byId.nagaOptions, 'naga-opt-tiles') === 2, '选项里的牌用图片显示（两组牌图，立直行无牌图）');
check(byId.nagaOptions.textContent.indexOf('其它') < 0,
  '打牌选项合计 >= 100% 时不追加「其它」行（立直不计入）= ' + byId.nagaOptions.textContent);
check(byId.nagaWho.textContent === '当前决策：A', '当前决策玩家 = ' + byId.nagaWho.textContent);
check(byId.nagaHud.textContent.indexOf('流局率') >= 0 && byId.nagaHud.textContent.indexOf('横移率') >= 0
  && byId.nagaHud.textContent.indexOf('放铳率') >= 0 && byId.nagaHud.textContent.indexOf('和了率') >= 0
  && byId.nagaHud.textContent.indexOf('期待顺位') >= 0, '5 个数据（纯文本）= ' + byId.nagaHud.textContent);
check(byId.nagaHud.textContent.indexOf('10.1%') >= 0, '流局率取自报告 end_type[3][0] = 10.1%');
check(byId.nagaHud.textContent.indexOf('2.58') >= 0, '期待顺位 = Σ(i+1)·game_rank[0][i] / 10000 = 2.58 位');
/* 立直特例与「其它」残差（用户 m01903 ③）：立直永远排第一、不看 10% 门槛；
   「其它」= 1 − 打牌 / 鸣牌选项合计（立直与打牌是同一帧里两个独立的边缘量，不计入）。 */
var savedNf1 = App.naga.rounds[0][1];
var mixDp = nagaZeroM();
mixDp[0] = 3000;                       // 打 1m 30%
mixDp[1] = 2000;                       // 打 2m 20%
App.naga.rounds[0][1] = { msg: 'tsumo', actor: 0, pai: '4s', reach: 2500, dahai_pred: mixDp,
  end_type: NAGA_ET, game_rank: NAGA_GR };
App.renderNagaPanel();
check(byId.nagaOptions.childNodes.length === 4
  && byId.nagaOptions.childNodes[0].textContent.indexOf('立直') === 0
  && byId.nagaOptions.childNodes[0].textContent.indexOf('25.0%') >= 0
  && byId.nagaOptions.childNodes[3].textContent.indexOf('其它') >= 0
  && byId.nagaOptions.childNodes[3].textContent.indexOf('50.0%') >= 0,
  '立直第一 + 「其它」只算打牌选项（立直 25% / 打 30% / 打 20% / 其它 50%）= ' + byId.nagaOptions.textContent);
App.naga.rounds[0][1] = savedNf1;
App.renderNagaPanel();
check(byId.nagaOptions.childNodes.length === 3, '还原合成帧后选项表恢复 = ' + byId.nagaOptions.childNodes.length + ' 项');
clickAct('next');
check(App.frameIndex === 2, '步进到鸣牌决策帧 ' + App.frameIndex);
check(byId.nagaOptions.childNodes.length === 3 && byId.nagaOptions.textContent.indexOf('碰') >= 0
  && byId.nagaOptions.textContent.indexOf('PASS') >= 0
  && byId.nagaOptions.textContent.indexOf('其它') >= 0 && byId.nagaOptions.textContent.indexOf('5.0%') >= 0,
  '鸣牌选项（碰 75% / PASS 20% / 其它 5%）= ' + byId.nagaOptions.textContent);
check(countCls(byId.nagaOptions, 'other') === 1, '「其它」行带 .other 标记（弱化显示）');
/* 「其它」按显示值补足到 100.0%（用户 m09901）：真实例 —— 唯一过门槛的选项 9954 万分比显示成 99.5%，
   原始残差 46（0.46%）不足旧的 0.5% 阈值而被省略，表内合计只剩 99.5%；现在应补出「其它 0.5%」。 */
var savedNfOther = App.naga.rounds[0][2];
var dp9954 = nagaZeroM();
dp9954[1] = 9954;                                       // 打 2m 99.54%（显示 99.5%）
App.naga.rounds[0][2] = { msg: 'tsumo', actor: 0, pai: '4s', reach: null, dahai_pred: dp9954,
  end_type: NAGA_ET, game_rank: NAGA_GR };
App.renderNagaPanel();
check(byId.nagaOptions.childNodes.length === 2
  && byId.nagaOptions.textContent.indexOf('99.5%') >= 0
  && byId.nagaOptions.textContent.indexOf('其它') >= 0
  && byId.nagaOptions.textContent.indexOf('0.5%') >= 0
  && countCls(byId.nagaOptions, 'other') === 1,
  '显示值 99.5% ⇒ 补「其它 0.5%」，表内合计 = 100.0%（用户 m09901）= ' + byId.nagaOptions.textContent);
App.naga.rounds[0][2] = savedNfOther;
App.renderNagaPanel();

/* ④ 杠的规范名称按**牌局状态**判定（用户 m08623）：手里 4 张 = 暗杠、碰副露 + 手里第 4 张 = 加杠、
   huro 档位 5 = 大明杠。Mortal 会把加杠报成 ankan（consumed 4 张）⇒ 不能按报告档位贴标签。 */
var savedStKan = App.rounds[0][1].state;
var stKan1 = JSON.parse(JSON.stringify(savedStKan));
stKan1.players[0].melds = [{ callType: 'pon', tiles: [16, 18, 19], calledId: 19, from: 1, open: true }];
stKan1.players[0].hand = [17, 0, 4];
App.rounds[0][1].state = stKan1;
App.naga.rounds[0][1] = { msg: 'tsumo', actor: 0, pai: '4s', reach: null, dahai_pred: NAGA_DP,
  kan: { '1': 8958 }, end_type: NAGA_ET, game_rank: NAGA_GR };
App.setFrame(1);
check(byId.nagaOptions.textContent.indexOf('加杠') >= 0 && byId.nagaOptions.textContent.indexOf('暗杠') < 0
  && byId.nagaOptions.textContent.indexOf('89.6%') >= 0,
  'Mortal 把加杠报成 ankan 时按状态显示「加杠 89.6%」（用户 m08623）= ' + byId.nagaOptions.textContent);
check(countCls(byId.nagaOptions, 'naga-opt-tiles') >= 1, '加杠行画出手里那第 4 张牌');
var stKan2 = JSON.parse(JSON.stringify(savedStKan));
stKan2.players[0].melds = [];
stKan2.players[0].hand = [16, 17, 18, 19, 0, 4];
App.rounds[0][1].state = stKan2;
App.naga.rounds[0][1] = { msg: 'tsumo', actor: 0, pai: '4s', reach: null, dahai_pred: NAGA_DP,
  kan: { '1': 9000 }, end_type: NAGA_ET, game_rank: NAGA_GR };
App.setFrame(1);
check(byId.nagaOptions.textContent.indexOf('暗杠') >= 0 && byId.nagaOptions.textContent.indexOf('加杠') < 0,
  '手里 4 张 ⇒ 显示「暗杠」（用户 m08623）= ' + byId.nagaOptions.textContent);
var savedNf2Kan = App.naga.rounds[0][2];
App.naga.rounds[0][2] = { msg: 'dahai', actor: 0, pai: '1m', huro: { '2': { '0': 2000, '5': 7500 } },
  end_type: NAGA_ET, game_rank: NAGA_GR };
App.setFrame(2);
check(byId.nagaOptions.textContent.indexOf('大明杠') >= 0 && byId.nagaOptions.textContent.indexOf('碰') < 0,
  'huro 档位 5 = 「大明杠」（不再写「杠」，用户 m08623）= ' + byId.nagaOptions.textContent);
App.naga.rounds[0][2] = savedNf2Kan;
App.naga.rounds[0][1] = savedNf1;
App.rounds[0][1].state = savedStKan;
App.setFrame(2);
check(byId.nagaWho.textContent === '当前决策：C', '决策玩家切到被鸣牌的家 = ' + byId.nagaWho.textContent);
check(App.nagaKindOfName('5pr') === 13 && App.nagaKindOfName('0m') === 4 && App.nagaKindOfName('4s') === 21
  && App.nagaKindOfName('E') === 27 && App.nagaKindOfName('C') === 33 && App.nagaKindOfName('zz') === null,
  'mjai 牌名 → kind：赤 5（5pr→13 / 0m→4）、数牌、字牌、非法名');
check(App.nagaChiPair(21, 1).join(',') === '22,23' && App.nagaChiPair(21, 2).join(',') === '20,22'
  && App.nagaChiPair(21, 3).join(',') === '19,20', '吃的三种牌对下标映射（打出牌作 最小/中间/最大）');

/* 关键帧判定先于概率过滤（用户 m09110）：报告给这一帧的决策者列出的可选策略不止 PASS ⇒ 关键帧，
   必须显示 AI 分析结果；表格本身仍按 >10% 过滤，所以 0.0% 的吃 / 碰选项进不了表格。
   m09045 看到的例：上家打出 3s、我方手里有 2s3s3s4s5s ⇒ 报告给了 4s5s 吃 / 2s4s 吃 / 3s3s 碰 / PASS。 */
var savedNfHuro = App.naga.rounds[0][2];
App.naga.rounds[0][2] = { msg: 'dahai', actor: 0, pai: '3s',
  huro: { '0': { '0': 9999, '1': 0, '2': 0, '4': 0 } }, end_type: NAGA_ET, game_rank: NAGA_GR };
App.setFrame(2);
check(byId.nagaWho.textContent.indexOf('当前决策：A') >= 0 && byId.nagaOptions.textContent.indexOf('PASS') >= 0
  && byId.nagaOptions.textContent.indexOf('100.0%') >= 0,
  '可选策略不止 PASS ⇒ 关键帧，照旧显示 AI 分析结果（用户 m09110）= ' + byId.nagaWho.textContent
  + ' / ' + byId.nagaOptions.textContent);
check(byId.nagaOptions.childNodes.length === 1 && byId.nagaOptions.textContent.indexOf('碰') < 0
  && byId.nagaOptions.textContent.indexOf('吃') < 0 && countCls(byId.nagaOptions, 'other') === 0,
  '10% 门槛保留：0.0% 的吃 / 碰选项不进表格；显示值合计已到 100.0% ⇒ 不补「其它」（用户 m09110 / m09901）= '
  + byId.nagaOptions.textContent);
check(byId.nagaHud.childNodes.length === 5,
  '关键帧照旧给出 5 项 AI 分析数据（流局率 / 横移率 / 放铳率 / 和了率 / 期待顺位）= '
  + byId.nagaHud.childNodes.length);
App.naga.rounds[0][2] = { msg: 'dahai', actor: 0, pai: '3s',
  huro: { '0': { '0': 10000 } }, end_type: NAGA_ET, game_rank: NAGA_GR };
App.setFrame(2);
check(byId.nagaOptions.childNodes.length === 0 && byId.nagaWho.textContent === ''
  && byId.nagaHud.childNodes.length === 0,
  '可选策略只有 PASS ⇒ 非关键帧、整块留空（用户 m09110）= 选项 ' + byId.nagaOptions.childNodes.length
  + ' / 玩家「' + byId.nagaWho.textContent + '」');
App.naga.rounds[0][2] = savedNfHuro;
App.setFrame(2);

/* 用户 m09803：新版 NAGA（NAGA-避四 / NAGA-争一）给的是「是否立直 × 打哪张牌」的联合分布 ——
   决策表分别列「打 xx」（默听支）与「打·立直 xx」（立直支），不再单独列「立直」行；
   概率条也按两支分色：两支都有 ⇒ 左右一分为二（左紫 = 默听、右红 = 立直），
   只有默听支 ⇒ 整宽紫条（与 NAGA-平衡 相同），只有立直支 ⇒ 整宽红条。 */
(function () {
  var savedNf1c = App.naga.rounds[0][1];
  var savedAiC = App.aiModel;
  var dm = nagaZeroM(), ri = nagaZeroM();
  dm[0] = 6000; ri[0] = 3000;      /* 1m：两支都能打 ⇒ 左紫 60% + 右红 30% */
  dm[1] = 2500;                    /* 2m：只能默听打 ⇒ 整宽紫 25% */
  ri[2] = 3000;                    /* 3m：只能立直打 ⇒ 整宽红 30% */
  App.setAiModel(0);
  App.naga.rounds[0][1] = {
    msg: 'tsumo', actor: 0, pai: '4s', reach: 1000, dahai_pred: [0, 0, 0],
    dahai_split: [{ dama: dm, riichi: ri }], end_type: NAGA_ET, game_rank: NAGA_GR
  };
  App.setFrame(1);
  var ot = byId.nagaOptions.textContent;
  check(byId.nagaOptions.childNodes.length === 4 && ot.indexOf('打·立直') >= 0
    && ot.indexOf('60.0%') >= 0 && ot.indexOf('25.0%') >= 0 && ot.indexOf('30.0%') >= 0,
    '新模型决策表 = 「是否立直 × 打哪张牌」的联合分布（打 1m 60% / 打·立直 1m 30% / 打·立直 3m 30% / 打 2m 25%）= ' + ot);
  var upBars = [];
  var allUp = byId.board.querySelectorAll('.tbar.up');
  for (var ub = 0; ub < allUp.length; ub++) {
    upBars.push(allUp[ub].className.replace(/^tbar up[ ]*/, '') + ':' + allUp[ub].style.height);
  }
  upBars.sort();
  check(upBars.join(' | ') === ':25.00% | dama:60.00% | riichi solo:30.00% | riichi:30.00%',
    '分色概率条（用户 m09803）：1m 左紫 60% + 右红 30%、2m 整宽紫 25%、3m 整宽红 30% = ' + upBars.join(' | '));
  check(byId.board.querySelectorAll('.tbar.up.riichi.solo').length === 1
    && byId.board.querySelectorAll('.tbar.up.dama').length === 1,
    '两支都能打的牌画左半紫条（.dama）、只能立直打的牌画整宽红条（.solo）各 1 条');
  check(byId.nagaHud.childNodes.length === 5,
    '联合分布不影响 HUD 的 5 项 AI 分析数据 = ' + byId.nagaHud.childNodes.length);
  App.naga.rounds[0][1] = savedNf1c;
  App.setAiModel(savedAiC);
  App.setFrame(2);
})();

/* 用户 m10081：新模型的决策空间是完整的 —— 除「打 xx / 打·立直 xx」外，报告还给出自摸（hora）、
   九種九牌流局（kyushu）、暗杠 / 加杠（ankan_pai / kakan_pai，直接给出杠哪张牌，可同时多张）。
   与打牌共用 >10% 门槛（不过门槛的进「其它」）；旧模型没有这些字段 ⇒ 展示一字不变。 */
(function () {
  var savedNf1d = App.naga.rounds[0][1];
  var savedAiD = App.aiModel;
  var dmD = nagaZeroM(), riD = nagaZeroM();
  dmD[0] = 4000; riD[0] = 1000;             /* 打 1m 40.0% / 打·立直 1m 10.0%（不过门槛） */
  App.setAiModel(0);
  App.naga.rounds[0][1] = {
    msg: 'tsumo', actor: 0, pai: '4s', dahai_pred: [],
    dahai_split: [{ dama: dmD, riichi: riD }],
    hora: { '0': [3000] },                   /* 自摸 30.0% */
    ankan_pai: [{ '32': 2000 }],             /* 暗杠 発 20.0% */
    kakan_pai: [{ '28': 500 }],              /* 加杠 南 5.0% ⇒ 不过门槛、进「其它」 */
    kyushu: [0],                             /* 九種九牌 0.0% ⇒ 不显示 */
    end_type: NAGA_ET, game_rank: NAGA_GR
  };
  App.setFrame(1);
  var otD = byId.nagaOptions.textContent;
  check(byId.nagaOptions.childNodes.length === 4
    && otD.indexOf('打40.0%') >= 0 && otD.indexOf('自摸30.0%') >= 0 && otD.indexOf('暗杠20.0%') >= 0
    && otD.indexOf('其它10.0%') >= 0 && otD.indexOf('加杠') < 0 && otD.indexOf('立直') < 0,
    '完整动作空间：打 1m 40% / 自摸 30% / 暗杠 発 20% / 其它 10%（≤10% 的加杠与打·立直不单列）= ' + otD);
  var upD = [];
  var allD = byId.board.querySelectorAll('.tbar.up');
  for (var ud = 0; ud < allD.length; ud++) {
    upD.push(allD[ud].className.replace(/^tbar up[ ]*/, '') + ':' + allD[ud].style.height);
  }
  upD.sort();
  check(upD.join(' | ') === 'dama:40.00% | riichi:10.00%',
    '1m 默听 / 立直两支都有 ⇒ 左半紫条 40% + 右半红条 10%（与新的动作空间共存）= ' + upD.join(' | '));
  /* 鸣牌响应帧：荣和（hora[决策者]）要单列一行（用户 m10081：以前默认「能和就和」、缺这一项） */
  App.naga.rounds[0][1] = {
    msg: 'dahai', actor: 0, pai: '3s', huro: { '1': [{ '0': 8000, '4': 1000 }] },
    hora: { '1': [1500] }, end_type: NAGA_ET, game_rank: NAGA_GR
  };
  App.setFrame(1);
  var otR = byId.nagaOptions.textContent;
  check(byId.nagaOptions.childNodes.length === 3
    && otR.indexOf('PASS80.0%') >= 0 && otR.indexOf('荣和15.0%') >= 0 && otR.indexOf('其它5.0%') >= 0
    && otR.indexOf('碰') < 0,
    '鸣牌响应帧的完整动作空间：PASS 80% / 荣和 15% / 其它 5%（碰 10.0% 不过门槛）= ' + otR);
  App.naga.rounds[0][1] = savedNf1d;
  App.setAiModel(savedAiD);
  App.setFrame(2);
})();

/* ② 概率条按「轮到谁决策就显示谁的」（用户 m02007 ②）：本局最后一帧是家 B（座位 1）摸牌，
   打牌预测柱应当画在座位 1 的手上；自家手牌上只有自家的危险条，没有别家的预测柱。 */
clickAct('next');
check(App.frameIndex === 3, '步进到本局最后一帧 ' + App.frameIndex);
check(countCls(boardPlayer(1), 'up') === 3 && countCls(boardPlayer(1), 'down') === 3,
  '轮到别家决策时预测柱与铳率条都画在决策者手上（' + countCls(boardPlayer(1), 'up') + ' 条上柱 / '
  + countCls(boardPlayer(1), 'down') + ' 条铳率条，取座位 1 那一行）');
check(countCls(boardPlayer(0), 'up') === 0 && countCls(boardPlayer(0), 'down') === 0,
  '别家决策时主视角自己的手牌上什么都不画（up=' + countCls(boardPlayer(0), 'up')
  + ' / down=' + countCls(boardPlayer(0), 'down') + '，用户 m03710 ①）');
/* ③ 没有决策分支的展示帧：NAGA 决策栏整块清空，只留标题（用户 m02007 ③） */
var savedNf3 = App.naga.rounds[0][3];
App.naga.rounds[0][3] = { msg: 'dahai', actor: 0, pai: '3s', end_type: NAGA_ET, game_rank: NAGA_GR };
App.setFrame(3);
check(App.nagaFrameChoices(3) === false, 'nagaFrameChoices：没有 dahai_pred / huro 的帧 = 没有决策分支');
check(App.isKeyFrame(App.rounds[0], 3) === true,
  '决策帧只看牌局：没有 AI 决策概率向量的摸牌帧仍是决策帧（用户 m06670）');
check(byId.nagaOptions.childNodes.length === 0 && byId.nagaHud.childNodes.length === 0
  && byId.nagaWho.textContent === '', '展示帧的 NAGA 面板只留标题（选项 ' + byId.nagaOptions.childNodes.length
  + ' / 5 个数据 ' + byId.nagaHud.childNodes.length + ' / 玩家「' + byId.nagaWho.textContent + '」）');
App.naga.rounds[0][3] = savedNf3;
App.setFrame(3);
check(App.nagaFrameChoices(3) === true && countCls(boardPlayer(1), 'up') === 3, '还原合成帧后决策面板与预测柱恢复');
/* 第 63 轮（用户 m07289 ①②）：出牌帧算不算关键帧，只看「这张牌**可能**被他家鸣牌」，
   与牌谱里实际有没有出现鸣牌无关。这个合成样本的手牌是「每种 kind 各一张、间距 4」，
   下家（座位 1）手里有 3p / 4p ⇒ 能吃打出的 5p，所以帧 2 现在是关键帧、决策者 = 座位 1。 */
check(App.isKeyFrame(App.rounds[0], 1) === true && App.isKeyFrame(App.rounds[0], 3) === true,
  '关键帧：摸牌帧算（isKeyFrame 复核）');
check(App.isKeyFrame(App.rounds[0], 2) === true
  && MJSFEAT.responders(App.rounds[0][2].state, 0, 13).join(',') === '1'
  && App.decisionSeats(App.rounds[0], 2).join(',') === '1',
  '出牌帧按「可能被他家鸣牌」判定：下家能吃 5p ⇒ 帧 2 是关键帧、决策者 = 座位 1（用户 m07289 ①）');
/* 反过来：三家都离这张牌很远（没有同种的第 2 张、下家也没有能吃的搭子）⇒ 不是决策帧 */
var _farSt = {
  oya: 0,
  players: [{ hand: [0, 4, 8], riichi: false, riichiPending: false },
            { hand: [1, 5, 9], riichi: false, riichiPending: false },
            { hand: [18, 22, 26], riichi: false, riichiPending: false },
            { hand: [27, 31, 33], riichi: false, riichiPending: false }]
};
var _farFrames = [{ ev: { type: 'draw', player: 0, tile: 52 }, state: _farSt },
                  { ev: { type: 'discard', player: 0, tile: 52 }, state: _farSt }];
check(MJSFEAT.responders(_farSt, 0, 13).length === 0
  && App.isKeyFrame(_farFrames, 1) === false && App.decisionSeats(_farFrames, 1).length === 0,
  '没人能鸣牌的出牌帧不算关键帧（判据只与状态有关，用户 m07289 ①）');
/* 决策帧 ≠ 有 AI 决策概率向量（用户 m06670）：Mortal 报告只复盘一家，别家的决策帧上没有概率
   向量，但「上一决策 / 下一决策」仍必须停在那些帧上，否则就成了「上一自家决策」。 */
var savedNf1 = App.naga.rounds[0][1];
var savedNf3b = App.naga.rounds[0][3];
App.naga.rounds[0][1] = { msg: 'tsumo', actor: 0, pai: '4s' };
App.naga.rounds[0][3] = { msg: 'tsumo', actor: 1, pai: '8m' };
App.setFrame(1);
check(App.nagaFrameChoices(1) === false && App.nagaFrameChoices(3) === false,
  '模拟 Mortal 报告：两家的决策帧都没有 AI 决策概率向量（用户 m06670）');
check(App.isKeyFrame(App.rounds[0], 1) === true && App.isKeyFrame(App.rounds[0], 3) === true,
  '决策帧的判据不受 AI 数据影响（用户 m06670）');
clickAct('nextKey');
check(App.frameIndex === 2 && App.decisionSeats(App.rounds[0], 2).join(',') === '1',
  '「下一决策」停在别家的决策帧上（不因「没有概率向量」而跳过，落到 ' + App.frameIndex
  + '，决策者 = 座位 ' + App.decisionSeats(App.rounds[0], App.frameIndex).join(',') + '，用户 m06670）');
App.naga.rounds[0][1] = savedNf1;
App.naga.rounds[0][3] = savedNf3b;
App.setFrame(1);
/* ① 隐藏他家手牌只影响别家：主视角自己的概率条 / 决策表照旧显示（用户 m03343 ①）。
   旧实现是「隐藏时把 app.js 的 naga 段整个丢掉」，连主视角一起隐藏了（用户 m02984 ② 的错误绑定）。 */
App.setFrame(1);                    /* 帧 1 = 自家（座位 0）的摸牌决策帧 */
check(App.hideOthers === false, '① 前置：当前显示他家手牌（决策帧 1）');
clickAct('others');
check(App.hideOthers === true, '① 点「隐藏他家手牌」：已切换');
check(countCls(byId.board, 'up') === 3 && countCls(byId.board, 'down') === 3,
  '① 隐藏他家手牌后主视角自己的概率条 / 铳率条仍在（up=' + countCls(byId.board, 'up')
  + ' / down=' + countCls(byId.board, 'down') + '）');
check(byId.nagaOptions.childNodes.length === 3 && byId.nagaWho.textContent === '当前决策：A',
  '① 主视角自己的决策表仍在（选项 ' + byId.nagaOptions.childNodes.length
  + ' / 「' + byId.nagaWho.textContent + '」）');
check(byId.nagaHud.childNodes.length === 5, '① 5 个数据仍在（' + byId.nagaHud.childNodes.length + ' 项）');
App.setFrame(3);                    /* 帧 3 = 别家（座位 1）的决策帧 */
check(countCls(boardPlayer(1), 'up') === 0 && countCls(byId.board, 'down') === 0,
  '① 别家决策帧 + 隐藏他家手牌：预测柱 / 铳率条都不画（up=' + countCls(boardPlayer(1), 'up')
  + ' / down=' + countCls(byId.board, 'down') + '）');
check(byId.nagaOptions.childNodes.length === 0 && byId.nagaWho.textContent === '',
  '① 别家决策帧：决策表留空、只保留标题（选项 ' + byId.nagaOptions.childNodes.length
  + ' / 玩家「' + byId.nagaWho.textContent + '」）');
clickAct('others');
check(App.hideOthers === false, '① 再点一次：恢复显示他家手牌');
check(countCls(boardPlayer(1), 'up') === 3,
  '① 恢复后别家的决策信息回来（座位 1 的预测柱 ' + countCls(boardPlayer(1), 'up') + ' 条）');

/* --- 黄框（用户 m07820 补充 2）：静态帧的「鸣牌响应局面」标出被响应的那张牌 --- */
App.items = [{ log_id: 'abc', round_index: 0, frame_index: 2, kind: 'wait', seat: 1,
  label: 'abc 東一局 0本場 1巡目 南家' }];
App.itemIndex = 0;
App.setFrame(2);          /* 帧 2 = 座位 0 打出 5p（id 52）、下家（座位 1）可以吃 ⇒ 鸣牌响应帧 */
var mkTiles = tilesIn(byId.board);
var mkCount = countCls(byId.board, 'mark'), mkId = -1, mkWhere = '';
for (var mki = 0; mki < mkTiles.length; mki++) {
  if (mkTiles[mki]._cls.indexOf('mark') >= 0) {
    mkId = tileIdOf(mkTiles[mki]);
    var mkn = mkTiles[mki];            /* 假 DOM 的父指针叫 parent（不是 parentNode） */
    while (mkn) {
      if (mkn._cls && mkn._cls.indexOf('p-river') >= 0) { mkWhere = '牌河'; break; }
      if (mkn._cls && mkn._cls.indexOf('p-hand') >= 0) { mkWhere = '手牌'; break; }
      mkn = mkn.parent;
    }
  }
}
check(mkCount === 1 && mkId === 52 && mkWhere === '牌河',
  '静态帧「鸣牌响应局面」用黄框标出被响应的那张牌（mark ' + mkCount + ' 个 / id ' + mkId
  + ' / 位置 ' + (mkWhere || '?') + '，用户 m07820 补充 2）');
/* ③ 同一张牌有多家能鸣牌：每家一条记录、各自的主视角（用户 m08125 ③） */
App.items = [
  { log_id: 'abc', round_index: 0, frame_index: 2, kind: 'wait', seat: 1, label: 'abc 東一局 0本場 1巡目 南家' },
  { log_id: 'abc', round_index: 0, frame_index: 2, kind: 'wait', seat: 2, label: 'abc 東一局 0本場 1巡目 西家' }
];
App.itemIndex = 0;
App.setFrame(2);
var vRotA = App.viewRot.join(',');
App.itemIndex = 1;
App.setFrame(2);
var vRotB = App.viewRot.join(',');
check(vRotA === '1,2,3,0' && vRotB === '2,3,0,1' && countCls(byId.board, 'mark') === 1,
  '同一张牌有多家能鸣牌 ⇒ 每家一条记录、各自的主视角（'
  + vRotA + ' / ' + vRotB + '，用户 m08125 ③）');
App.items = [{ log_id: 'abc', round_index: 0, frame_index: 2, kind: 'draw', seat: 0,
  label: 'abc 東一局 0本場 1巡目 東家' }];
App.itemIndex = 0;
App.setFrame(2);
check(countCls(byId.board, 'mark') === 0, '静态帧但不是「鸣牌响应局面」⇒ 不画黄框（kind=draw）');
App.itemIndex = -1;
App.items = [];
App.itemSource = '';
App.setViewSeat(0);
App.setFrame(2);
check(countCls(byId.board, 'mark') === 0,
  '正常播放时不画黄框（用户 m07820 补充 2 只针对检索 / 全部浏览的静态帧）');
App.setFrame(3);          /* 复位：后面的「② 切换主视角」节从 [0,1,2,3] 起步 */

/* --- 细红框（用户 m08125 ② / m08178）：主视角本帧即将打出的牌 / 即将杠的 4 张 --- */
var svGame = App.game, svRounds = App.rounds, svRi = App.roundIndex, svFi = App.frameIndex;
App.setFrame(1);       /* 帧 1 = 座位 0（主视角）摸到 5p（id 52），下一事件 = 打出 52 */
var nxMark = App.redMarkOf(App.rounds[0][1].state);
check(nxMark && nxMark.kind === 13 && nxMark.tids.length === 0 && nxMark.melds.length === 0,
  '「下一张要打出的牌」只给 kind、由手牌挑一张（' + JSON.stringify(nxMark) + '）');
var nxT = tilesIn(byId.board).filter(function (n) { return n._cls.indexOf('next') >= 0; });
check(nxT.length === 1 && tileIdOf(nxT[0]) === 52,
  '细红框落在手牌（摸牌槽位）里的那一张上（' + nxT.length + ' 张 / id '
  + (nxT[0] ? tileIdOf(nxT[0]) : -1) + '）');
App.setFrame(3);       /* 帧 3 = 座位 1 摸牌：决策者是座位 1（不是主视角） */
var nxMark2 = App.redMarkOf(App.rounds[0][3].state);
check(nxMark2 && nxMark2.seat === 1 && nxMark2.kind === 13 && countCls(byId.board, 'next') === 1
  && countCls(byId.board.querySelector('.cell-right .p-hand'), 'next') === 1,
  '细红框跟着本帧决策者走、不再限定主视角（用户 m08319 ①：帧 3 的框画在座位 1 手里，'
  + JSON.stringify(nxMark2) + '）');
App.items = [{ log_id: 'abc', round_index: 0, frame_index: 2, kind: 'wait', seat: 1,
  label: 'abc 東一局 0本場 1巡目 南家' }];
App.itemIndex = 0;
App.setFrame(2);       /* 静态帧「鸣牌响应局面」：主视角 = 响应者，本帧没有要打的牌 */
check(App.redMarkOf(App.rounds[0][2].state) === null && countCls(byId.board, 'next') === 0,
  '鸣牌响应局面不画细红框（决策者这一帧要决定的是吃 / 碰 / 过，没有要打出的牌，用户 m08125 ②）');
App.itemIndex = -1;
App.items = [];
App.itemSource = '';
App.setViewSeat(0);
/* 立直宣言：下一事件是 reach（step 1）⇒ 细红框给的是紧跟着的那张宣言牌 */
var rEvs = [{ type: 'draw', player: 0, tile: 52 }, { type: 'reach', player: 0, step: 1 },
            { type: 'discard', player: 0, tile: 52 }];
var rSt = JSON.parse(JSON.stringify(App.rounds[0][1].state));
rSt.players[0].hand = [0, 4, 52];
rSt.players[0].melds = [];
rSt.drawn = { player: 0, tile: 52 };
App.game = { meta: { names: ['A', 'B', 'C', 'D'] }, rounds: [{ init: null, events: rEvs }] };
App.rounds = [[{ ev: null, state: rSt }, { ev: rEvs[0], state: rSt }]];
App.roundIndex = 0;
App.frameIndex = 1;    /* 下一事件 = events[1] = reach ⇒ 看 events[2] 的那张宣言牌 */
var rMark = App.redMarkOf(rSt);
check(rMark && rMark.kind === 13 && rMark.tids.length === 0,
  '立直宣言视为打出的宣言牌（kind ' + (rMark ? rMark.kind : null) + '）');
/* 加杠：手里 1 张 + 副露区那 3 张；暗杠：手里 4 张（用户 m08178） */
var kEvs = [{ type: 'draw', player: 0, tile: 17 },
            { type: 'call', player: 0, callee: 3, rel: 3, m: null, callType: 'kakan', tiles: [17] }];
var kSt = JSON.parse(JSON.stringify(rSt));
kSt.players[0].hand = [17, 0, 4];
kSt.players[0].melds = [{ callType: 'pon', tiles: [16, 18, 19], calledId: 16, from: 3, open: true }];
kSt.drawn = { player: 0, tile: 17 };
App.game = { meta: { names: ['A', 'B', 'C', 'D'] }, rounds: [{ init: null, events: kEvs }] };
App.rounds = [[{ ev: null, state: kSt }, { ev: kEvs[0], state: kSt }]];
App.frameIndex = 1;
var kMark = App.redMarkOf(kSt);
check(kMark && kMark.kind === 4 && kMark.tids.indexOf(17) >= 0 && kMark.melds.join(',') === '16,18,19',
  '加杠：手里 1 张 + 副露区 3 张（' + JSON.stringify(kMark) + '）');
global.UI.renderBoard(byId.board, kSt, { selfSeat: 0, viewRot: [0, 1, 2, 3], next: kMark });
check(countCls(byId.board, 'next') === 4
  && countCls(byId.board.querySelector('.cell-bottom .p-hand'), 'next') === 1
  && countCls(byId.board.querySelector('.cell-bottom .p-melds'), 'next') === 3,
  '加杠的 4 张牌都在细红框里（手牌 1 + 副露 3，用户 m08178）');
var aEvs = [{ type: 'draw', player: 0, tile: 19 },
            { type: 'call', player: 0, callee: null, rel: 0, m: null, callType: 'ankan',
              tiles: [16, 17, 18, 19] }];
var aSt = JSON.parse(JSON.stringify(rSt));
aSt.players[0].hand = [16, 17, 18, 19];
aSt.players[0].melds = [];
aSt.drawn = { player: 0, tile: 19 };
App.game = { meta: { names: ['A', 'B', 'C', 'D'] }, rounds: [{ init: null, events: aEvs }] };
App.rounds = [[{ ev: null, state: aSt }, { ev: aEvs[0], state: aSt }]];
App.frameIndex = 1;
var aMark = App.redMarkOf(aSt);
check(aMark && aMark.kind === 4 && aMark.melds.length === 0 && aMark.tids.length === 4,
  '暗杠：手里 4 张（' + JSON.stringify(aMark) + '）');
global.UI.renderBoard(byId.board, aSt, { selfSeat: 0, viewRot: [0, 1, 2, 3], next: aMark });
check(countCls(byId.board, 'next') === 4
  && countCls(byId.board.querySelector('.cell-bottom .p-hand'), 'next') === 4,
  '暗杠的 4 张手牌都画细红框（' + countCls(byId.board.querySelector('.cell-bottom .p-hand'), 'next') + ' 张，用户 m08178）');
check(countCls(byId.board, 'big') === 0,
  '桌面上所有牌同尺寸（手牌 / 摸牌槽位不再放大 1.15 倍，用户 m08319 ③）');
App.game = svGame;
App.rounds = svRounds;
App.roundIndex = svRi;
App.frameIndex = svFi;
App.setViewSeat(0);
App.setFrame(svFi);

/* ② 切换主视角（用户 m03343 ②）：旋转向量 + 4 行上拉框 + 立刻刷新 */
check(App.viewRot.join(',') === '0,1,2,3' && App.selfSeat === 0,
  '② 初始旋转向量 [0,1,2,3]，主视角 = 座位 0');
check(byId.board.querySelector('.cell-bottom').textContent.indexOf('A') >= 0
  && byId.board.querySelector('.cell-right').textContent.indexOf('B') >= 0
  && byId.board.querySelector('.cell-top').textContent.indexOf('C') >= 0
  && byId.board.querySelector('.cell-left').textContent.indexOf('D') >= 0,
  '② 初始座位：下 A / 右 B / 上 C / 左 D');
check(byId.viewMenu.classList.contains('hidden'), '② 上拉框默认收起');
check(byId.btnView.textContent.indexOf('切换主视角') === 0 && byId.btnView.textContent.indexOf('A') >= 0,
  '② 按钮带当前主视角玩家 ID（' + byId.btnView.textContent + '）');
clickAct('view');
check(!byId.viewMenu.classList.contains('hidden') && byId.viewMenu.childNodes.length === 4,
  '② 点「切换主视角」弹出 4 行上拉框（' + byId.viewMenu.childNodes.length + ' 行）');
check(byId.viewMenu.style.right === 'auto' && /^\d+px$/.test(byId.viewMenu.style.left || '')
  && /^\d+px$/.test(byId.viewMenu.style.bottom || ''),
  '② 上拉框贴着按钮定位（left/bottom 由 JS placeViewMenu 算出，不再固定界面右下角）：'
  + 'left=' + byId.viewMenu.style.left + ' bottom=' + byId.viewMenu.style.bottom);
var vrows = byId.viewMenu.querySelectorAll('.view-row');
check(vrows.length === 4 && vrows[0].textContent === '東家A' && vrows[1].textContent === '南家B'
  && vrows[2].textContent === '西家C' && vrows[3].textContent === '北家D',
  '② 上拉框按东 1 局座次 東 > 南 > 西 > 北 列出四家 ID：' + byId.viewMenu.textContent);
check(countCls(byId.viewMenu, 'cur') === 1 && vrows[0].className.indexOf('cur') >= 0,
  '② 当前主视角那一行带 .cur');
vrows[1].fire('click', { target: vrows[1] });
check(App.viewRot.join(',') === '1,2,3,0' && App.selfSeat === 1,
  '② 点第 2 行（南家 B）后旋转向量 = [' + App.viewRot.join(',') + ']');
check(byId.viewMenu.classList.contains('hidden'), '② 选完后上拉框自动收起');
check(byId.btnView.textContent === '切换主视角：B', '② 按钮文字跟着主视角刷新（' + byId.btnView.textContent + '）');
check(byId.board.querySelector('.cell-bottom').textContent.indexOf('B') >= 0
  && byId.board.querySelector('.cell-bottom').querySelector('.p-rot').className.indexOf('r0') >= 0,
  '② B 换到下方主视角');
check(byId.board.querySelector('.cell-right').textContent.indexOf('C') >= 0
  && byId.board.querySelector('.cell-right').querySelector('.p-rot').className.indexOf('r270') >= 0
  && byId.board.querySelector('.cell-top').textContent.indexOf('D') >= 0
  && byId.board.querySelector('.cell-left').textContent.indexOf('A') >= 0,
  '② C 转到右侧（r270）、D 在上、A 在左：其他玩家保持相对方位');
App.setFrame(1);                    /* 决策帧：A（座位 0）摸牌 */
check(countCls(byId.board.querySelector('.cell-left'), 'up') === 3,
  '② 换主视角后概率条画到 A 的新位置（左侧 ' + countCls(byId.board.querySelector('.cell-left'), 'up') + ' 条）');
check(countCls(byId.board, 'down') === 3 && countCls(byId.board.querySelector('.cell-left'), 'down') === 3,
  '② 铳率条跟着决策者的手牌走：A 的手牌换到左侧后条文也在左侧（共 '
  + countCls(byId.board, 'down') + ' 条，左侧 ' + countCls(byId.board.querySelector('.cell-left'), 'down') + ' 条）');
App.setViewSeat(0);
App.setFrame(1);
check(App.viewRot.join(',') === '0,1,2,3' && countCls(byId.board, 'down') === 3,
  '② 复位主视角后铳率条回来（down=' + countCls(byId.board, 'down') + '）');

/* ② 铳率条 + 听牌率条（用户 m03479 ②、m03627、m03710 ①②、m03799 ①）：铳率条画在「当前决策者」
   手牌每张牌的下方（该家自己视角，左→右 = 上家 K / 対面 T / 下家 S，高 = 那张牌的危险度），
   只画决策者一家；听牌率条竖着贴在这一家手牌左端外侧（红色自下而上、高度 = 听牌率）。
   tenpai_* 取「主视角那一行 + 展示槽位」。用一帧稀疏数据分别验证。 */
function zero34() { var a = [], i; for (i = 0; i < 34; i++) { a.push(0); } return a; }
function rows34(spec) {                    /* spec = {座位: [kind, 万分比]} */
  var out = [zero34(), zero34(), zero34(), zero34()], p;
  for (p in spec) { out[Number(p)][spec[p][0]] = spec[p][1]; }
  return out;
}
function handHost(cell) {                  /* 这一家的手牌容器（铳率条 / 听牌率条的宿主） */
  return byId.board.querySelector('.cell-' + cell + ' .p-hand .tiles');
}
function downCount(cell) {
  var h = handHost(cell);
  return h ? countCls(h, 'down') : 0;
}
function downBars(cell, idx) {             /* 第 idx 张手牌牌下方的条（DOM 顺序 = K, T, S） */
  var h = handHost(cell);
  if (!h) { return []; }
  var tiles = [], i;
  for (i = 0; i < h.childNodes.length; i++) {
    if (h.childNodes[i]._cls && h.childNodes[i]._cls.indexOf('tile') >= 0) { tiles.push(h.childNodes[i]); }
  }
  var t = tiles[idx];
  if (!t) { return []; }
  var out = [];
  for (i = 0; i < t.childNodes.length; i++) {
    var c = t.childNodes[i];
    if (c._cls && c._cls.indexOf('down') >= 0) { out.push(String(c.style.height || '') + '/' + c.className); }
  }
  return out;
}
var savedNf1b = App.naga.rounds[0][1];
App.naga.rounds[0][1] = {
  msg: 'tsumo', actor: 0, pai: '4s', dahai_pred: NAGA_DP,
  danger_k: rows34({ 0: [0, 8000], 1: [1, 3000] }),
  danger_t: rows34({ 0: [0, 4500] }),
  danger_s: rows34({ 0: [1, 2000], 2: [2, 6000], 3: [3, 1000] }),
  tenpai_s: [8000, 1000, 0, 0], tenpai_t: [4000, 2000, 0, 0], tenpai_k: [1500, 3000, 0, 0],
  end_type: NAGA_ET, game_rank: NAGA_GR
};
/* 座位 0 的 2m：上家危险 30%（危险值按 row[kind] 逐张查，同一方向可以落在不同牌上） */
App.naga.rounds[0][1].danger_k[0][1] = 3000;
App.setFrame(1);
check(downCount('bottom') === 4 && countCls(byId.board, 'down') === 4,
  '② 铳率条只画在当前决策者（A）手牌上，共 ' + countCls(byId.board, 'down') + ' 条（别家不画）');
check(downBars('bottom', 0).join(' | ') === '80.00%/tbar down k | 45.00%/tbar down t'
  && downBars('bottom', 1).join(' | ') === '30.00%/tbar down k | 20.00%/tbar down s',
  '② 每条铳率条画在对应那张牌的下方、取「该家自己那一行」：'
  + downBars('bottom', 0).join(' | ') + ' / ' + downBars('bottom', 1).join(' | '));
check(downBars('bottom', 2).length === 0,
  '② 只取「决策者自己那一行」：别的行的危险牌（r2/r3 的 6000 / 1000）不会画到他的手上（0 条）');
check(byId.board.querySelector('.p-dangers') === null && countCls(byId.board, 'dgr') === 0,
  '② 第 43 轮的竖条（.p-dangers / .dgr）已不再生成（用户 m03799 ①）');
check(downBars('bottom', 0)[0].indexOf('down k') > 0 && downBars('bottom', 0)[1].indexOf('down t') > 0,
  '② 每张牌下面的三条顺序 = 该家自己视角 左→右 上家 K / 対面 T / 下家 S（0 不画）');
function tpRedH(cell) {                    /* 听牌率条红段的高度（红自下而上长，用户 m03799 ①） */
  var r = byId.board.querySelector('.cell-' + cell + ' .p-tenpai .tp-red');
  return r ? String(r.style.height || '') : '(无)';
}
function tpCls(cell) {
  var b = byId.board.querySelector('.cell-' + cell + ' .p-tenpai');
  return b ? b.className : '(无)';
}
check(byId.board.querySelectorAll('.p-tenpai').length === 3
  && !byId.board.querySelector('.cell-bottom .p-tenpai'),
  '② 听牌率条只画别家三家、主视角自己没有（' + byId.board.querySelectorAll('.p-tenpai').length + ' 条）');
check(handHost('right') !== null && handHost('right').querySelector('.p-tenpai') !== null,
  '② 听牌率条挂在 .p-hand .tiles 里（竖着贴在手牌左端外侧、随面板一起旋转，用户 m03799 ①）');
check(tpRedH('right') === '80.0%' && tpCls('right').indexOf('tp-s') >= 0,
  '② 右侧（座位 1 = 下家）听牌率条红段高 = ' + tpRedH('right') + '、基色 class = ' + tpCls('right'));
check(tpRedH('top') === '40.0%' && tpCls('top').indexOf('tp-t') >= 0,
  '② 上方（座位 2 = 対面）听牌率条红段高 = ' + tpRedH('top') + '、基色 class = ' + tpCls('top'));
check(tpRedH('left') === '15.0%' && tpCls('left').indexOf('tp-k') >= 0,
  '② 左侧（座位 3 = 上家）听牌率条红段高 = ' + tpRedH('left') + '、基色 class = ' + tpCls('left'));
App.setViewSeat(1);
App.setFrame(1);                    /* setViewSeat 只改状态，重画要再走一次 render */
check(tpRedH('right') === '10.0%' && tpRedH('top') === '20.0%' && tpRedH('left') === '30.0%',
  '② 切换主视角后听牌率条跟着换行（右 ' + tpRedH('right') + ' / 上 ' + tpRedH('top')
  + ' / 左 ' + tpRedH('left') + '）');
check(downCount('left') === 4 && downCount('right') === 0 && downCount('top') === 0 && downCount('bottom') === 0,
  '② 铳率条跟着决策者的手牌换位置：A 的手牌到了左侧（左 ' + downCount('left') + ' / 右 ' + downCount('right')
  + ' / 上 ' + downCount('top') + ' / 下 ' + downCount('bottom') + '）');
clickAct('others');                    /* 决策者是别家、他的牌被盖住 ⇒ 铳率条也不画（用户 m03710 ①） */
check(App.hideOthers === true && countCls(byId.board, 'down') === 0,
  '② 隐藏他家手牌时决策者（别家）的铳率条也隐藏（全桌 ' + countCls(byId.board, 'down') + ' 条）');
clickAct('others');
App.setViewSeat(0);
App.setFrame(1);
check(countCls(byId.board, 'down') === 4, '② 复位后决策者（A）的铳率条还在（共 ' + countCls(byId.board, 'down') + ' 条）');
App.naga.rounds[0][1] = savedNf1b;
App.setFrame(1);
check(countCls(byId.board, 'down') === 3,
  '② 还原合成帧（决策者 A 的 3 条铳率条：' + countCls(byId.board, 'down') + '）');
/* ① 复制 url（用户 m03479 ①）：NAGA = 官网观看页（不还原 ricochet），按钮点了有反馈 */
check(App.paipuUrl() === 'https://naga.dmv.nico/htmls/report_viewer.html?report_id=abc&tw=0',
  '① NAGA 牌谱的复制 URL = ' + App.paipuUrl());
check(App.paipuUrl().indexOf('ricochet') < 0, '① 复制出来的是 naga 官网地址、不还原 ricochet');
/* ③ Mortal 报告（用户 m05937 ③）：复制 URL = mjai.ekyu.moe 的报告 JSON；模型菜单只放行 Mortal 那一行 */
var savedMKind = App.naga.kind, savedMModels = App.naga.models, savedMidx = App.naga.model_index;
App.naga.kind = 'mortal';
App.naga.models = [{ index: 0, raw: '4.1c', name: 'Mortal-4.1-争一', series: 'Mortal' }];
App.naga.model_index = 0;
check(App.paipuUrl() === 'https://mjai.ekyu.moe/report/abc.json',
  '③ Mortal 牌谱的复制 URL = ' + App.paipuUrl());
App.setAiModel(-1);
App.toggleAiModelMenu(true);
var mmenu = byId.nagaModelMenu;
check(mmenu.childNodes.length === 8 && mmenu.childNodes[7].textContent === 'Mortal-4.1-争一 决策'
  && !mmenu.childNodes[7].classList.contains('disabled'),
  '③ Mortal 报告（4.1c）菜单里只有「Mortal-4.1-争一 决策」可点（8 行 = 无AI决策 + 7 模型）');
check(mmenu.childNodes[1].classList.contains('disabled') && mmenu.childNodes[2].classList.contains('disabled')
  && mmenu.childNodes[3].classList.contains('disabled') && mmenu.childNodes[4].classList.contains('disabled')
  && mmenu.childNodes[5].classList.contains('disabled') && mmenu.childNodes[6].classList.contains('disabled'),
  '③ Mortal 报告里 NAGA / 其它 Mortal 模型行全部灰显（用户 m05937 ② / m09507）');
App.toggleAiModelMenu(false);
App.naga.kind = savedMKind;
if (savedMModels === undefined) { delete App.naga.models; } else { App.naga.models = savedMModels; }
App.naga.model_index = savedMidx;
App.setAiModel(0);
check(byId.btnCopyUrl.disabled === false, '① 载入 NAGA 牌谱后「复制url」按钮可用');
byId.btnCopyUrl.fire('click', { target: byId.btnCopyUrl });
check(byId.btnCopyUrl.textContent === '已复制' && byId.btnCopyUrl.classList.contains('copied'),
  '① 点「复制url」后按钮反馈 = 「' + byId.btnCopyUrl.textContent + '」');
App.setFrame(3);
/* 用户 m02546 / m02801 ③：NAGA 和了帧的结算要和天凤一致 —— 标题带「自摸」（绿色标题行），
   还有符 / 点、役名 + 番数、宝牌 / 里宝指示牌。合成的和了样本走一遍前端渲染。 */
var NAGA_AGARI = {
  meta: { names: ['A', 'B', 'C', 'D'], oya: 0, naga: true },
  rounds: [{
    init: { round: 0, combo: 0, kyotaku: 1, dices: [1, 1], dora: 0,
      scores: [25000, 25000, 25000, 25000], oya: 0, hands: NAGA_HANDS },
    events: [
      { type: 'draw', player: 0, tile: 52 },
      { type: 'agari', winner: 0, fromWho: 0, hand: NAGA_HANDS[0].concat([52]), machi: [52],
        dora: [0], ura: [52], ten: [20, 12000], yaku: [[1, 1], [0, 1], [52, 2]],
        ba: [0, 0], before: [25000, 25000, 25000, 25000], gain: [12000, -4000, -4000, -4000] }
    ]
  }],
  naga: { report_id: 'xyz', types: { '0': 'ニシキ' }, model: 'ニシキ', model_index: 0,
    rounds: [[{ msg: 'start_kyoku' }, { msg: 'tsumo', actor: 0, pai: '4s' }]] }
};
check(App.loadText(JSON.stringify(NAGA_AGARI), 'xyz.json.gz') === true, 'NAGA 和了样本能载入');
App.setFrame(2);
var resBox = byId.board.querySelector('.cell-center .c-result');
var resTitle = resBox ? resBox.querySelector('.c-result-title') : null;
var resYaku = resBox ? resBox.querySelector('.c-yaku') : null;
var resTen = resBox ? resBox.querySelector('.c-ten') : null;
check(!!resTitle && resTitle.textContent === '東家 自摸和了',
  '和了帧的结算标题带「自摸」（绿色标题行）= ' + (resTitle ? resTitle.textContent : '(无)'));
check(!!resTen && resTen.textContent === '20 符 / 12000 点',
  '和了帧显示符 / 点 = ' + (resTen ? resTen.textContent : '(无)'));
check(!!resYaku && resYaku.textContent === '立直(1) / 門前清自摸和(1) / 宝牌(2)',
  '和了帧显示役名 + 番数 = ' + (resYaku ? resYaku.textContent : '(无)'));
check(!!resBox && countCls(resBox, 'c-dora-show') === 2,
  '宝牌 / 里宝指示牌两行都显示 = ' + countCls(resBox, 'c-dora-show') + ' 行');
var badJsonOk = App.loadText('{"foo":1}', 'bad.json');
check(badJsonOk === false && byId.homeMsg.textContent.indexOf('缺少 INIT') >= 0,
  'JSON 里没有对局时给出可读提示：' + byId.homeMsg.textContent);
/* 初始主视角 = meta.viewer_seat（用户 m06323 ①）：mortal 报告只有被复盘的那一家有决策数据，
   所以它的静态帧 / 播放视图应当直接坐在那一家（NAGA / 天凤没有视角字段 ⇒ 0）。 */
var VS_GAME = {
  meta: { names: ['A', 'B', 'C', 'D'], oya: 0, naga: true, viewer_seat: 2 },
  rounds: [{
    init: { round: 0, combo: 0, kyotaku: 0, dices: [1, 1], dora: 0,
      scores: [25000, 25000, 25000, 25000], oya: 0, hands: NAGA_HANDS },
    events: [{ type: 'draw', player: 2, tile: 52 }, { type: 'discard', player: 2, tile: 52 }]
  }],
  naga: { report_id: 'vs', types: { '0': '4.1b' }, model: 'Mortal-4.1-平衡', model_index: 0,
    rounds: [[{ msg: 'start_kyoku' }, { msg: 'tsumo', actor: 2, pai: '5p', dahai_pred: NAGA_DP }]] }
};
check(App.loadText(JSON.stringify(VS_GAME), 'vs.mortal-b') === true, 'mortal 合成样本能载入（viewer_seat = 2）');
check(App.selfSeat === 2 && App.viewRot.join(',') === '2,3,0,1',
  '初始主视角 = meta.viewer_seat（用户 m06323 ①）：viewRot=[' + App.viewRot.join(',') + ']');
App.loadText(fs.readFileSync(xmlPath(f.replace(/\.xml$/, '')), 'utf8'), f);
check(App.rounds.length === 9 && App.naga === null, '切回天凤牌谱后 App.naga 清空、局数 ' + App.rounds.length);
check(byId.nagaOptions.childNodes.length === 0 && byId.nagaHud.childNodes.length === 0
  && byId.nagaWho.textContent === '', '天凤牌谱时 NAGA 面板三块留空（仅有固定框架，共有组件不错位）');
check(byId.nagaModelBtn.textContent === '无AI决策', '天凤牌谱默认「无AI决策」= ' + byId.nagaModelBtn.textContent);
byId.nagaModelBtn.fire('click');
var tfRows = byId.nagaModelMenu.childNodes, tfAllDisabled = (tfRows.length === 8);
for (var tfr = 1; tfr < tfRows.length; tfr++) { if (!tfRows[tfr].classList.contains('disabled')) { tfAllDisabled = false; } }
check(tfAllDisabled, '天凤牌谱下 7 个 AI 模型选项全灰（用户 m04556 ① / m05937 ② / m09507）');
byId.nagaModelBtn.fire('click');   /* 收起菜单，免得影响后续断言 */
check(App.paipuUrl() === 'http://tenhou.net/0/?log=' + f.replace(/\.xml$/, '') + '&tw=0',
  '① 天凤牌谱的复制 URL 用文件名特征码 = ' + App.paipuUrl());

console.log('\n=== 2b2. 5m / 5p / 5s 的概率条优先普通 5（用户 m04498） ===');
/* 同种牌只画最靠左那张（用户 m00198 ③）—— 但赤 5 的 id 是同一 kind 里最小的（赤 5 = kind * 4 + 0），
   升序排列后反而排在最左。用户 m04498 要求 5m / 5p / 5s 优先普通 5、避开赤 5（手里只有赤 5 时除外）。
   5m 的 4 张牌 = id 16(赤) / 17 / 18 / 19；5s = id 88(赤) / 89 / 90 / 91。 */
function barOnIn(root, id) {               /* root 子树里 id 这张牌上的条数 → 'up:down' */
  if (!root) { return '(无容器)'; }
  var tiles = tilesIn(root), i, j;
  for (i = 0; i < tiles.length; i++) {
    if (tileIdOf(tiles[i]) !== id) { continue; }
    var up = 0, dn = 0;
    for (j = 0; j < tiles[i].childNodes.length; j++) {
      if (tiles[i].childNodes[j]._cls && tiles[i].childNodes[j]._cls.indexOf('up') >= 0) { up++; }
      if (tiles[i].childNodes[j]._cls && tiles[i].childNodes[j]._cls.indexOf('down') >= 0) { dn++; }
    }
    return up + ':' + dn;
  }
  return '(没找到牌 ' + id + ')';
}
function barOn(cell, id) { return barOnIn(handHost(cell), id); }
function v5Frame(kind) {                   /* 只给 kind 这一种牌：打牌预测 60% + 上家危险 40% */
  var pred = zero34(); pred[kind] = 6000;
  return {
    msg: 'tsumo', actor: 0, pai: '5m', dahai_pred: pred,
    danger_k: rows34({ 0: [kind, 4000] }), danger_t: rows34({}), danger_s: rows34({}),
    tenpai_s: [0, 0, 0, 0], tenpai_t: [0, 0, 0, 0], tenpai_k: [0, 0, 0, 0],
    end_type: NAGA_ET, game_rank: NAGA_GR
  };
}
function v5Game(hand0, kind, drawTile) {
  return {
    meta: { names: ['A', 'B', 'C', 'D'], oya: 0, naga: true },
    rounds: [{
      init: { round: 0, combo: 0, kyotaku: 0, dices: [1, 1], dora: 0,
        scores: [25000, 25000, 25000, 25000], oya: 0, hands: [hand0, NAGA_HANDS[1], NAGA_HANDS[2], NAGA_HANDS[3]] },
      events: [{ type: 'draw', player: 0, tile: (drawTile === undefined ? 108 : drawTile) }]
    }],
    naga: { report_id: 'v5', types: { '0': 'ニシキ' }, model: 'ニシキ', model_index: 0,
      rounds: [[{ msg: 'start_kyoku' }, v5Frame(kind)]] }
  };
}
/* 5m：手里有赤 5m(16) 与普通 5m(17) ⇒ 条画在 17（最靠左的那张是赤 5，但要让给普通 5） */
check(App.loadText(JSON.stringify(v5Game([16, 17, 18, 0, 1, 2, 3, 5, 6, 7, 9, 10, 11], 4)), 'v5m.json.gz') === true,
  '⑤ 5m 样本能载入');
App.setAiModel(0);   /* 第 52 轮：默认「无AI决策」不画条，这里显式选平衡形 */
App.setFrame(1);
check(barOn('bottom', 17) === '1:1' && barOn('bottom', 16) === '0:0',
  '⑤ 同种 5m：条画在普通 5m(id 17) 上、赤 5m(id 16) 上没有（17=' + barOn('bottom', 17)
  + '，16=' + barOn('bottom', 16) + '）');
check(countCls(handHost('bottom'), 'up') === 1 && countCls(handHost('bottom'), 'down') === 1,
  '⑤ 同种牌仍然只画一套条（up ' + countCls(handHost('bottom'), 'up')
  + ' / down ' + countCls(handHost('bottom'), 'down') + '）');
/* 只有赤 5m ⇒ 只能画在赤 5 上（用户 m04498 的例外） */
check(App.loadText(JSON.stringify(v5Game([16, 20, 21, 22, 0, 1, 2, 3, 5, 6, 7, 9, 10], 4)), 'v5m2.json.gz') === true,
  '⑤ 只有赤 5m 的样本能载入');
App.setAiModel(0);   /* 第 52 轮：默认「无AI决策」不画条，这里显式选平衡形 */
App.setFrame(1);
check(barOn('bottom', 16) === '1:1', '⑤ 手里只有赤 5m 时条画在赤 5 上（16=' + barOn('bottom', 16) + '）');
/* 5s：同样的规则（不写死 5m） */
check(App.loadText(JSON.stringify(v5Game([88, 89, 90, 0, 1, 2, 3, 5, 6, 7, 9, 10, 11], 22)), 'v5s.json.gz') === true,
  '⑤ 5s 样本能载入');
App.setAiModel(0);   /* 第 52 轮：默认「无AI决策」不画条，这里显式选平衡形 */
App.setFrame(1);
check(barOn('bottom', 89) === '1:1' && barOn('bottom', 88) === '0:0',
  '⑤ 5s 同规则：条画在普通 5s(id 89) 上、赤 5s(id 88) 上没有（89=' + barOn('bottom', 89)
  + '，88=' + barOn('bottom', 88) + '）');
/* 摸到的牌也算「手里」：手牌只有赤 5m、摸到的是普通 5m ⇒ 优先普通 5，条画在摸到的那张上 */
check(App.loadText(JSON.stringify(v5Game([16, 20, 21, 22, 0, 1, 2, 3, 5, 6, 7, 9, 10], 4, 17)), 'v5m3.json.gz') === true,
  '⑤ 摸牌样本能载入（手牌只有赤 5m、摸到普通 5m）');
App.setAiModel(0);   /* 第 52 轮：默认「无AI决策」不画条，这里显式选平衡形 */
App.setFrame(1);
check(barOnIn(byId.board.querySelector('.cell-bottom .p-hand'), 17) === '1:1' && barOn('bottom', 16) === '0:0',
  '⑤ 摸到的普通 5m(id 17) 上画条、手牌的赤 5m(id 16) 上没有（17='
  + barOnIn(byId.board.querySelector('.cell-bottom .p-hand'), 17) + '，16=' + barOn('bottom', 16) + '）');
check(countCls(byId.board.querySelector('.cell-bottom .p-hand'), 'up') === 1,
  '⑤ 手牌 + 摸到的牌一共只画一条 up（' + countCls(byId.board.querySelector('.cell-bottom .p-hand'), 'up') + '）');

/* ============================================================ 2c. 大字（vocalization）*/
console.log('\n=== 2c. 吃 / 碰 / 杠 / 和了帧的日语大字 ===');
/* 用户 m03978 ②：仿官方 viewer 的 renderBa —— 位置 = 展示位置百分比（下 50%/76.92%、
   右 80%/49.23%、上 50%/24.62%、左 20%/49.23%），字号 1.5 倍牌高，永远水平不旋转。
   第 48 轮的左移已按用户 m04456 回滚（位置复原）；检索静态帧不画大字（用户 m04456）。 */
var VOCAL_GAME = {
  meta: { names: ['A', 'B', 'C', 'D'], oya: 0 },
  rounds: [{
    init: { round: 0, combo: 0, kyotaku: 0, dices: [1, 1], dora: 0,
      scores: [25000, 25000, 25000, 25000], oya: 0, hands: NAGA_HANDS },
    events: [
      { type: 'draw', player: 0, tile: 52 },
      { type: 'discard', player: 0, tile: 12 },
      { type: 'call', callType: 'pon', player: 1, callee: 0, tiles: [12, 13, 14] },
      { type: 'discard', player: 1, tile: 16 },
      { type: 'call', callType: 'chi', player: 2, callee: 1, tiles: [16, 26, 27] },
      { type: 'call', callType: 'ankan', player: 3, tiles: [39, 40, 41, 42] },
      { type: 'call', callType: 'nuki', player: 3, tiles: [51] },
      { type: 'agari', winner: 2, fromWho: 0, hand: NAGA_HANDS[2].concat([12]), machi: [12],
        dora: [0], ura: [52], ten: [30, 3900], yaku: [[1, 1]], ba: [0, 0],
        before: [25000, 25000, 25000, 25000], gain: [-3900, 0, 3900, 0] }
    ]
  }]
};
check(App.vocalTextOf(null) === null && App.vocalTextOf({ type: 'draw', player: 0 }) === null
  && App.vocalTextOf({ type: 'discard', player: 0, tile: 0 }) === null, '大字取值：摸牌 / 打牌帧不画');
check(App.vocalTextOf({ type: 'call', callType: 'chi' }) === 'チー'
  && App.vocalTextOf({ type: 'call', callType: 'pon' }) === 'ポン'
  && App.vocalTextOf({ type: 'call', callType: 'kakan' }) === 'カン'
  && App.vocalTextOf({ type: 'call', callType: 'daiminkan' }) === 'カン'
  && App.vocalTextOf({ type: 'call', callType: 'nuki' }) === null,
  '大字取值：吃→チー、碰→ポン、三种杠→カン、拔北→不画');
check(App.vocalTextOf({ type: 'agari', winner: 1, fromWho: 1 }) === 'ツモ'
  && App.vocalTextOf({ type: 'agari', winner: 1, fromWho: 2 }) === 'ロン',
  '大字取值：winner === fromWho → ツモ，否则 ロン');
check(App.loadText(JSON.stringify(VOCAL_GAME), 'vocal.json.gz') === true, '大字样本能载入');
function vocalElOf() { return byId.board.querySelector('.vocal'); }
function vocalAtOf() { var v = vocalElOf(); return v ? (v.style.left + '/' + v.style.top) : '(无)'; }
App.setViewSeat(0);
App.setFrame(3);
check(!!vocalElOf() && vocalElOf().textContent === 'ポン', '碰帧画「ポン」= ' + (vocalElOf() ? vocalElOf().textContent : '(无)'));
check(vocalAtOf() === '80%/49.23%', '「ポン」落在鸣牌者（座位 1）的展示位置 = 右家 80%/49.23%（左移已按用户 m04456 回滚），实得 ' + vocalAtOf());
App.setFrame(5);
check(!!vocalElOf() && vocalElOf().textContent === 'チー' && vocalAtOf() === '50%/24.62%',
  '吃帧画「チー」在上家（座位 2）= ' + (vocalElOf() ? vocalElOf().textContent : '(无)') + ' ' + vocalAtOf());
App.setFrame(6);
check(!!vocalElOf() && vocalElOf().textContent === 'カン' && vocalAtOf() === '20%/49.23%',
  '暗杠帧画「カン」在左家（座位 3）= ' + (vocalElOf() ? vocalElOf().textContent : '(无)') + ' ' + vocalAtOf());
App.setFrame(7);
check(vocalElOf() === null, '拔北帧不画大字');
App.setFrame(8);
check(!!vocalElOf() && vocalElOf().textContent === 'ロン' && vocalAtOf() === '50%/24.62%',
  '荣和帧画「ロン」在和了者（座位 2）的展示位置 = ' + (vocalElOf() ? vocalElOf().textContent : '(无)') + ' ' + vocalAtOf());
App.setFrame(2);
check(vocalElOf() === null, '打牌帧不画大字');
App.setViewSeat(1);
App.setFrame(3);
check(vocalAtOf() === '50%/76.92%', '切换主视角后「ポン」跟着旋转到展示位置 0（下方 50%/76.92%），实得 ' + vocalAtOf());
/* 用户 m04456：牌谱检索 / 全部浏览的静态帧不画大字 */
App.setViewSeat(0);
App.setFrame(3);
check(!!vocalElOf() && vocalElOf().textContent === 'ポン', '前置：正常播放的碰帧仍画大字');
App.items = [{ log_id: 'vocal', round_index: 0, frame_index: 3, kind: 'pon',
  label: 'vocal 東一局 0本場 1巡目 東家' }];
App.itemIndex = 0;
App.setFrame(3);
check(App.vocalForFrame() === null, '静态帧 vocalForFrame() 返回 null（用户 m04456）');
check(vocalElOf() === null, '静态帧的碰帧不画大字（用户 m04456）');
App.setFrame(5);
check(vocalElOf() === null, '静态帧的吃帧也不画大字（用户 m04456）');
App.setFrame(8);
check(vocalElOf() === null, '静态帧的和了帧也不画大字（用户 m04456）');
App.itemIndex = -1;
App.items = [];
App.itemSource = '';
App.setFrame(3);
check(!!vocalElOf() && vocalElOf().textContent === 'ポン', '退出静态帧后大字恢复（用户 m04456）');
App.setViewSeat(0);
check(App.loadText(fs.readFileSync(xmlPath(f.replace(/\.xml$/, '')), 'utf8'), f) === true && App.rounds.length === 9,
  '大字测试后恢复天凤牌谱（9 局）');

/* ============================================================ 3. 步进 */
console.log('\n=== 3. 下一步 / 上一步 ===');
function clickAct(act) {
  var b = document.querySelector('#controls button[data-act="' + act + '"]');
  b.fire('click', { target: b });
}
var t0 = countTiles(byId.board);
clickAct('next');
check(App.frameIndex === 1, '点「下一步」后 frameIndex = ' + App.frameIndex);
check(byId.rpFrame.textContent === '1 / ' + (App.rounds[0].length - 1) + ' 步', '步进计数 = ' + byId.rpFrame.textContent);
check(curFrame().ev.type === 'draw', '第 1 帧事件 = ' + curFrame().ev.type);
var sawDraw = false;
for (var dr = 0; dr < byId.eventListBody.childNodes.length; dr++) {
  if (String(byId.eventListBody.childNodes[dr].textContent).indexOf('摸牌') >= 0) { sawDraw = true; break; }
}
check(sawDraw, '事件列表里能看到「摸牌」事件（描述条已删除，用户 m05131 ④）');
clickAct('next');
clickAct('prev');
check(App.frameIndex === 1, '上一步回到 frameIndex = ' + App.frameIndex);
clickAct('prev');
check(App.frameIndex === 0, '再上一步到 0');
var bPrev = document.querySelector('#controls button[data-act="prev"]');
check(bPrev.disabled === false, '第 0 帧时「上一步」不再被禁用（用户 m05350）');
clickAct('prev');
check(App.frameIndex === 0 && App.roundIndex === 0, '第 0 局开局点「上一步」停在原地（无处可退）');
clickAct('last');
check(App.frameIndex === App.rounds[0].length - 1, '「本局结束」跳到末帧 = ' + App.frameIndex);
check(curFrame().state.phase !== 'playing', '末帧 phase = ' + curFrame().state.phase);
var bNext = document.querySelector('#controls button[data-act="next"]');
check(bNext.disabled === false, '末帧时「下一步」不再被禁用（结算帧再点即进下一局，用户 m05277 ③）');
clickAct('next');
check(App.roundIndex === 1 && App.frameIndex === 0, '本局结算帧点「下一步」跳到下一局开局');
clickAct('prevRound');
check(App.roundIndex === 0 && App.frameIndex === 0, '回到第 1 局第 0 帧（恢复后续步骤的状态）');
clickAct('first');
check(App.frameIndex === 0, '「开局」回到 0');

/* ============================================================ 4. 关键帧 */
console.log('\n=== 4. 关键帧跳转 ===');
/* 关键帧 = 有待玩家做决策的帧（用户 m01903 ①②、m02007 ③；第 63 轮按用户 m07289 ①②③ 改判定义）：
   摸牌后 / 吃碰后 → 等待出牌（打牌 · 立直 · 杠 · 自摸 · 九种九牌流局）；
   有人打出牌后 → 只有「这张牌**可能**被他家鸣牌」时（非立直家同种 ≥2＝能碰 / 大明杠；
   下家有能吃的搭子、且吃后手里还有不在食替禁牌里的牌）那几家才算决策帧 —— 与实际有没有出现鸣牌无关；
   自摸帧（能和就和）与暗杠 / 加杠 / 大明杠的宣言帧都不算。 */
function keyKindAt(i) {
  var fr = App.rounds[App.roundIndex][i];
  return (fr && fr.ev) ? fr.ev.type : null;
}
function keyAt(i) { return App.isKeyFrame(App.rounds[App.roundIndex], i); }
clickAct('nextKey');
check(App.frameIndex === 1 && keyKindAt(1) === 'draw',
  '「下一关键」先停在摸牌帧（等待出牌决策）= ' + App.frameIndex + '（' + keyKindAt(1) + '）');
clickAct('nextKey');
check(App.frameIndex === 3 && keyKindAt(3) === 'draw' && keyAt(2) === false,
  '第二次「下一关键」跳过「打出牌后没人能鸣牌」的展示帧 2，停在下一次摸牌帧 = ' + App.frameIndex
  + '（' + keyKindAt(App.frameIndex) + '）');
clickAct('prevKey');
check(App.frameIndex === 1, '「上一关键」回退到摸牌帧 ' + App.frameIndex);
clickAct('first');
/* 打牌后真有人鸣牌 / 荣和的帧仍然是关键帧 */
var meldKey = -1, meldNext = '';
for (var mk = 1; mk < App.rounds[0].length - 1; mk++) {
  var e2 = App.rounds[0][mk].ev, n2 = App.rounds[0][mk + 1].ev;
  if (e2 && e2.type === 'discard' && n2 && (n2.type === 'call' || n2.type === 'agari')) {
    meldKey = mk; meldNext = n2.type; break;
  }
}
check(meldKey > 0 && keyAt(meldKey) === true,
  '打牌后有人能鸣牌 / 荣和的帧仍是关键帧（帧 ' + meldKey + '，下一次事件 = ' + meldNext + '）');
/* 第 62 轮（用户 m06801 / m06832）；第 63 轮按用户 m07289 ① 改判：
   出牌帧的决策者 = 「可能鸣牌」的那几家（这个真实样本里就是实际的响应者），且该帧「等待鸣牌」= 是 */
App.setFrame(meldKey);
var meldOwner = (meldNext === 'call')
  ? App.rounds[0][meldKey + 1].ev.player : App.rounds[0][meldKey + 1].ev.winner;
check(App.frameSeatOf(App.rounds[0][meldKey].state) === meldOwner
  && App.seatOfFrame(App.rounds[0], meldKey) === meldOwner,
  '等待鸣牌帧的决策者 = 响应者（帧 ' + meldKey + ' → 座位 ' + meldOwner + '，用户 m06801）');
var _waitSt = App.rounds[0][meldKey].state;
var _exWait = (typeof MJSFEAT.extract === 'function') ? MJSFEAT.extract(_waitSt, meldOwner, 'wait') : null;
var _exDraw = (typeof MJSFEAT.extract === 'function') ? MJSFEAT.extract(_waitSt, meldOwner, 'draw') : null;
check(!!_exWait && _exWait.meld_wait === '是' && !!_exDraw && _exDraw.meld_wait === '否',
  '等待鸣牌帧「等待鸣牌」= 是 / 摸牌帧 = 否（用户 m06832）');
clickAct('first');

/* 连点「下一关键」走完一整局：落点都必须是关键帧，且不会停在立直宣言 / 新宝牌 / 和了帧上 */
var visited = 0, badLand = null, execStops = 0, discardLands = 0;
for (var z = 0; z < 400; z++) {
  var beforeKey = App.frameIndex;
  clickAct('nextKey');
  if (App.frameIndex === beforeKey) { break; }
  var kt = keyKindAt(App.frameIndex);
  if (!keyAt(App.frameIndex)) {
    if (App.frameIndex === App.rounds[0].length - 1) { break; }      // 末帧（和了 / 流局）是收尾，不算落点异常
    badLand = App.frameIndex + ':' + kt + '(非关键帧)';
    break;
  }
  if (kt === 'discard') {                                            // 落点里的出牌帧必须「可能被他家鸣牌」
    if (App.decisionSeats(App.rounds[0], App.frameIndex).length === 0) {
      badLand = App.frameIndex + ':展示帧'; break;
    }
    discardLands++;
  }
  visited++;
  if (kt === 'dora' || kt === 'agari' || kt === 'ryuukyoku') { execStops++; }
  if (App.frameIndex === App.rounds[0].length - 1) { break; }
}
check(badLand === null, '连点「下一关键」的落点都是关键帧（异常：' + badLand + '）');
check(execStops === 0 && visited > 0, '不会停在新宝牌 / 和了 / 流局帧上（立直宣言帧是决策帧、允许停；共访问了 ' + visited + ' 个关键帧）');
check(discardLands >= 1, '落点里保留了「打牌后有人能鸣牌 / 荣和」的帧（' + discardLands + ' 个）');
check(App.frameIndex === App.rounds[0].length - 1 && curFrame().state.phase !== 'playing',
  '连点「下一关键」能走到本局终局（末帧 phase=' + curFrame().state.phase + '）');

/* ============================================================ 5. 局切换 */
console.log('\n=== 5. 局切换 ===');
clickAct('nextRound');
check(App.roundIndex === 1 && App.frameIndex === 0, '「下一局」-> 第 2 局第 0 帧（roundIndex=' + App.roundIndex + '）');
check(byId.roundSelect.value === '1', '下拉框同步 = ' + byId.roundSelect.value);
check(byId.eventListBody.childNodes.length === App.rounds[1].length, '事件列表换成了第 2 局的 ' + byId.eventListBody.childNodes.length + ' 行');
clickAct('prevRound');
check(App.roundIndex === 0, '「上一局」回到第 1 局');
check(document.querySelector('#controls button[data-act="prevRound"]').disabled === true, '第 1 局时「上一局」被禁用');
byId.roundSelect.value = '8';
byId.roundSelect.fire('change', { target: byId.roundSelect });
check(App.roundIndex === 8 && App.frameIndex === 0, '下拉框选第 9 局生效（roundIndex=' + App.roundIndex + '）');
check(document.querySelector('#controls button[data-act="nextRound"]').disabled === true, '最后一局时「下一局」被禁用');
var last = byId.roundSelect.childNodes[8].textContent;
clickAct('last');
check(countTiles(byId.board) > 0, '第 9 局末帧渲染 ' + countTiles(byId.board) + ' 张牌');
console.log('       第 9 局下拉项 = "' + last + '"');
byId.roundSelect.value = '0';
byId.roundSelect.fire('change', { target: byId.roundSelect });

/* ============================================================ 6. 事件列表点击 */
console.log('\n=== 6. 事件列表点击跳帧 ===');
var rows = byId.eventListBody.childNodes;
check(rows.length > 5, '列表有 ' + rows.length + ' 行');
var target = rows[5];
target.fire('click', { target: target });
check(App.frameIndex === 5, '点第 5 行 -> frameIndex = ' + App.frameIndex);
check(byId.eventListBody.querySelector('.ev-row.cur').getAttribute('data-idx') === '5', '第 5 行被标记为当前帧');
/* 点一行里的深层子节点（模拟点到文字上） */
var deep = rows[2].childNodes[1];
deep.fire('click', { target: deep });
check(App.frameIndex === 2, '点子节点也能命中（最近 .ev-row 祖先）-> ' + App.frameIndex);

/* ============================================================ 7. 复选框 */
console.log('\n=== 7. 显示/隐藏他家手牌（按钮）===');
var bOthers = document.querySelector('#controls button[data-act="others"]');
check(!!bOthers, '控制条里有「他家手牌」按钮（id=' + (bOthers ? bOthers.id : '') + '）');
check(App.hideOthers === false, '初始状态 = 显示他家手牌');
check(bOthers.textContent === '隐藏他家手牌', '按钮文案 = "' + bOthers.textContent + '"');
clickAct('others');
check(App.hideOthers === true, '点一次：已切换为隐藏');
check(bOthers.classList.contains('on'), '隐藏时按钮高亮 (.on)');
check(bOthers.textContent === '显示他家手牌', '按钮文案变成 "' + bOthers.textContent + '"');
check(countCls(byId.board, 'back') > 0, '渲染出 ' + countCls(byId.board, 'back') + ' 张牌背');
clickAct('others');
check(App.hideOthers === false, '再点一次：恢复显示');
check(!bOthers.classList.contains('on') && bOthers.textContent === '隐藏他家手牌', '按钮恢复初始态');

console.log('\n=== 7b. 四家面板旋转（按截图）===');
var ROT = { 'cell-top': 'r180', 'cell-left': 'r90', 'cell-right': 'r270', 'cell-bottom': 'r0' };
Object.keys(ROT).forEach(function (cc) {
  var cell = byId.board.querySelector('.' + cc);
  var rot = cell ? cell.querySelector('.p-rot') : null;
  check(!!rot && rot.classList.contains(ROT[cc]),
    cc + ' 面板旋转 = ' + (rot ? rot.className : 'null') + '（期望含 ' + ROT[cc] + '）');
});
var ROT_ORDER = { 'cell-top': 'wind', 'cell-left': 'wind', 'cell-right': 'wind', 'cell-bottom': 'wind' };
Object.keys(ROT_ORDER).forEach(function (cc) {
  var rot = byId.board.querySelector('.' + cc + ' .p-rot');
  var kids = rot.childNodes.map(function (n) { return n._cls[0]; }).join(' > ');
  var bot0 = rot.querySelector('.p-bottom');
  var bkids0 = bot0 ? bot0.childNodes.map(function (n) { return n._cls[0]; }) : [];
  check(kids.indexOf('p-head') === 0 && kids.indexOf('p-river') > 0 && kids.lastIndexOf('p-bottom') > kids.indexOf('p-river'),
    cc + ' 面板内顺序（中心 -> 外侧）= ' + kids);
  check(bkids0.indexOf('p-hand') === 0, cc + ' 最外侧一行以手牌开头 = ' + bkids0.join(' > '));
});

/* m01386：摸牌槽位在每一帧都占位（非摸牌帧是 .empty），手牌行宽度不随帧变化 */
var slotBad = [];
['cell-top', 'cell-left', 'cell-right', 'cell-bottom'].forEach(function (cc) {
  var hr = byId.board.querySelector('.' + cc + ' .p-hand');
  if (!hr) { slotBad.push(cc + '(无手牌行)'); return; }
  var grps = hr.childNodes.filter(function (n) { return n._cls && n._cls.indexOf('tiles') >= 0; });
  var dr = grps.filter(function (n) { return n._cls.indexOf('drawn') >= 0; })[0];
  if (grps.length !== 2 || !dr) { slotBad.push(cc + '(tiles=' + grps.length + ')'); }
});
check(slotBad.length === 0, '四家手牌行都有固定的摸牌槽位（异常：' + (slotBad.join(' / ') || '无') + '）');

console.log('\n=== 7c. 中央区（只留 局/余/供托/宝牌）===');
var cen = byId.board.querySelector('.cell-center');
check(cen.querySelector('.c-round') !== null, '局数框 = "' + cen.querySelector('.c-round').textContent + '"');
check(cen.querySelector('.c-left') !== null, '剩余牌数 = "' + cen.querySelector('.c-left').textContent + '"');
check(cen.querySelector('.c-kyotaku') !== null, '供托行 = "' + cen.querySelector('.c-kyotaku').textContent + '"');
check(cen.querySelector('.c-dora') !== null, '宝牌指示牌行存在（' + countTiles(cen.querySelector('.c-dora')) + ' 张）');
check(cen.querySelector('.c-scores') === null, '中央不再重复显示四家点数列表');

console.log('\n=== 7d. 牌河分行（前 2 排各 6 张、第 3 排向右延伸，用户 m08576）===');
var okMid = true, rows = 0, detail0 = [];
['top', 'left', 'right', 'bottom'].forEach(function (a) {
  var rv = byId.board.querySelector('.cell-' + a + ' .p-river');
  if (!rv) { return; }
  var per = rv.querySelectorAll('.river-row').map(function (r) { return r.querySelectorAll('.tile').length; });
  rows += per.length;
  detail0.push(a + '[' + per.join(',') + ']');
  if (per.length > 3) { okMid = false; }
  if (per.slice(0, -1).some(function (v) { return v !== 6; })) { okMid = false; }
});
check(rows > 0 && okMid, '牌河分行 = 前几排各 6 张、最多 3 排（' + detail0.join(' ') + '，用户 m08576）');
/* 走到本局末帧，牌河最长：第 13 张起全部在第 3 排向右延伸，不再出现第 4 排（用户 m08576） */
clickAct('last');
var okRows = true, detail = [], maxLen = 0;
['top', 'left', 'right', 'bottom'].forEach(function (a) {
  var rv = byId.board.querySelector('.cell-' + a + ' .p-river');
  if (!rv) { return; }
  var rws = rv.querySelectorAll('.river-row');
  var n = countTiles(rv);
  maxLen = Math.max(maxLen, n);
  var per = rws.map(function (r) { return r.querySelectorAll('.tile').length; });
  detail.push(a + '=' + n + '张/' + rws.length + '排[' + per.join(',') + ']');
  if (rws.length > 3 || rws.length !== Math.min(3, Math.ceil(n / 6))) { okRows = false; }
  if (per.slice(0, -1).some(function (v) { return v !== 6; })) { okRows = false; }
  if (per.some(function (v) { return v <= 0; })) { okRows = false; }
  if (per.length === 3 && per[2] !== n - 12) { okRows = false; }
});
check(okRows && maxLen > 6, '末帧牌河分行正确（最长 ' + maxLen + ' 张，最多 3 排、第 3 排向右延伸）：' + detail.join('  '));
/* 直接测 riverEl 的分行规则（用户 m08576） */
[6, 12, 13, 18, 19, 20, 24, 30].forEach(function (n) {
  var rv = [];
  for (var i = 0; i < n; i++) { rv.push({ tile: 0, tsumogiri: false, riichi: false, called: false, win: false }); }
  var per = UI.riverEl(rv, false).querySelectorAll('.river-row')
    .map(function (r) { return r.querySelectorAll('.tile').length; });
  var want = (n <= 6) ? [n] : ((n <= 12) ? [6, n - 6] : [6, 6, n - 12]);
  check(per.join(',') === want.join(','), 'riverEl ' + n + ' 张 = ' + per.join('+') + '（期望 ' + want.join('+') + '）');
});
clickAct('first');

console.log('\n=== 7e. 事件列表（常态显示，用户 m03175 ①）===');
check(!byId.eventList.classList.contains('off') && byId.eventListBody.childNodes.length > 0,
      '事件列表没有开关、一直显示（当前 ' + byId.eventListBody.childNodes.length + ' 行）');

/* ============================================================ 8. 键盘 */
console.log('\n=== 8. 键盘操作 ===');
clickAct('first');
function key(k) {
  var ev = { key: k, target: { tagName: 'BODY' }, preventDefault: function () { this._pd = true; } };
  (documentListeners.keydown || []).forEach(function (fn) { fn(ev); });
  return ev;
}
key('ArrowRight'); key('ArrowRight');
check(App.frameIndex === 2, '→ → 到 frameIndex = ' + App.frameIndex);
key('ArrowLeft');
check(App.frameIndex === 1, '← 回到 ' + App.frameIndex);
key('End');
check(App.frameIndex === App.rounds[App.roundIndex].length - 1, 'End 到末帧');
key('Home');
check(App.frameIndex === 0, 'Home 回第 0 帧');
key('ArrowDown');
var kd = App.frameIndex;
check(kd > 0 && App.isKeyFrame(App.rounds[App.roundIndex], kd), '↓「下一关键」-> ' + kd + ' (' + App.rounds[App.roundIndex][kd].ev.type + ')');
key('ArrowUp');
check(App.frameIndex === 0, '↑ 回到 ' + App.frameIndex);
key('PageDown');
check(App.roundIndex === 1, 'PageDown 到下一局（roundIndex=' + App.roundIndex + '）');
var pd = key('ArrowRight');
check(pd._pd === true, '按下的方向键会被 preventDefault（避免页面滚动）');
key('PageUp');
check(App.roundIndex === 0, 'PageUp 回到上一局');
/* 在输入框里按键不应触发 */
clickAct('first');
var ev2 = { key: 'ArrowRight', target: { tagName: 'INPUT' }, preventDefault: function () { this._pd = true; } };
(documentListeners.keydown || []).forEach(function (fn) { fn(ev2); });
check(App.frameIndex === 0, '焦点在 INPUT 时不响应快捷键');

/* ============================================================ 9. 控制面板跳转 / 完场结算框 */
console.log('\n=== 9. 控制面板跳转 / 完场结算框（用户 m05131） ===');
check(typeof App.atGameEnd === 'function' && typeof App.stepSelfKey === 'function'
  && typeof App.showGameEnd === 'function' && typeof App.finalBoxRows === 'function',
  '新增 atGameEnd / stepSelfKey / showGameEnd / finalBoxRows（用户 m05131 ②④）');
/* 「下一自家决策」：落到等待主视角做决策的关键帧 */
App.setRound(0, 0);
clickAct('nextSelf');
check(App.frameIndex > 0 && App.isKeyFrame(App.rounds[App.roundIndex], App.frameIndex)
  && App.seatOfFrame(App.rounds[App.roundIndex], App.frameIndex) === App.selfSeat,
  '「下一自家决策」落在等待主视角决策的关键帧 ' + App.frameIndex);
var selfLand = App.frameIndex;
clickAct('prevSelf');
check(App.frameIndex <= selfLand, '「上一自家决策」往回跳（' + selfLand + ' -> ' + App.frameIndex + '）');
/* 「开局」= 整个牌谱第 0 局第 0 帧 */
clickAct('nextRound');
clickAct('allFirst');
check(App.roundIndex === 0 && App.frameIndex === 0, '「开局」回到整个牌谱第 0 局第 0 帧（用户 m05131 ④）');
check(document.querySelector('#controls button[data-act="allFirst"]').disabled === true, '第 0 局第 0 帧时「开局」禁用');
/* 「完场」= 最后一局末帧 + 直接跳出结算框 */
clickAct('allLast');
check(App.roundIndex === App.rounds.length - 1
  && App.frameIndex === App.rounds[App.roundIndex].length - 1,
  '「完场」跳到最后两局的最终帧（round=' + App.roundIndex + ' frame=' + App.frameIndex + '）');
check(App.finalShown === true && byId.board.querySelector('.final-box') !== null,
  '「完场」直接跳出完场结算框（用户 m05131 ②）');
var frows = byId.board.querySelectorAll('.fb-row');
check(frows.length === 4, '结算框 4 行（一行一个排名，实际 ' + frows.length + '）');
check(frows[0].textContent.indexOf('1位') >= 0, '第一行 = 第 1 名（' + frows[0].textContent + '）');
var frows2 = App.finalBoxRows();
check(frows2 && frows2.length === 4 && frows2[0].score >= frows2[3].score, '结算框按最终得点从高到低排名');
check(/^-?\d+$/.test(String(frows2[0].score)), '得点是纯数字（' + frows2[0].score + '）');
check(document.querySelector('#controls button[data-act="allLast"]').disabled === true, '已弹出结算框时「完场」禁用（用户 m05277 ②）');
/* 离开最终帧 → 结算框消失；最终帧点「下一步」→ 只跳出 / 保持结算框，不改变帧号 */
clickAct('prev');
check(App.finalShown === false && byId.board.querySelector('.final-box') === null, '离开最终帧后结算框消失');
clickAct('allLast');
var endFrame = App.frameIndex;
clickAct('next');
check(App.frameIndex === endFrame && App.finalShown === true,
  '最终帧点「下一步」只跳出结算框、不改变帧号（用户 m05131 ②）');
check(App.itemIndex === -1, '结算框是浮层、不是检索结果（itemIndex 仍为 -1）');

/* 用户 m05277 ②：「完场」只在已经弹出结算框时才灰；在最终帧但未弹出时仍可点 */
function btnOff(act) { return document.querySelector('#controls button[data-act="' + act + '"]').disabled; }
clickAct('prev');
clickAct('last');
check(App.finalShown === false && byId.board.querySelector('.final-box') === null && btnOff('allLast') === false,
  '在最终帧但未弹出结算框时「完场」仍可用（用户 m05277 ②）');
clickAct('allLast');
check(App.finalShown === true && byId.board.querySelector('.final-box') !== null && App.frameIndex === endFrame,
  '「完场」跳转到弹出结算框的时刻');

/* 用户 m05277 ③：本局内没有目标帧时，「下一步 / 下一决策 / 下一自家决策」不变灰，
 * 改为跳到本局结算帧；在本局结算帧再点则跳到下一局开局 */
var r0last = App.rounds[0].length - 1;
App.setRound(0, r0last - 1);
check(btnOff('next') === false && btnOff('nextKey') === false && btnOff('nextSelf') === false,
  '接近本局结算帧时三个「下一…」按钮仍然可用（用户 m05277 ③）');
clickAct('next');
check(App.frameIndex === r0last, '本局没有下一帧时「下一步」跳到本局结算帧（' + App.frameIndex + '）');
clickAct('next');
check(App.roundIndex === 1 && App.frameIndex === 0 && App.finalShown === false,
  '本局结算帧点「下一步」跳到下一局开局（用户 m05277 ③）');
App.setRound(0, r0last - 1);
clickAct('nextKey');
check(App.frameIndex === r0last, '本局没有下一决策帧时「下一决策」跳到本局结算帧');
clickAct('nextKey');
check(App.roundIndex === 1 && App.frameIndex === 0, '本局结算帧点「下一决策」跳到下一局开局');
App.setRound(0, r0last - 1);
clickAct('nextSelf');
check(App.frameIndex === r0last, '本局没有下一个自家决策时「下一自家决策」跳到本局结算帧');
clickAct('nextSelf');
check(App.roundIndex === 1 && App.frameIndex === 0, '本局结算帧点「下一自家决策」跳到下一局开局');

App.setRound(0, 0);
check(App.finalShown === false, '换局后结算框状态复位');

/* 用户 m05350：「上一步 / 上一决策 / 上一自家决策」本局内没有目标帧时不变灰，
 * 改为退回本局开局；已经在本局开局时再点则退回上一局结算（上一局末帧） */
App.setRound(0, 1);
check(btnOff('prev') === false && btnOff('prevKey') === false && btnOff('prevSelf') === false,
  '第 1 帧时三个「上一…」按钮都可用（用户 m05350）');
clickAct('prev');
check(App.frameIndex === 0, '本局第 1 帧点「上一步」退回本局开局（' + App.frameIndex + '）');
var r0last2 = App.rounds[0].length - 1;
App.setRound(1, 0);
clickAct('prev');
check(App.roundIndex === 0 && App.frameIndex === r0last2,
  '第 2 局开局点「上一步」退回上一局结算（round=' + App.roundIndex + ' frame=' + App.frameIndex + '）');
App.setRound(1, 0);
clickAct('prevKey');
check(App.roundIndex === 0 && App.frameIndex === r0last2, '第 2 局开局点「上一决策」退回上一局结算');
App.setRound(1, 0);
clickAct('prevSelf');
check(App.roundIndex === 0 && App.frameIndex === r0last2, '第 2 局开局点「上一自家决策」退回上一局结算');
App.setRound(1, App.rounds[1].length - 1);
clickAct('prevKey');
check(App.roundIndex === 1 && App.frameIndex < App.rounds[1].length - 1,
  '本局内仍有上一决策帧时照旧往回跳（' + App.frameIndex + '）');
App.setRound(0, 0);
clickAct('prev');
check(App.roundIndex === 0 && App.frameIndex === 0, '第 0 局开局点「上一步」停在原地（无处可退）');
check(btnOff('prev') === false && btnOff('prevKey') === false && btnOff('prevSelf') === false,
  '第 0 局开局时三个「上一…」按钮也不灰（用户 m05350）');

/* ============================================================ 10. 视图切换 */
console.log('\n=== 10. 视图切换 ===');
byId.btnGoSearch.fire('click', { target: byId.btnGoSearch });
check(App.view === 'search' && !byId['view-search'].classList.contains('hidden'), '进入检索视图（占位）');
byId.btnBackHome.fire('click', { target: byId.btnBackHome });
check(App.view === 'home', '返回首页');
var tabReplay = null;
tabs.forEach(function (t) { if (t.getAttribute('data-view') === 'replay') { tabReplay = t; } });
tabReplay.fire('click', { target: tabReplay });
check(App.view === 'replay', '点页签回到播放视图');
check(countTiles(byId.board) > 0, '切回后牌桌仍在（渲染 ' + countTiles(byId.board) + ' 张牌）');

/* 播放功能的入口（m04628）：首页只留介绍 + 开始播放，播放控件搬进播放视图 */
var homeHtml = html.slice(html.indexOf('id="view-home"'), html.indexOf('id="view-replay"'));
var rpHtml = html.slice(html.indexOf('id="view-replay"'), html.indexOf('id="view-analyze"'));
check(homeHtml.indexOf('btnGoReplay') >= 0 && homeHtml.indexOf('btnPickFile') < 0 && homeHtml.indexOf('dropZone') < 0,
      '首页只留「开始播放」入口，不再直接暴露选择文件 / 拖拽区');
check(rpHtml.indexOf('btnPickFile') >= 0 && rpHtml.indexOf('dropZone') >= 0 && rpHtml.indexOf('homeMsg') >= 0
      && rpHtml.indexOf('rpModeBrowse') >= 0 && rpHtml.indexOf('rpModeSearch') >= 0
      && rpHtml.indexOf('codeInput') >= 0 && rpHtml.indexOf('codeResults') >= 0,
      '打开牌谱栏 = 浏览选择 / 按特征码搜索 + 结果框 + 提示（用户 m03175 ④⑤）');
check(rpHtml.indexOf('sampleSelect') < 0 && rpHtml.indexOf('chkList') < 0 && rpHtml.indexOf('btnLoadSample') < 0,
      '示例下拉、「载入」按钮与「事件列表」勾选项都已删除（用户 m03175 ①③）');
check(rpHtml.indexOf('boardBox') >= 0 && rpHtml.indexOf('dropZone') > rpHtml.indexOf('boardBox')
      && rpHtml.indexOf('<details') < 0,
      '拖放区搬进牌桌区域、「打不开文件…」提示段已删除（用户 m03175 ⑥⑦）');
var cssTxt = fs.readFileSync(base + '/web/style.css', 'utf8');
check(homeHtml.indexOf('牌谱下载') < homeHtml.indexOf('牌谱播放')
      && homeHtml.indexOf('牌谱播放') < homeHtml.indexOf('牌谱分析')
      && homeHtml.indexOf('牌谱分析') < homeHtml.indexOf('牌谱检索'),
      '首页四张卡片顺序 = 下载 / 播放 / 分析 / 检索');
check(/\.cards\s*\{[^}]*repeat\(2,/.test(cssTxt), '首页五个入口按 2 列排布（.cards 两列网格，第五张卡跨两列）');
byId.btnGoReplay.fire('click', { target: byId.btnGoReplay });
check(App.view === 'replay' && byId.rpOpenBar.classList.contains('hidden'),
      '已载入牌谱时点「开始播放」直接回播放视图，不再叠出入口栏（用户 m04285 ①）');
byId.btnOpenPicker.fire('click', { target: byId.btnOpenPicker });
check(!byId.rpOpenBar.classList.contains('hidden'), '「打开牌谱…」展开该栏');
byId.btnOpenPicker.fire('click', { target: byId.btnOpenPicker });
check(byId.rpOpenBar.classList.contains('hidden'), '再点一次收起');

/* ============================================================ 10b. 「牌谱播放」入口状态机（用户 m04285 ①）
   牌谱检索 / 全部浏览点开的静态帧不算「牌谱播放」状态：点页签 / 首页卡片要先把牌谱卸载、
   回到「等待选择」的播放界面，不能把入口栏与旧牌桌叠成截图里那种混乱状态。 */
console.log('\n=== 10b. 「牌谱播放」入口状态机 ===');
check(typeof App.openReplayView === 'function' && typeof App.resetReplay === 'function',
      '导出 openReplayView / resetReplay（页签与首页卡片共用一条入口逻辑）');
var beforeRounds = App.rounds.length;
App.openReplayView();
check(App.view === 'replay' && App.game !== null && App.rounds.length === beforeRounds,
      '正常播放时点「牌谱播放」只切回播放视图（牌谱不卸载）');
/* 模拟「牌谱检索 → 点开一条结果 → 静态帧播放」：loadText 的 name 与条目的 log_id 一致，
   于是 openItem 直接走「当前牌谱就是这一条」的分支（不发请求）。 */
var S10B = '2026082919gm-00a9-0000-4e40cd3e';
var item10b = { log_id: S10B, round_index: 0, frame_index: 1, kind: 'draw', label: S10B + ' 東一局 0本場 1巡目 東家' };
App.loadText(fs.readFileSync(xmlPath(S10B), 'utf8'), S10B + '.xml');
App.items = [item10b];
App.openItem(0);
check(App.itemIndex === 0 && App.view === 'replay' && countTiles(byId.board) > 0, '进入静态帧（条目模式）');
check(!byId.itemInfo.classList.contains('hidden') && byId.itemInfo.textContent.indexOf('条目 1 / 1') === 0,
      '静态帧显示条目计数：' + byId.itemInfo.textContent);
byId.btnBackHome.fire('click', { target: byId.btnBackHome });
check(App.view === 'home', '先回首页（此时牌谱与条目模式都还留着）');
App.openReplayView();
check(App.game === null && App.naga === null && App.rounds.length === 0 && App.itemIndex === -1,
      '静态帧模式点「牌谱播放」卸载牌谱并退出条目模式（用户 m04285 ①）');
check(App.view === 'replay' && !byId.rpOpenBar.classList.contains('hidden'), '回到等待选择的播放界面（入口栏展开）');
check(!byId.dropZone.classList.contains('hidden'), '等待选择时显示拖放提示');
check(byId.board.childNodes.length === 0, '旧牌桌已清空（不再出现图层叠加）');
check(byId.itemInfo.classList.contains('hidden') && byId.btnPrevItem.classList.contains('hidden')
      && byId.btnNextItem.classList.contains('hidden'), '「上一条目 / 下一条目」隐藏');
check(byId.rpFile.textContent === '' && byId.fileInfo.textContent === '未载入牌谱', '工具栏特征码与文件信息复位');
check(byId.rpFrame.textContent === '' && byId.roundSelect.childNodes.length === 0, '步数 / 局下拉复位');
check(byId.eventListBody.childNodes.length === 0, '事件列表清空');
check(byId.nagaOptions.childNodes.length === 0 && byId.nagaHud.childNodes.length === 0, 'NAGA 决策面板清空');
check(byId.homeMsg.textContent.indexOf('请「浏览选择」') >= 0, '提示玩家重新选择牌谱');
check(App.items.length === 1, '检索结果条目表保留（回到检索页还能再点开）');
App.openReplayView();
check(App.view === 'replay' && byId.board.childNodes.length === 0, '重复点入口保持等待界面（幂等）');
/* 中间不回首页、直接点入口也要复位（先把牌谱载回来，与真实流程一致） */
App.loadText(fs.readFileSync(xmlPath(S10B), 'utf8'), S10B + '.xml');
App.items = [item10b];
App.openItem(0);
check(App.itemIndex === 0 && App.game !== null, '再次进入静态帧');
App.openReplayView();
check(App.game === null && App.itemIndex === -1 && App.view === 'replay'
      && !byId.rpOpenBar.classList.contains('hidden') && byId.board.childNodes.length === 0,
      '静态帧模式直接点「牌谱播放」→ 等待选择的播放界面（用户 m04285 ①）');
App.items = [];
App.itemSource = '';

/* ============================================================ 11. 全量遍历 */
console.log('\n=== 11. 全量帧遍历（所有牌谱 / 所有局 / 所有帧）===');
var totalFrames = 0, gameCount = 0, renderErrors = 0;
['2026082919gm-00a9-0000-4e40cd3e.xml', '2026082920gm-00a9-0000-5db954e6.xml',
 '2026082921gm-00a9-0000-d2e544e6.xml', '2026083020gm-00a9-0000-e9ce1efe.xml',
 '2026083021gm-00a9-0000-d0810acf.xml'].forEach(function (fn) {
  var ok2 = App.loadText(fs.readFileSync(xmlPath(fn.replace(/\.xml$/, '')), 'utf8'), fn);
  if (!ok2) { problems.push('载入失败 ' + fn); return; }
  gameCount++;
  var n = 0;
  for (var ri = 0; ri < App.rounds.length; ri++) {
    clickAct('first');
    byId.roundSelect.value = String(ri);
    byId.roundSelect.fire('change', { target: byId.roundSelect });
    for (var fi = 0; fi < App.rounds[ri].length; fi++) {
      App.frameIndex = fi;   /* 直接设下标 + 渲染，避免 5000 次 DOM 重建太慢 */
      try { global.UI.renderBoard(byId.board, App.rounds[ri][fi].state, { selfSeat: 0, hideOthers: false }); }
      catch (e) { renderErrors++; problems.push(fn + ' R' + ri + ' F' + fi + ' 渲染异常: ' + e.message); fi = 1e9; }
      n++;
    }
    totalFrames += n;
    n = 0;
  }
  console.log('       ' + fn + ': ' + App.rounds.length + ' 局全部帧渲染成功');
});
check(renderErrors === 0, '全量 ' + totalFrames + ' 帧 / ' + gameCount + ' 个牌谱渲染无异常（异常 ' + renderErrors + ' 处）');

/* ============================================================ 7f. 样式表关键规则回归 */
/* 本节点不渲染 CSS，只做「规则回归」：防止牌河方向 / 自适应缩放被改回旧写法。 */
function cssRule(text, sel) {
  var i = text.indexOf(sel + ' {');
  if (i < 0) { return ''; }
  var j = text.indexOf('}', i);
  return j < 0 ? text.slice(i) : text.slice(i, j + 1);
}
/* 断言前先剥掉注释（第 35 轮，用户 m02007 ①②）：CSS 注释不能嵌套，一旦某条规则被「忘了收尾」的
   注释吞掉，这条规则就不会生效，而按原文匹配的断言仍然「找得到」它，测不出这类事故。 */
var cssRaw = fs.readFileSync(base + '/web/style.css', 'utf8');
var cssText = cssRaw.replace(/\/\*[\s\S]*?\*\//g, '');
var boardCss = cssRule(cssText, '.board');
var riverCss = cssRule(cssText, '.p-river');
check(/var\(--tile-w\)/.test(boardCss), '牌桌轨道宽度以 --tile-w 为单位（各分辨率同一观感）');
check(boardCss.indexOf('1fr') < 0, '牌桌基础轨道不再用 1fr 拉伸（避免大屏留白）');
check(/(^|[^-])column\s*;/.test(riverCss) && !/column-reverse/.test(riverCss), '牌河第 1 排靠中央信息框（flex-direction: column）');
check(/min-height:\s*calc\(var\(--tile-h\)\s*\*\s*4/.test(riverCss), '牌河预留 4 排高度（牌最多占 3 排，第 4 排只留白，用户 m08576）');
check(/\.tile\.big\s*\{[^}]*calc\(var\(--tile-w\)/.test(cssText), '.tile.big 尺寸随牌宽缩放（非写死 px）');
check(/\.c-dora\s+\.tile\s*\{[^}]*calc\(var\(--tile-w\)/.test(cssText), '.c-dora .tile 尺寸随牌宽缩放（非写死 px）');
check(/\.board-box\s*\{/.test(cssText) && byId.boardBox != null, '#boardBox 容器存在（fitBoard 的测量基准）');
check(/\.tile\.called\s*\{[^}]*#e0503a/.test(cssText) && !/\.tile\.called\s*\{[^}]*grayscale/.test(cssText), '被鸣走的牌用红框标记（不再用灰度/透明度）');
check(/\.tile\.rot\s*\{[^}]*rotate\(-90deg\)/.test(cssText), '横放 = 从竖放位置逆时针 90°');
check(!/\.tile\.riichi/.test(cssText), '立直宣言牌不再加方框/文字（只横放）');
check(/\.p-bottom\s*\{/.test(cssText), '.p-bottom（手牌 + 右侧副露）存在');
check(/\.p-bottom\s*\{[^}]*flex-wrap:\s*nowrap/.test(cssText) && /\.p-bottom\s*>\s*\*\s*\{[^}]*flex:\s*0\s+0\s+auto/.test(cssText),
  '手牌/副露一行不被压缩换行（.p-bottom nowrap + 子项 flex:0 0 auto）');
check(/\.p-melds\s*\{[^}]*flex-wrap:\s*nowrap/.test(cssText), '副露容器 flex-wrap: nowrap（m00483 ③）');
/* m00635 ③：红框 / 绿框加粗，且宽度随 --tile-w 缩放（不再是写死的 2px） */
check(/\.tile\.called\s*\{[^}]*calc\(var\(--tile-w\)/.test(cssText), '.tile.called 红框加粗且随牌宽缩放（m00635 ③）');
check(/\.tile\.win\s*\{[^}]*calc\(var\(--tile-w\)/.test(cssText), '.tile.win 绿框加粗且随牌宽缩放（m00635 ③）');
/* 第 64 轮（用户 m07820 补充 1）：红 / 绿 / 黄框统一提到牌层之上（z-index: 1），线宽统一缩到 .14
   （不再缩太细）；黄框（用户 m07820 补充 2）尺寸与红 / 绿框一致。 */
/* cssRule() 只认「选择器 + 一个空格 + {」，这三条规则的选择器与 { 之间是多空格 ⇒ 自己取块。 */
function ruleOf(sel) {
  var m = new RegExp(sel.replace(/\./g, '\\.') + '\\s*\\{([^}]*)\\}').exec(cssText);
  return m ? m[1] : '';
}
var calledCss = ruleOf('.tile.called');
var winCss = ruleOf('.tile.win');
var markCss = ruleOf('.tile.mark');
check(/z-index:\s*1/.test(calledCss) && /z-index:\s*1/.test(winCss) && /z-index:\s*1/.test(markCss),
  '红 / 绿 / 黄框都在牌层之上（z-index: 1，用户 m07820 补充 1）');
check(/calc\(var\(--tile-w\)\s*\*\s*\.14\)/.test(calledCss) && /calc\(var\(--tile-w\)\s*\*\s*\.14\)/.test(winCss)
  && /calc\(var\(--tile-w\)\s*\*\s*\.14\)/.test(markCss),
  '三种框的外圈统一缩到 .14 倍牌宽（不再缩太细，用户 m07820 补充 1）');
check(/\.tile\.mark\s*\{[^}]*#ffd54a/.test(cssText),
  '黄框颜色 = #ffd54a（与检索结果匹配子串的高亮同色，用户 m07820 补充 2）');
check(!/\.tile\.called\s*\{[^}]*\*\.17/.test(cssText) && !/\.tile\.win\s*\{[^}]*\*\.17/.test(cssText),
  '旧的 .17 倍外圈已不再使用（用户 m07820 补充 1）');
/* 细红框（用户 m08125 ② / m08178）：内嵌一圈 .06（细于牌河红框的内圈 .08）、同样 z-index: 1 */
var nextCss = ruleOf('.tile.next');
check(/z-index:\s*1/.test(nextCss) && /inset 0 0 0 calc\(var\(--tile-w\)\s*\*\s*\.06\)/.test(nextCss)
  && /#e0503a/.test(nextCss),
  '细红框（.tile.next）：z-index 1 + 内嵌 .06 倍牌宽的红圈（' + nextCss.slice(0, 60) + '…）');
/* 用户 m08319 ③：所有牌同尺寸（手牌不再放大）；④：加杠第 4 张按官方画法同列上移一整张牌宽 */
check(!/\.p-hand\s+\.drawn\.self/.test(cssText),
  '摸牌槽位不再按 1.15 倍预留（桌面上所有牌同尺寸，用户 m08319 ③）');
var addedCss = ruleOf('.tile-stack .tile.added');
check(/left:\s*0/.test(addedCss) && /top:\s*calc\(var\(--tile-w\)\s*\*\s*-1\)/.test(addedCss),
  '加杠第 4 张与横牌同列、正上方错开一整张牌宽（官方 viewer 画法，用户 m08319 ④）：' + addedCss);
/* m01386：播放视图各区域固定尺寸 —— 防「文本/内容变长把框顶大、把牌桌挤得缩放跳动」 */
check(/grid-template-rows:\s*calc\(var\(--tile-h\)/.test(boardCss), '牌桌三行高度固定为 --tile-h 的倍数（不再 auto）');
check(/overflow:\s*hidden/.test(cssRule(cssText, '.board-box')), '#boardBox 不滚动（牌桌缩放不受滚动条影响）');
var ctrlCss = cssRule(cssText, '.controls');
check(/display:\s*grid/.test(ctrlCss) && /grid-template-columns:\s*repeat\(6,/.test(ctrlCss)
  && /grid-auto-rows:\s*25px/.test(ctrlCss) && /flex:\s*0\s+0\s+63px/.test(ctrlCss),
  '控制条 = 两行七列网格、整块仍占 63px（1.25 倍界面，用户 m09339 ①）');
check(!/\.desc-bar\s*\{/.test(cssText), '描述条样式已删除（用户 m05131 ④）');
var fboxCss = cssRule(cssText, '.final-box');
check(/position:\s*absolute/.test(fboxCss) && /rgba\(0,\s*0,\s*0,\s*\.78\)/.test(fboxCss)
  && /color:\s*#fff/.test(fboxCss) && /font-size:\s*calc\(var\(--tile-h\)/.test(fboxCss),
  '完场结算框 = 黑底半透明 + 白字大字号（用户 m05131 ②）');
check(/\.fb-row\s*\{[^}]*display:\s*flex/.test(cssText), '结算框每行 = flex 一行（排名 / ID / 得点）');
check(/min-width:\s*calc\(var\(--tile-w\)\s*\*\s*15\)/.test(fboxCss) && /max-width:\s*calc\(100% - 30px\)/.test(fboxCss),
  '结算框加宽到 15 张牌宽（容纳更长的玩家 ID，用户 m05277 ①）');
check(/padding:\s*calc\(var\(--tile-h\)\s*\*\s*\.7\)/.test(fboxCss) && /line-height:\s*2/.test(fboxCss),
  '结算框上下留白加大、行间距加大（用户 m05277 ①）');
check(/\.fb-row\s*\{[^}]*gap:\s*calc\(var\(--tile-w\)\s*\*\s*1\.4\)/.test(cssText)
  && /\.fb-id\s*\{[^}]*text-overflow:\s*ellipsis/.test(cssText),
  '结算框三列间距加大、玩家 ID 过长时框内省略（用户 m05277 ①）');
var fkCss = cssRule(cssText, '.frame-key');
check(/flex:\s*0\s+0\s+58px/.test(fkCss) && /white-space:\s*normal/.test(fkCss)
  && /word-break:\s*break-all/.test(fkCss), '特征码条固定两行 58px、完整换行不省略（用户 m01518 ①）');
check(/\.frame-key:empty\s*\{[^}]*visibility:\s*hidden/.test(cssText), '特征码条为空时只占位不可见');
check(/\.c-result\s*\{[^}]*position:\s*absolute/.test(cssText), '本局结果改成绝对定位浮层（不再撑高中央框）');
check(/\.warn-bar\s*\{[^}]*position:\s*absolute/.test(cssText), '回放警告改成绝对定位浮层（出现/消失不影响布局）');
check(/\.file-info\s*\{[^}]*text-overflow:\s*ellipsis/.test(cssText), '顶栏文件名单行省略号（防顶栏折行改变高度）');
var fpCss = cssRule(cssText, '.feat-panel');
check(/min-width:\s*0/.test(fpCss) && /overflow:\s*hidden/.test(fpCss), '特征面板 min-width:0 + overflow:hidden（长特征码不再撑宽面板）');
var fphCss = cssRule(cssText, '.feat-panel-head');
check(/flex:\s*0\s+0\s+133px/.test(fphCss) && /flex-wrap:\s*wrap/.test(fphCss)
  && /align-content:\s*flex-start/.test(fphCss), '特征面板标题行 = 标题 + 预留 5 行特征码（固定 133px）');
check(/\.feat-panel-head\s+\.muted\s*\{[^}]*white-space:\s*normal/.test(cssText)
  && /\.feat-panel-head\s+\.muted\s*\{[^}]*word-break:\s*break-all/.test(cssText), '标题行里的特征码完整换行显示（不省略，用户 m01518 ①）');
check(/\.ev-text\s*\{[^}]*text-overflow:\s*ellipsis/.test(cssText), '事件行文本省略号');
check(/\.p-hand\s+\.drawn\s*\{[^}]*min-width:\s*var\(--tile-w\)/.test(cssText)
  && /\.p-hand\s+\.drawn\s*\{[^}]*align-items:\s*flex-end/.test(cssText)
  && /\.p-hand\s+\.drawn\.empty\s*\{[^}]*visibility:\s*hidden/.test(cssText), '摸牌槽位固定占位 + 槽位里的牌按底对齐（不会再比别的手牌高出一截，用户 m02007 ①）');
/* 用户 m01518 ② / ③：牌面白圈 + NAGA 决策条 + NAGA 面板 */
check(/\.tile\s*\{[^}]*padding:\s*calc\(var\(--tile-w\)/.test(cssText), '牌面四周留一圈白底（.tile padding，牌不会变大）');
var tbarUpCss = cssRule(cssText, '.tbar.up');
check(/color:\s*var\(--fg-dim\)/.test(cssRule(cssText, '.naga-opt.other .naga-opt-word, .naga-opt.other .naga-opt-pct')),
  '「其它」行用弱化颜色显示（选择器完整，与具体选项区分）');
check(/color:\s*var\(--danger\)/.test(cssRule(cssText, '.naga-opt.reach .naga-opt-word, .naga-opt.reach .naga-opt-pct')),
  '立直行用另一种颜色显示（选择器完整，与打牌 / 鸣牌选项区分）');
check(/bottom:\s*100%/.test(tbarUpCss) && /width:\s*35%/.test(tbarUpCss) && /left:\s*32\.5%/.test(tbarUpCss),
  '打牌预测柱画在牌上方、宽 35%、left 32.5% ⇒ 水平居中（用户 m03710 ③）');
check(/background:\s*rgb\(124,\s*59,\s*230\)/.test(tbarUpCss),
  '默听条统一紫色 rgb(124, 59, 230)（= 原 argmax 色，用户 m10014）');
check(!/\.tbar\.up\.max/.test(cssText)
  && /\.tbar\.up\.dama\s*\{[^}]*background:\s*rgb\(124,\s*59,\s*230\)/.test(cssText),
  'argmax 高亮规则已删除；联合分布条的左半（默听）也用同一紫色（用户 m10014）');
check(/\.tbar\.up\.riichi\s*\{[^}]*background:\s*#e0503a/.test(cssText)
  && /\.tbar\.up\.riichi\.solo\s*\{[^}]*left:\s*32\.5%/.test(cssText),
  '立直条统一红色 #e0503a（半宽 .riichi / 整宽 .solo 两种形态，用户 m10014）');
check(!/\.tbar-layer/.test(cssText) && !/\.p-dangers/.test(cssText) && !/\.dgr/.test(cssText),
  '第 43 轮的定位层与竖条形态已整体删除（用户 m03799 ①②）');
var tbarDownCss = cssRule(cssText, '.tbar.down');
check(/top:\s*100%/.test(tbarDownCss) && /width:\s*30\.7%/.test(tbarDownCss),
  '铳率条回到牌下方（top: 100%、每条宽 30.7% 牌宽；用户 m03799 ①）');
check(/\.tbar\.down\.k\s*\{[^}]*background:\s*#2196F3/.test(cssText) && /left:\s*3\.4%/.test(cssRule(cssText, '.tbar.down.k'))
  && /\.tbar\.down\.t\s*\{[^}]*background:\s*#FFEB3B/.test(cssText) && /left:\s*34\.1%/.test(cssRule(cssText, '.tbar.down.t'))
  && /\.tbar\.down\.s\s*\{[^}]*background:\s*#4CAF50/.test(cssText) && /left:\s*64\.8%/.test(cssRule(cssText, '.tbar.down.s')),
  '三条铳率条 = 上家蓝 / 対面黄 / 下家绿，左偏移 3.4% / 34.1% / 64.8%');
check(/\.p-hand\s+\.tiles\s*\{[^}]*position:\s*relative/.test(cssText),
  '手牌容器仍是听牌率条的定位参照（position: relative）');
check(/\.naga-panel\s*\{[^}]*flex:\s*0\s+0\s+250px/.test(cssText), 'NAGA 决策面板常驻固定宽 250px（非 NAGA 牌谱留空也不错位）');
check(/\.naga-hud\s*\{[^}]*min-height:\s*88px/.test(cssText), 'NAGA 的 5 个数据区固定 min-height:88px');
check(/max-height:\s*38px/.test(cssText) && !/max-width:\s*340px/.test(cssText), '工具栏特征码不再截成 340px、改为两行完整显示');/* 用户 m02801 ③：中央结算框铺满中央列 + 安全居中（内容超高也不裁掉标题），宝牌行同排 */
check(/\.center\s*\{[^}]*width:\s*100%/.test(cssText), '中央信息框铺满中央列宽度（不再只有 ~120px 内容宽）');
check(/\.c-result\s*\{[^}]*justify-content:\s*flex-start/.test(cssText)
  && !/\.c-result\s*\{[^}]*justify-content:\s*center/.test(cssText),
  '中央结果框改成安全居中：内容超高时从顶部开始滚，结算标题不会被裁');
check(/\.c-result\s*>\s*:first-child\s*\{[^}]*margin-top:\s*auto/.test(cssText)
  && /\.c-result\s*>\s*:last-child\s*\{[^}]*margin-bottom:\s*auto/.test(cssText),
  '内容不满时靠首尾 auto 外边距居中（等价于居中的观感）');
check(/\.c-dora-show\s*\{[^}]*display:\s*flex/.test(cssText), '宝牌 / 里宝指示牌标签与牌同排（省一行高度）');
check(/\.c-result\s+\.tiles\s+\.tile\s*\{[^}]*calc\(var\(--tile-w\)\s*\*\s*\.8\)/.test(cssText),
  '结果里的指示牌缩到 80%（两行宝牌也放得下）');
/* 用户 m03175 ④⑤⑥：特征码输入框 / 结果框 / 牌桌区域的拖放区 */
check(/\.code-input\s*\{[^}]*max-width:\s*1125px/.test(cssText),
  '特征码输入框足够长（放得下 133 字符的特征码，超出时自身横向滚动）');
check(/\.code-results\s*\{[^}]*height:\s*165px[^}]*overflow:\s*auto/.test(cssText),
  '搜索结果框高度固定、结果多时纵向滚动');
check(/\.code-hit\s*\{[^}]*background:\s*#ffd54a/.test(cssText),
      '匹配子串黄色高亮的样式（.code-hit）');
check(/\.code-row\s*\{[^}]*white-space:\s*nowrap/.test(cssText),
  '搜索结果单行显示牌谱名（超长横向滚动，不换行）');
check(/\.board-box\s*\{[^}]*position:\s*relative/.test(cssText)
  && /\.board-box\s+\.drop-zone\s*\{[^}]*position:\s*absolute/.test(cssText)
  && /\.board-box\s+\.drop-zone\s*\{[^}]*pointer-events:\s*none/.test(cssText),
  '拖放区绝对定位覆盖整个牌桌区域、不吃指针事件（用户 m03175 ⑥）');
check(!/\.open-bar\s+\.drop-zone/.test(cssText), '打开牌谱栏里不再有拖放区（已搬到牌桌区域）');
/* 切换主视角（用户 m03343 ②） */
check(!/#btnView\s*\{[^}]*min-width:\s*250px/.test(cssText),
  '切换主视角按钮不再要求 250px 最小宽度（改由第 7 列 1.5 倍宽保证单行显示完整 ID，用户 m05131 ④）');
var vmCss = cssRule(cssText, '.view-menu');
check(/position:\s*absolute/.test(vmCss) && /bottom:\s*120px/.test(vmCss) && /min-width:\s*300px/.test(vmCss)
  && /width:\s*max-content/.test(vmCss), '上拉框浮在控制条上方、够宽：' + vmCss.slice(0, 60));
check(!/right:\s*18px/.test(vmCss) && /left:\s*18px/.test(vmCss),
  '上拉框 CSS 不再用 right 钉在右下角（位置交给 JS，兜底 left：' + vmCss.slice(0, 50) + '）');
check(/white-space:\s*nowrap/.test(cssRule(cssText, '.view-row')), '上拉框每行单行不换行');
check(/\.view-row\.cur\s*\{[^}]*color/.test(cssText), '当前主视角那一行用强调色');
check(/\.p-tenpai\s*\{[^}]*position:\s*absolute/.test(cssText)
  && /\.p-tenpai\s*\{[^}]*right:\s*calc\(100%\s*\+\s*var\(--tile-w\)\s*\*\s*\.8\)/.test(cssText)
  && /\.p-tenpai\s*\{[^}]*bottom:\s*calc\(var\(--tile-h\)\s*\*\s*-\.25\)/.test(cssText)
  && /\.p-tenpai\s*\{[^}]*height:\s*calc\(var\(--tile-h\)\s*\*\s*1\.5\)/.test(cssText),
  '听牌率条竖在手牌左端外侧、与手牌留 0.8 倍牌宽间隔：1.5 牌高、上下各伸出 .25 牌高（用户 m03799 ① / m03978 ① / m04160 ③）');
check(/\.p-tenpai\s*\{[^}]*width:\s*calc\(var\(--tile-w\)\s*\*\s*\.307\)/.test(cssText)
  && !/\.p-tenpai\s*\{[^}]*width:\s*calc\(var\(--tile-w\)\s*\*\s*13\)/.test(cssText)
  && !/\.p-tenpai\s*\{[^}]*margin-top/.test(cssText),
  '听牌率条宽度 = 一条铳率条的宽度（30.7% 牌宽）；旧的 13 牌宽横条 + 留白已删除');
check(/\.p-tenpai\s*\{[^}]*border:\s*2px\s+solid\s+#4CAF50/.test(cssText)
  && /\.p-tenpai\s*\{[^}]*background:\s*transparent/.test(cssText),
  '听牌率条绿基色边框 + 内部透明（用户 m03627 / m04422：听牌率 100% 时靠边框看是谁家的）');
check(/\.p-tenpai\.tp-t\s*\{[^}]*border-color:\s*#FFEB3B/.test(cssText) && !/\.p-tenpai\.tp-t\s*\{[^}]*background:/.test(cssText)
  && /\.p-tenpai\.tp-k\s*\{[^}]*border-color:\s*#2196F3/.test(cssText) && !/\.p-tenpai\.tp-k\s*\{[^}]*background:/.test(cssText),
  '听牌率条边框颜色 = 対面黄 / 上家蓝，且两者都不再有底色（用户 m04422）');
check(/\.p-tenpai\s+\.tp-red\s*\{[^}]*bottom:\s*0/.test(cssText)
  && /\.p-tenpai\s+\.tp-red\s*\{[^}]*background:\s*var\(--danger\)/.test(cssText)
  && !/\.p-tenpai\s+\.tp-red\s*\{[^}]*width/.test(cssText),
  '红段从该家自己下方（bottom: 0）往上长，高度 = 听牌率（用户 m03799 ①）');
/* 用户 m03978 ②：大字（vocalization）—— 吃 / 碰 / 杠 / 和了帧的チー / ポン / カン / ツモ / ロン */
check(/\.board\s*\{[^}]*position:\s*relative/.test(cssText), '牌桌是大字的定位基准（.board position: relative）');
var vocalCss = cssRule(cssText, '.vocal');
check(/position:\s*absolute/.test(vocalCss) && /z-index:\s*1/.test(vocalCss)
  && /transform:\s*translate\(-50%,\s*-100%\)/.test(vocalCss),
  '大字绝对定位盖在牌桌之上（z-index: 1），left/top 给「文字中线 x / 基线 y」：' + vocalCss.slice(0, 50));
check(/font-size:\s*calc\(var\(--tile-h\)\s*\*\s*1\.5\)/.test(vocalCss) && /font-weight:\s*900/.test(vocalCss)
  && /color:\s*#fff/.test(vocalCss)
  && /-webkit-text-stroke:\s*calc\(var\(--tile-h\)\s*\*\s*\.003\)\s*#000/.test(vocalCss)
  && /paint-order:\s*stroke\s+fill/.test(vocalCss)
  && /text-shadow:\s*calc\(var\(--tile-h\)\s*\*\s*\.05\)/.test(vocalCss) && !/filter:\s*drop-shadow/.test(vocalCss),
  '大字 = 1.5 倍牌高 / 900 字重 / 全实心白字 + 细黑描边 + 右下黑影（用户 m04386 改回实心）');
check(/\.c-result\s*\{[^}]*z-index:\s*2/.test(cssText),
  '和了结算框盖在大字之上（官方图层顺序：牌 → 大字 → 结算窗）');
/* 用户 m04160 ①：官方大字字体打成子集随包发布 */
check(/@font-face\s*\{[^}]*font-family:\s*"vocalization"[^}]*\}/.test(cssText)
  && /url\("\.\.\/media\/fonts\/NotoSansJP-Black\.subset\.otf"\)/.test(cssText),
  '大字字体随包发布：@font-face 「vocalization」指向 media/fonts/NotoSansJP-Black.subset.otf');
check(/"vocalization"/.test(vocalCss) && /"Noto Sans JP"/.test(vocalCss),
  '大字优先用打包的 vocalization 字体、回退系统 Noto Sans JP');
var fontPath = base + '/media/fonts/NotoSansJP-Black.subset.otf';
var fontHead = '';
try { fontHead = fs.readFileSync(fontPath).slice(0, 4).toString('latin1'); } catch (e) { fontHead = String(e.code || e.message); }
check(fontHead === 'OTTO' && fs.statSync(fontPath).size < 20000,
  '子集字体文件存在且是 OTF 子集（' + fontPath + ' -> ' + fontHead + '）');
check(fs.existsSync(base + '/media/fonts/LICENSE-NotoSansJP-OFL.txt'), '子集字体附带 SIL OFL 许可证');
/* 用户 m04160 ②：副露区不再写「吃 / 碰 / 杠」文字 */
check(!/\.meld-tag/.test(cssText), '副露区不再有「吃 / 碰 / 杠」文字标签的样式（用户 m04160 ②）');
check(/\.cell-top\s*\{[^}]*align-items:\s*flex-end/.test(cssText)
  && /\.cell-bottom\s*\{[^}]*align-items:\s*flex-start/.test(cssText),
  '四家面板向中央信息框靠拢（下贴上贴，用户 m03479 ②）');
check(/\.board\s*\{[^}]*gap:\s*calc\(var\(--tile-w\)\s*\*\s*\.25\)/.test(cssText)
  && /\.board\s*\{[^}]*grid-template-rows:[^}]*calc\(var\(--tile-h\)\s*\*\s*7\.4\)/.test(cssText),
  '牌桌更紧凑：格间距 .25 牌宽、上下两行 7.4 牌高（给听牌率条留位）');

/* ============================================================ 7g. 鸣牌 / 立直 / 和了 的展示规则 */
console.log('\n=== 7g. 鸣牌 / 立直 / 和了 的展示规则 ===');
function tilesIn(node) {
  return walk(node, []).filter(function (n) { return n._cls && n._cls.indexOf('tile') >= 0; });
}
function rotIn(node) { return tilesIn(node).filter(function (n) { return n._cls.indexOf('rot') >= 0; }); }
function tileIdOf(n) { var mm = /\(id (\d+)\)$/.exec(n.title || ''); return mm ? +mm[1] : -1; }
function firstFrameWith(pred) {
  for (var ri = 0; ri < App.rounds.length; ri++) {
    for (var fi = 0; fi < App.rounds[ri].length; fi++) {
      if (pred(App.rounds[ri][fi].state)) { return App.rounds[ri][fi]; }
    }
  }
  return null;
}
function meldHit(st, type) {
  for (var s = 0; s < 4; s++) {
    for (var j = 0; j < st.players[s].melds.length; j++) {
      if (st.players[s].melds[j].callType === type) { return { seat: s, m: st.players[s].melds[j] }; }
    }
  }
  return null;
}
function show(st, hideOthers) { global.UI.renderBoard(byId.board, st, { selfSeat: 0, hideOthers: !!hideOthers }); }
/* 当前牌谱未必四种鸣牌齐全，先切到一个都有的，保证每个分支都被验证 */
(function () {
  var dFiles = xmlNames();
  var pick = null;
  dFiles.forEach(function (fn) {
    if (pick) { return; }
    var txt = fs.readFileSync(xmlPath(fn.replace(/\.xml$/, '')), 'utf8'), g = MJLOG.parse(txt), has = {};
    g.rounds.forEach(function (r) { r.events.forEach(function (e) { if (e.type === 'call') { has[e.callType] = 1; } }); });
    if (has.chi && has.pon && has.kakan && has.ankan) { pick = { fn: fn, txt: txt }; }
  });
  if (pick && App.loadText(pick.txt, pick.fn) === true) {
    console.log('  --  7g：已切到四种鸣牌齐全的牌谱 ' + pick.fn + '（含加杠/暗杠）');
  }
})();
var SEATS = ['bottom', 'right', 'top', 'left'];
[['chi', 1], ['pon', 1], ['kakan', 2], ['ankan', 0]].forEach(function (pair) {
  var type = pair[0], want = pair[1];
  var frame = firstFrameWith(function (st) { return !!meldHit(st, type); });
  if (!frame) { console.log('  --  ' + type + '：本牌谱无样本，跳过'); return; }
  show(frame.state);
  var hit = meldHit(frame.state, type);
  var rot0 = byId.board.querySelector('.cell-' + SEATS[hit.seat] + ' .p-rot');
  var bot = rot0.querySelector('.p-bottom');
  var bkids = bot ? bot.childNodes.map(function (n) { return n._cls[0]; }) : [];
  check(bkids.indexOf('p-hand') === 0 && bkids.indexOf('p-melds') > 0,
    type + '：副露在手牌右侧（' + bkids.join(' > ') + '）');
  check(countCls(byId.board, 'meld-tag') === 0 && countCls(byId.board, 'meld') > 0,
    type + '：副露只有牌、不再渲染「吃 / 碰 / 杠」文字（用户 m04160 ②）');
  var mnode = rot0.querySelector('.meld-' + type);
  var mt = tilesIn(mnode), mr = rotIn(mnode);
  var wantTiles = { chi: 3, pon: 3, kakan: 4, ankan: 4, daiminkan: 4 }[type];
  check(mt.length === hit.m.tiles.length && mt.length === wantTiles,
    type + '：副露渲染 ' + mt.length + ' 张 = 状态 ' + hit.m.tiles.length + ' 张（期望 ' + wantTiles
    + ' 张；加杠曾只带 1 张、导致 4 张牌消失，用户 m08125 ①）');
  check(mr.length === want, type + '：横放 ' + mr.length + ' 张（期望 ' + want + ' 张）');
  if (type === 'chi') {
    var ids = mt.map(tileIdOf);
    /* 吃只可能来自上家：被吃的那张横放摆在第 1 张，另外两张按点数升序跟在后面 */
    check(ids[0] === hit.m.calledId && ids[1] < ids[2],
      'chi：第 1 张是被吃的那张、后两张升序（id ' + ids.join(',') + '，calledId=' + hit.m.calledId + '）');
    check(mr.length === 1 && tileIdOf(mr[0]) === hit.m.calledId,
      'chi：横放的那张 = 被吃的那张（横放 id ' + tileIdOf(mr[0]) + '）');
  }
});
/* 大明杠：5 个测试牌谱里 0 次、没有真实样本可渲染，只能单测「来源 -> 横放位置」映射表本身
 * （用户 m00483 指定：上家=第 1 张、対面=第 2 张、下家=第 4 张，永不横放第 3 张） */
(function () {
  var ids = [0, 1, 2, 3], seat = 0;
  function mk(type, from) { return { callType: type, from: from, tiles: ids.slice(), calledId: ids[0] }; }
  var dk = [UI.rotIndexOf(mk('daiminkan', 3), ids, seat), UI.rotIndexOf(mk('daiminkan', 2), ids, seat), UI.rotIndexOf(mk('daiminkan', 1), ids, seat)];
  check(dk.join(',') === '0,1,3',
    '大明杠横放位置映射（上家=1 / 対面=2 / 下家=4；未做真实数据验证）实测第 ' + dk.map(function (v) { return v + 1; }).join('/') + ' 张');
  var pk = [UI.rotIndexOf(mk('pon', 3), ids.slice(0, 3), seat), UI.rotIndexOf(mk('pon', 2), ids.slice(0, 3), seat), UI.rotIndexOf(mk('pon', 1), ids.slice(0, 3), seat)];
  check(pk.join(',') === '0,1,2',
    '碰横放位置映射（上家=1 / 対面=2 / 下家=3）实测第 ' + pk.map(function (v) { return v + 1; }).join('/') + ' 张');
  check(UI.rotIndexOf({ callType: 'ankan', from: null, tiles: ids, calledId: null }, ids, seat) === -1 &&
        UI.rotIndexOf({ callType: 'nuki', from: null, tiles: ids, calledId: null }, ids, seat) === -1,
    '暗杠 / 拔北 不横放（返回 -1）');
})();
/* ④ 副露排列顺序：后鸣的紧挨手牌、先鸣的在外侧（DOM 里最后一个）——
 * 用「同一家有多组副露」的帧验证 DOM 顺序 = 状态副露顺序的倒序（暗杠有背面牌、跳过） */
var multiFrame = firstFrameWith(function (st) {
  return st.players.some(function (p) { return p.melds.length >= 2; });
});
if (!multiFrame) {
  console.log('  --  多组副露：本牌谱无样本，跳过');
} else {
  show(multiFrame.state);
  var sp = null, si = -1;
  multiFrame.state.players.forEach(function (p, i) { if (sp === null && p.melds.length >= 2) { sp = p; si = i; } });
  var mn = walk(byId.board.querySelector('.cell-' + SEATS[si]), []).filter(function (n) {
    return n._cls && n._cls[0] === 'meld' && n._cls.indexOf('meld-ankan') < 0;
  });
  var wantM = sp.melds.slice().reverse().filter(function (m) { return m.callType !== 'ankan'; });
  var sigOf = function (ids) { return ids.slice().sort(function (a, b) { return a - b; }).join(','); };
  var gotSig = mn.map(function (n) { return sigOf(tilesIn(n).map(tileIdOf)); });
  var wantSig = wantM.map(function (m) { return sigOf(m.tiles); });
  check(mn.length === wantM.length, '副露块数量 = 状态副露数（' + mn.length + ' / ' + wantM.length + '，不含暗杠）');
  check(gotSig.join(' | ') === wantSig.join(' | '),
    '副露顺序：后鸣的紧挨手牌、先鸣的在外侧（DOM ' + gotSig.join(' | ') + ' / 期望 ' + wantSig.join(' | ') + '）');
}
var callFrame = firstFrameWith(function (st) {
  return st.players.some(function (p) { return p.river.some(function (r) { return r.called; }); });
});
show(callFrame.state);
var expCalled = 0;
callFrame.state.players.forEach(function (p) {
  p.melds.forEach(function (m) {
    if (m.callType === 'chi' || m.callType === 'pon' || m.callType === 'daiminkan') { expCalled++; }
  });
});
check(countCls(byId.board, 'called') === expCalled,
  '被鸣走的牌仍留在牌河并用红框标出（' + countCls(byId.board, 'called') + ' 张 = 吃/碰/大明杠 ' + expCalled + ' 次）');
var riFrame = firstFrameWith(function (st) {
  return st.players.some(function (p) { return p.river.some(function (r) { return r.riichi; }); });
});
show(riFrame.state);
var riRot = 0;
SEATS.forEach(function (a) {
  var rv = byId.board.querySelector('.cell-' + a + ' .p-river');
  if (rv) { riRot += rotIn(rv).length; }
});
check(riRot >= 1, '立直宣言牌在牌河里横放（' + riRot + ' 张 .tile.rot）');
var agFrame = firstFrameWith(function (st) { return st.phase === 'agari'; });
var evA = agFrame.ev, oyaA = agFrame.state.oya, W4 = ['東', '南', '西', '北'];
var winW = W4[(evA.winner - oyaA + 4) % 4] + '家', fromW = W4[(evA.fromWho - oyaA + 4) % 4] + '家';
var wantTitle = (evA.winner === evA.fromWho) ? (winW + ' 自摸和了') : (fromW + ' 放铳 ' + winW);
show(agFrame.state);
var gotTitle = byId.board.querySelector('.c-result-title').textContent;
check(gotTitle === wantTitle, '和了时中央显示 "' + gotTitle + '"（期望 "' + wantTitle + '"）');
/* ① ② 和了帧的展示特例（m00569）：只摊开和了者（可能有双响/三响）的手牌、其余三家（含自家）隐藏；
 * 副露任何时候都不隐藏；荣和的铳牌留在放铳者牌河的最后一张（绿框 .win）且不进和了者手牌；
 * 自摸的摸牌不插进手牌，仍照上一帧单摆在手牌末端 */
function agariSpec(frame, tag) {
  var st = frame.state, res = st.result;
  var winners = (st.reveal && st.reveal.length) ? st.reveal : [res.winner];
  var ankan = 0, hiddenTiles = 0;
  st.players.forEach(function (p, i) {
    if (winners.indexOf(i) < 0) { hiddenTiles += p.hand.length; }
    p.melds.forEach(function (m) { if (m.callType === 'ankan') { ankan++; } });
  });
  show(st, true);                                  /* 故意勾上「隐藏他家手牌」 */
  var backs = countCls(byId.board, 'back');
  check(backs === hiddenTiles + ankan * 2,
    tag + '：只摊开和了者手牌、其余三家（含自家）隐藏（牌背 ' + backs + ' = 未和牌者手牌 ' + hiddenTiles + ' + 暗杠 ' + ankan + '×2）');
  var meldBacks = 0;
  SEATS.forEach(function (a) {
    var mEl = byId.board.querySelector('.cell-' + a + ' .p-melds');
    if (mEl) { meldBacks += countCls(mEl, 'back'); }
  });
  check(meldBacks === ankan * 2, tag + '：副露任何时候都不隐藏（副露区牌背 ' + meldBacks + ' = 暗杠 ' + ankan + '×2）');
  var wcell = byId.board.querySelector('.cell-' + SEATS[res.winner]);
  var handRow = wcell.querySelector('.p-hand'), handGrp = null, drawnGrp = null;
  handRow.childNodes.forEach(function (n) {
    if (n._cls && n._cls.indexOf('tiles') >= 0) {
      if (n._cls.indexOf('drawn') >= 0) { drawnGrp = n; } else if (!handGrp) { handGrp = n; }
    }
  });
  var handIds = tilesIn(handGrp).map(tileIdOf);
  check(handIds.indexOf(res.winTile) < 0, tag + '：和了牌没有出现在和了者手牌里（手牌 ' + handIds.length + ' 张）');
  if (res.winner === res.fromWho) {
    var dId = drawnGrp ? tilesIn(drawnGrp).map(tileIdOf)[0] : -1;
    check(dId === res.winTile, tag + '：自摸牌单摆在手牌末端、没有插进手牌（摸牌 id ' + dId + ' / 和了牌 ' + res.winTile + '）');
    check(handIds.length === st.players[res.winner].hand.length - 1,
      tag + '：自摸帧手牌张数 = 上一帧（' + handIds.length + ' 张）');
  } else {
    check(handIds.length === st.players[res.winner].hand.length,
      tag + '：荣和帧手牌张数 = 上一帧（' + handIds.length + ' 张）');
    var rv = byId.board.querySelector('.cell-' + SEATS[res.fromWho] + ' .p-river');
    var wt = tilesIn(rv).filter(function (n) { return n._cls.indexOf('win') >= 0; });
    check(wt.length === 1 && tileIdOf(wt[0]) === res.winTile,
      tag + '：铳牌留在放铳者牌河最后一张并加绿框（' + wt.map(tileIdOf).join(',') + ' / 和了牌 ' + res.winTile + '）');
  }
  var resTxt = byId.board.querySelector('.c-result').textContent;
  check(resTxt.indexOf('ドラ') < 0 && resTxt.indexOf('裏ドラ') < 0, tag + '：中央结果栏不再出现「ドラ / 裏ドラ」字样');
  if (res.dora && res.dora.length) { check(resTxt.indexOf('宝牌指示牌') >= 0, tag + '：宝牌指示牌（不写「ドラ」）'); }
  if (res.ura && res.ura.length) { check(resTxt.indexOf('里宝指示牌') >= 0, tag + '：里宝指示牌（不写「裏ドラ」）'); }
  var uraHan = null;
  (res.yaku || []).forEach(function (y) { if (y && y.length && y[0] === 53) { uraHan = y[1] || 0; } });
  if (uraHan === 0) { check(resTxt.indexOf('里宝牌') < 0, tag + '：里宝牌 0 番（没中里宝）时不显示该条目（m01212）'); }
  else if (uraHan > 0) { check(resTxt.indexOf('里宝牌') >= 0, tag + '：里宝牌 ' + uraHan + ' 番时仍显示（m01212）'); }
}
var ronFrame = firstFrameWith(function (st) { return st.phase === 'agari' && st.result && st.result.winner !== st.result.fromWho; });
var tsumoFrame = firstFrameWith(function (st) { return st.phase === 'agari' && st.result && st.result.winner === st.result.fromWho; });
if (ronFrame) { agariSpec(ronFrame, '和了帧（荣和）'); } else { console.log('  --  和了帧（荣和）：本牌谱无样本，跳过'); }
if (tsumoFrame) { agariSpec(tsumoFrame, '和了帧（自摸）'); } else { console.log('  --  和了帧（自摸）：本牌谱无样本，跳过'); }
/* ---------------- 7g.2 和了番种里的「里宝牌」：0 番（没中里宝）时不显示（m01212） ---------------- */
(function () {
  var zeroSt = null, someSt = null;
  for (var ri = 0; ri < App.rounds.length; ri++) {
    for (var fi = 0; fi < App.rounds[ri].length; fi++) {
      var st = App.rounds[ri][fi].state, res = st && st.result;
      if (!st || st.phase !== 'agari' || !res || !res.yaku) { continue; }
      var u = null;
      res.yaku.forEach(function (y) { if (y && y.length && y[0] === 53) { u = y[1] || 0; } });
      if (u === 0 && !zeroSt) { zeroSt = st; }
      if (u > 0 && !someSt) { someSt = st; }
    }
  }
  if (zeroSt) {
    show(zeroSt);
    var t0 = byId.board.querySelector('.c-result').textContent;
    check(t0.indexOf('里宝牌') < 0, '里宝牌 0 番：和了番种里不显示「里宝牌」（实际 "' + t0 + '"）');
  } else { console.log('  --  里宝牌 0 番：本牌谱无样本，跳过'); }
  if (someSt) {
    show(someSt);
    var t1 = byId.board.querySelector('.c-result').textContent;
    check(t1.indexOf('里宝牌') >= 0, '里宝牌 >0 番：和了番种仍显示「里宝牌」（实际 "' + t1 + '"）');
  } else { console.log('  --  里宝牌 >0 番：本牌谱无样本，跳过'); }
})();
/* 自家（bottom）没和牌时自己的手牌也要隐藏 —— 和了帧的显示/隐藏与用户选项无关 */
if (ronFrame) {
  var wns = (ronFrame.state.reveal && ronFrame.state.reveal.length) ? ronFrame.state.reveal : [ronFrame.state.result.winner];
  if (wns.indexOf(0) < 0) {
    show(ronFrame.state, true);
    var sb = countCls(byId.board.querySelector('.cell-bottom .p-hand'), 'back');
    check(sb === ronFrame.state.players[0].hand.length,
      '和了帧：自家没和牌时自家手牌也隐藏（牌背 ' + sb + ' / 手牌 ' + ronFrame.state.players[0].hand.length + '）');
  }
}
/* ============================================================ 7h. 流局帧的展示规则（m00635 ①②） */
console.log('\n=== 7h. 流局帧的展示规则 ===');
/* ② 中央信息栏顺序：本場 -> 供托 -> 剩余牌数 */
(function () {
  var fr = firstFrameWith(function (st) { return st.honba > 0; }) || App.rounds[0][0];
  show(fr.state, true);
  var kids = byId.board.querySelector('.center').childNodes.map(function (n) { return n._cls[0]; });
  check(kids.indexOf('c-honba') >= 0 && kids.indexOf('c-honba') < kids.indexOf('c-kyotaku') && kids.indexOf('c-kyotaku') < kids.indexOf('c-left'),
    '中央信息栏顺序：本場 -> 供托 -> 剩余牌数（' + kids.join(' > ') + '）');
})();
/* ① 荒牌流局帧：只摊开听牌家（其余含自家一律隐藏），中央写「荒牌流局」+「… 流局听牌」 */
var ryFrame = firstFrameWith(function (st) { return st.phase === 'ryuukyoku'; });
if (!ryFrame) { console.log('  --  流局帧：本牌谱无样本，跳过'); } else {
  var rst = ryFrame.state, rres = rst.result;
  var rev = (rst.reveal || []).slice(), tp = [], ankanN = 0, hiddenTiles = 0;
  for (var s = 0; s < 4; s++) { if (rres.hands[s] && rres.hands[s].length) { tp.push(s); } }
  rst.players.forEach(function (p2, i) {
    if (rev.indexOf(i) < 0) { hiddenTiles += p2.hand.length; }
    p2.melds.forEach(function (m) { if (m.callType === 'ankan') { ankanN++; } });
  });
  check(rev.join(',') === tp.join(','), '荒牌流局：摊开名单 = mjlog 的听牌家（' + rev.join(',') + ' / 期望 ' + tp.join(',') + '）');
  show(rst, false);            /* 故意不勾「隐藏他家手牌」：流局帧的显示/隐藏不受用户选项影响 */
  var rBacks = countCls(byId.board, 'back');
  check(rBacks === hiddenTiles + ankanN * 2,
    '荒牌流局：只摊开听牌家、其余（含自家）隐藏（牌背 ' + rBacks + ' = 未听牌者手牌 ' + hiddenTiles + ' + 暗杠 ' + ankanN + '×2）');
  rev.forEach(function (s2) {
    var hEl = byId.board.querySelector('.cell-' + SEATS[s2] + ' .p-hand');
    check(hEl != null && countCls(hEl, 'back') === 0, '荒牌流局：听牌家 ' + SEATS[s2] + ' 的手牌摊开（无牌背）');
  });
  var ryTxt = byId.board.querySelector('.c-result').textContent;
  var oyaR = rst.oya, W = ['東', '南', '西', '北'];
  var wantWho = tp.slice().sort(function (a, b) { return ((a - oyaR + 4) % 4) - ((b - oyaR + 4) % 4); })
    .map(function (s3) { return W[(s3 - oyaR + 4) % 4] + '家'; }).join(' ') + ' 流局听牌';
  check(ryTxt.indexOf('荒牌流局') >= 0, '荒牌流局：中央第 1 行写「荒牌流局」（' + ryTxt + '）');
  check(ryTxt.indexOf(wantWho) >= 0, '荒牌流局：中央第 2 行写听牌家「' + wantWho + '」');
}
/* 各流局方式的摊开名单（5 个真实牌谱里只有荒牌流局，其余用构造事件直接跑引擎） */
(function () {
  var cases = [
    ['', [], '荒牌流局、无人听牌 -> 四家全隐藏', '荒牌流局', '流局听牌'],
    ['nm', [2], '流局満貫 -> 只摊开満貫者（+8000 的那家）', '流局満貫', '流局听牌'],
    ['yao9', [2], '九種九牌 -> 只摊开宣告者（= 最后摸牌的那家）', '九種九牌', '荒牌流局'],
    ['reach4', [0, 1, 2, 3], '四家立直 -> 强制摊开四家', '四家立直', '荒牌流局'],
    ['kaze4', [], '四風連打 -> 强制隐藏四家', '四風連打', '荒牌流局'],
    ['rck4', [], '四槓散了 -> 强制隐藏四家', '四槓散了', '荒牌流局'],
    ['tripleRon', [0, 1, 3], '三家和了 -> 摊开三家荣和者、隐藏放铳家（who 缺失 -> 用最后摸牌的家 = 2 号）', '三家和了', '荒牌流局'],
    ['tripleRon', [0, 2, 3], '三家和了 -> 放铳家由 mjlog 的 who 指定（who=1）', '三家和了', '荒牌流局', 1]
  ];
  var base0 = REPLAY.cloneState(App.rounds[0][0].state);
  cases.forEach(function (cs) {
    var st = REPLAY.cloneState(base0);
    st.drawn = { player: 2, tile: 5 };          /* 九種九牌：宣告者 = 最后摸牌的那家 */
    var gain = [0, 0, 0, 0];
    if (cs[0] === 'nm') { gain[2] = 8000; gain[0] = -2000; gain[1] = -2000; gain[3] = -4000; }
    REPLAY.applyEvent(st, {
      type: 'ryuukyoku', reason: cs[0], who: (cs.length > 5 ? cs[5] : null), hands: [null, null, null, null],
      ba: [0, 0], before: st.scores.slice(), gain: gain, owari: null
    });
    check((st.reveal || []).join(',') === cs[1].join(','), cs[2] + '（reveal = [' + (st.reveal || []).join(',') + ']）');
    show(st, false);
    var cTxt = byId.board.querySelector('.c-result').textContent;
    check(cTxt.indexOf(cs[3]) >= 0 && cTxt.indexOf(cs[4]) < 0, cs[2] + '：中央显示「' + cTxt + '」');
  });
})();

/* ============================================================ 8. 牌谱分析 / 牌谱检索 */
console.log('\n=== 8. 牌谱分析与检索（本地服务） ===');

/* --- 同步 thenable：把被 stub 的 fetch 变成同步，便于顺序断言 --- */
function SyncThen(v, isErr) { this.v = v; this.err = !!isErr; }
SyncThen.prototype.then = function (onOk, onErr) {
  if (this.err) {
    if (!onErr) { return this; }
    try { var r = onErr(this.v); return (r instanceof SyncThen) ? r : new SyncThen(r); }
    catch (e) { return new SyncThen(e, true); }
  }
  if (!onOk) { return this; }
  try { var r2 = onOk(this.v); return (r2 instanceof SyncThen) ? r2 : new SyncThen(r2); }
  catch (e) { return new SyncThen(e, true); }
};
SyncThen.prototype['catch'] = function (onErr) { return this.then(null, onErr); };
function syncOk(v) { return new SyncThen(v); }

var LOG2 = '2026083021gm-00a9-0000-d0810acf';
var g2 = MJLOG.parse(fs.readFileSync(xmlPath(LOG2), 'utf8'));
g2.logId = LOG2;
var recs2 = MJSFEAT.recordsForRound(g2, 0);
function dbRow(rec, logFile) {
  return { idx: rec.ev_index, log_id: rec.log_id, url: rec.url, round_index: rec.round_index,
           ev_index: rec.ev_index, frame_index: rec.frame_index, seat: rec.seat,
           joukyoku: rec.joukyoku, honba: rec.honba, wind: rec.wind, junme: rec.junme,
           kind: rec.kind, label: MJSFEAT.rowLabel(rec), log_path: 'data/' + logFile + '.xml' };
}
/* 第 7 节可能把别的牌谱载进来了，这里先回到第 2 节的牌谱 */
App.loadText(fs.readFileSync(xmlPath(f.replace(/\.xml$/, '')), 'utf8'), f);
var gCur = MJLOG.parse(fs.readFileSync(xmlPath(f.replace(/\.xml$/, '')), 'utf8'));
gCur.logId = f.replace(/\.xml$/, '');
var recsCur = MJSFEAT.recordsForRound(gCur, 0);
check(recsCur.length > 3 && recs2.length > 3, '打点行：当前谱 ' + recsCur.length + ' 条 / 另一谱 ' + recs2.length + ' 条');
var RC0 = recsCur[0], RC1 = recsCur[1];
var ROW0 = dbRow(RC0, f.replace(/\.xml$/, '')), ROW1 = dbRow(recs2[0], LOG2);

/* 副露帧（吃/碰后等待出牌的那一帧）—— 第 13 轮新增的数据库主体 */
var recCall = null;
/* 第 62 轮：跳过 kind='wait' 的行 —— 本节测的是「吃 / 碰后等待出牌的那一帧」 */
for (var ci = 0; ci < recsCur.length; ci++) {
  if (recsCur[ci].kind === 'chi' || recsCur[ci].kind === 'pon') { recCall = recsCur[ci]; break; }
}
var ROWCALL = recCall ? dbRow(recCall, f.replace(/\.xml$/, '')) : null;
/* 第 21 轮 / 第 29 轮 / 第 36 轮 / 第 52 轮 / 第 59 轮 / 第 62 轮 / 第 63 轮 / 第 74 轮：假数据库行的 42 个特征值
   （第零类 7 项 + 第一类 17 项 + 第二类 17 项 + 第三类 1 项：枚举一律 '是' / 实数 0.5 / 整数 1） */
var FAKE_FEATS = {};
MJSFEAT.FEATURES.forEach(function (f4) {
  FAKE_FEATS[f4.key] = (f4.kind === 'enum') ? '是' : (f4.kind === 'float' ? 0.5 : 1);
});

/* 8.1 手动播放到摸牌帧时，静态帧的特征串必须与分析脚本给的条目名逐字一致 */
App.itemIndex = -1;
App.setRound(RC0.round_index, RC0.frame_index);
check(byId.frameKey.textContent === ROW0.label,
      '手动播放的特征串 = "' + byId.frameKey.textContent + '"（期望 "' + ROW0.label + '"）');
App.setFrame(RC1.frame_index);
check(byId.frameKey.textContent === dbRow(RC1, f.replace(/\.xml$/, '')).label,
      '换一帧后特征串 = "' + byId.frameKey.textContent + '"');
App.setFrame(0);
check(byId.frameKey.textContent === '', '开局帧（还没摸牌）不显示特征串');
check(App.frameKeyText().indexOf('本場') >= 0 || App.frameKeyText() === '', 'frameKeyText() 可独立调用');

check(!!recCall, '本局有副露帧可测：' + (recCall ? recCall.kind + ' / ' + recCall.junme + '巡目' : '无'));
App.itemIndex = -1;
App.setRound(recCall.round_index, recCall.frame_index);
check(byId.frameKey.textContent === MJSFEAT.rowLabel(recCall),
      '手动播放到副露帧的特征串 = "' + byId.frameKey.textContent + '"（期望 "' + MJSFEAT.rowLabel(recCall) + '"）');
check(MJSFEAT.rowLabel(recCall) !== MJSFEAT.rowLabel(RC0) || recCall.junme === RC0.junme,
      '副露帧巡目与摸牌帧口径一致：' + MJSFEAT.rowLabel(recCall));

/* --- 假服务 --- */
var reqs = [];
/* 第 21 轮：可由测试改写的假响应（分析/下载进度、帧特征、条目明细） */
var FAKE = { anProgress: null, dlProgress: null, frameFeats: null, detailRow: null };
global.fetch = function (url, opt) {
  var body = (opt && opt.body) ? JSON.parse(opt.body) : null;
  var path = String(url).replace(/^https?:\/\/[^/]+/, '');
  reqs.push({ url: path, method: (opt && opt.method) || 'GET', body: body });
  function json(obj, code) {
    return syncOk({ ok: (code || 200) < 400, status: code || 200,
                    text: function () { return syncOk(JSON.stringify(obj)); } });
  }
  if (path.indexOf('/api/dbs') === 0) {
    return json({ ok: true, dbs: [{ name: 'paipu', size: 400000, meta: { record_count: '2679', tool: 'node' },
                                    app_version: '0.2.0', compatible: true }] });
  }
  if (path.indexOf('/api/features') === 0) {
    return json({ ok: true, name: '天凤牌谱分析', version: '1.4.3', schema_version: 11,
                  features: MJSFEAT.FEATURES,
                  first_features: MJSFEAT.FIRST_FEATURES, second_features: MJSFEAT.SECOND_FEATURES,
                  third_features: MJSFEAT.THIRD_FEATURES, wait_modes: ['出牌', '鸣牌响应'],
                  full_note: '勾选：把每一帧的原始数据写进 frame_full 表，以后新增特征可以直接用旧牌谱重算；'
                    + '不勾选：只写 42 个特征值，数据库更小，但新增特征时必须重新分析牌谱。' });
  }
  if (path.indexOf('/api/paipu-browse') === 0) {
    var bdir = decodeURIComponent((path.split('dir=')[1] || '')) || 'data/paipu';
    var bfiles = bdir === 'data/paipu' ? ['data/paipu/' + f, 'data/paipu/abc.json.gz']
                                       : [bdir.replace(/\/$/, '') + '/abc.json.gz'];
    return json({ ok: true, root: 'D:/x/data/paipu', root_rel: 'data/paipu', dir: 'D:/x/' + bdir,
                  dir_rel: bdir, dirs: ['data/paipu', 'data/paipu/sub'], files: bfiles });
  }
  if (path.indexOf('/api/scan') === 0) {
    var dirq = decodeURIComponent((path.split('dir=')[1] || 'data'));
    return json({ ok: true, dir: dirq, count: 5, files: [f, LOG2 + '.xml'] });
  }
  if (path.indexOf('/api/analyze-progress') === 0) {
    return json({ ok: true, progress: FAKE.anProgress || {} });
  }
  if (path.indexOf('/api/download-progress') === 0) {
    return json({ ok: true, progress: FAKE.dlProgress || {} });
  }
  if (path.indexOf('/api/analyze') === 0) {
    return json({ ok: true, db: 'data/db/paipu.sqlite', db_total: 2679, logs: 2, rounds: 10,
                  annotations: 300, tool: 'node', warnings: [],
                  extend: !!(body && body.extend), skipped: [] });
  }
  if (path.indexOf('/api/read') === 0) {
    var q = decodeURIComponent(path.split('path=')[1] || '');
    var id = q.split('/').pop().replace(/\.xml$/, '');
    return json({ ok: true, path: q, text: fs.readFileSync(xmlPath(id), 'utf8') });
  }
  if (path.indexOf('/api/query') === 0) {
    if (body && body.conds && body.conds[0] && body.conds[0].expr === 'boom') {
      return json({ ok: false, error: '「巡目」的可接受条件：整数 / 区间(1-3) / 列表(1,2,3) / 比较(>=3)，收到「boom」' }, 400);
    }
    if (body && body.conds && body.conds[0] && body.conds[0].expr === 'call') {
      return json({ ok: true, total: 2, limit: body.limit, offset: 0, used: ['巡目'], rows: [ROWCALL, ROW0] });
    }
    return json({ ok: true, total: 2, limit: body.limit, offset: 0, used: ['巡目'], rows: [ROW0, ROW1] });
  }
  if (path.indexOf('/api/browse') === 0) {
    return json({ ok: true, total: 2, limit: body.limit, offset: 0, rows: [ROW0, ROW1] });
  }
  if (path.indexOf('/api/frame-feats') === 0) {
    return json({ ok: true, row: FAKE.frameFeats });
  }
  if (path.indexOf('/api/detail') === 0) {
    return json({ ok: true, row: FAKE.detailRow });
  }
  if (path.indexOf('/api/download') === 0) {
    var sub = (body && body.subdir) || '';
    return json({ ok: true, started: true, dir: 'data/paipu/' + sub, total: 2, urls: 2 });
  }
  return json({ ok: false, error: '未知接口 ' + path }, 404);
};

/* 8.2 牌谱分析视图 */
byId.btnGoAnalyze.fire('click');
check(App.view === 'analyze' && !byId['view-analyze'].classList.contains('hidden'), '进入牌谱分析视图');
check(byId.anDbList.childNodes.length === 1 && byId.anDbList.textContent.indexOf('2679') >= 0,
      '数据库列表：' + byId.anDbList.textContent);
byId.btnScan.fire('click');
check(App.analyzeState.files.length === 2, '扫描到 ' + App.analyzeState.files.length + ' 个牌谱文件');
check(byId.anFileList.childNodes.length === 2, '文件列表 ' + byId.anFileList.childNodes.length + ' 行');
check(byId.anFileCount.textContent.indexOf('2') >= 0, '文件计数：' + byId.anFileCount.textContent);
byId.anFileList.childNodes[1].querySelector('input').checked = false;
byId.btnAnalyze.fire('click');
var areq = null;
for (var ri2 = reqs.length - 1; ri2 >= 0; ri2--) {
  if (reqs[ri2].url === '/api/analyze') { areq = reqs[ri2]; break; }
}
check(areq.url === '/api/analyze' && areq.body && areq.body.paths.length === 1,
      '只提交勾选的文件（' + (areq.body ? areq.body.paths.length : '?') + ' 个）');
check(byId.anMsg.textContent.indexOf('完成') >= 0, '分析结果提示：' + byId.anMsg.textContent);

/* 8.2b 牌谱目录 / 牌谱文件改成下拉选择（用户 m01171 第 2 条：前缀固定 data/paipu） */
check(byId.anSourceDir.tagName === 'SELECT' && byId.anSourceFile.tagName === 'SELECT',
      '牌谱目录 / 牌谱文件改成下拉选择');
check(App.isNagaFileName('x.json.gz') && App.isNagaFileName('x.json') && App.isNagaFileName('x.gz')
      && !App.isNagaFileName('x.xml') && !App.isNagaFileName('x.mjlog'),
      'NAGA 报告（.json.gz / .json / .gz）走服务端转换，天凤牌谱仍本地解析');
byId.anSourceDir.value = 'data/paipu/sub';
byId.anSourceDir.fire('change');
check(byId.anSourceFile.childNodes.length === 2
      && byId.anSourceFile.childNodes[1].value === 'data/paipu/sub/abc.json.gz',
      '切换目录后牌谱文件下拉刷新：' + byId.anSourceFile.childNodes.length + ' 项');
byId.anSourceFile.value = 'data/paipu/sub/abc.json.gz';
byId.anSourceFile.fire('change');
check(App.analyzeState.files.length === 1 && App.analyzeState.files[0] === 'data/paipu/sub/abc.json.gz',
      '只选一个牌谱文件时只分析这一个：' + JSON.stringify(App.analyzeState.files));
byId.btnScan.fire('click');
check(App.analyzeState.files.length === 2, '点「扫描」回到整个目录：' + App.analyzeState.files.length + ' 个牌谱文件');

/* 8.3 牌谱检索：添加特征 / 不能重复 */
byId.btnGoSearch.fire('click');
check(App.view === 'search', '进入牌谱检索视图');
/* 8.3a 第零类特征检索方案（用户 m04556 ③）：四种互斥方案 + 「同时具有」的方形多选框，默认不选 = 不筛选 */
check(byId.aiModes.childNodes.length === 4, '第零类方案 ' + byId.aiModes.childNodes.length + ' 个互斥选项');
check(byId.aiModes.textContent.indexOf('任意AI决策') >= 0 && byId.aiModes.textContent.indexOf('NAGA决策') >= 0
      && byId.aiModes.textContent.indexOf('Mortal决策') >= 0 && byId.aiModes.textContent.indexOf('同时具有') >= 0,
      '方案名：' + byId.aiModes.textContent);
check(App.aiPayload() === null && byId.aiPicks.classList.contains('hidden'),
      '默认不选任何方案 = 不筛选，「同时具有」的多选框隐藏');
App.setAiMode('naga');
check(App.aiPayload().mode === 'naga' && App.aiPayload().picks.length === 0,
      '选「NAGA决策」= ' + JSON.stringify(App.aiPayload()));
check(byId.aiModes.childNodes[1].childNodes[0].checked === true, '单选钮状态与方案同步（第 2 项被勾上）');
App.setAiMode('multi');
check(!byId.aiPicks.classList.contains('hidden') && byId.aiPicks.childNodes.length === 7,
      '「同时具有」显示 7 个第零类多选框（' + byId.aiPicks.childNodes.length + ' 个，用户 m05937 ② / m09507）');
App.setAiPick('ai_balance', true);
App.setAiPick('ai_mortal41b', true);
check(App.aiPayload().mode === 'multi' && App.aiPayload().picks.join(',') === 'ai_balance,ai_mortal41b',
      '多选 = ' + App.aiPayload().picks.join(','));
App.setAiPick('ai_balance', false);
check(App.aiPayload().picks.join(',') === 'ai_mortal41b', '取消勾选后 = ' + App.aiPayload().picks.join(','));
byId.scDbPath.value = 'data/db/paipu.sqlite';
App.setAiMode('any');
byId.btnRunQuery.fire('click');
var aqreq = reqs[reqs.length - 1];
check(aqreq.url === '/api/query' && aqreq.body.conds.length === 0 && aqreq.body.ai && aqreq.body.ai.mode === 'any',
      '只有第零类方案也能检索（conds 空 + ai 透传）：' + JSON.stringify(aqreq.body.ai));
byId.btnAiClear.fire('click');
check(App.aiPayload() === null && byId.aiPicks.classList.contains('hidden'), '「清除方案」回到不筛选');
check(byId.scFeatSelect.childNodes.length === MJSFEAT.FEATURES.length - MJSFEAT.AI_FEATURES.length - 1,
      '特征下拉 ' + byId.scFeatSelect.childNodes.length + ' 项 = 42 − 7 − 1（第零类与第三类都不进下拉，用户 m04556 ③ / m07289）');
/* 第 63 轮（用户 m07289 的补充要求）：第三类特征「局面」是第零类框右端的必选单选
   「出牌」（默认，= 等待出牌的局面）/「鸣牌响应」；不选也按默认「出牌」筛选（服务端 AND）。 */
check(aqreq.body.wait === '出牌', '检索请求默认带第三类单选 wait=出牌：' + JSON.stringify(aqreq.body.wait));
check(App.searchState.wait === '出牌' && App.waitPayload() === '出牌',
      '局面单选默认「出牌」= ' + App.searchState.wait);
check(html.indexOf('name="waitMode"') >= 0 && html.indexOf('是否具有AI决策') >= 0
      && html.indexOf('第零类特征（AI 分析模型）') < 0,
      '第零类框标题改「是否具有AI决策」，右端放上下两行「出牌 / 鸣牌响应」单选（用户 m07289）');
byId.btnRunQuery.fire('click');
check(byId.scMsg.textContent.indexOf('第零类特征') >= 0, '空条件被拦下：' + byId.scMsg.textContent);
byId.scFeatSelect.value = 'junme';
byId.btnAddFeat.fire('click');
check(App.searchState.conds.length === 1 && App.searchState.conds[0].key === 'junme', '添加「巡目」条件');
check(byId.scCondList.querySelectorAll('.cond-row').length === 1, '条件列表 1 行');
check(byId.scFeatSelect.childNodes.length === MJSFEAT.FEATURES.length - MJSFEAT.AI_FEATURES.length - 1 - 1, '已添加的特征不再出现在下拉里');
byId.btnRunQuery.fire('click');
check(byId.scMsg.textContent.indexOf('还没填写') >= 0, '没填条件被拦下：' + byId.scMsg.textContent);

/* 8.4 检索 -> 结果条目 -> 跳帧 */
var inp = byId.scCondList.querySelector('.cond-input');
inp.value = '3';
inp.fire('input');
byId.btnRunQuery.fire('click');
var qreq = reqs[reqs.length - 1];
check(qreq.url === '/api/query' && qreq.body.conds[0].expr === '3', '检索条件 = ' + JSON.stringify(qreq.body.conds));
check(qreq.body.wait === '出牌', '检索请求默认带第三类单选 wait=出牌：' + JSON.stringify(qreq.body.wait));
/* 第 63 轮（用户 m07289 的补充要求）：第三类特征「局面」是第零类框右端的必选单选 —— 切到「鸣牌响应」
   后请求带 wait=鸣牌响应（服务端按 f_meld_wait 过滤，与其它条件 AND）。 */
App.setWait('鸣牌响应');
byId.btnRunQuery.fire('click');
var wq = reqs[reqs.length - 1];
check(wq.url === '/api/query' && wq.body.wait === '鸣牌响应',
      '切到「鸣牌响应」后请求带 wait=鸣牌响应（' + JSON.stringify(wq.body.wait) + '）');
App.setWait('出牌');
check(App.waitPayload() === '出牌' && App.searchState.wait === '出牌', '切回默认「出牌」');
check(App.items.length === 2 && App.itemSource === 'query', '拿到 ' + App.items.length + ' 个条目');
check(byId.scResultList.childNodes.length === 2, '结果列表 ' + byId.scResultList.childNodes.length + ' 行');
check(byId.scResultInfo.textContent.indexOf('2') >= 0, '结果计数：' + byId.scResultInfo.textContent);
byId.scResultList.childNodes[0].fire('click');
check(App.view === 'replay', '点条目后进入播放视图');
check(App.roundIndex === ROW0.round_index && App.frameIndex === ROW0.frame_index,
      '跳到 局' + App.roundIndex + ' / 帧' + App.frameIndex + '（期望 局' + ROW0.round_index + ' / 帧' + ROW0.frame_index + '）');
check(byId.frameKey.textContent === ROW0.label, '静态帧特征串 = "' + byId.frameKey.textContent + '"');
check(byId.itemInfo.textContent.indexOf('1 / 2') >= 0, '条目导航：' + byId.itemInfo.textContent);
check(byId.btnPrevItem.disabled === true && byId.btnNextItem.disabled === false, '第一条目时「上一条目」禁用');
/* ③ 静态帧（检索条目）固定显示他家手牌：按钮禁用 + 强制显示（用户 m02984 ③） */
check(byId.btnOthers.disabled === true && App.hideOthers === false,
  '③ 静态帧（检索条目）下「隐藏他家手牌」禁用 + 强制显示他家手牌（disabled=' + byId.btnOthers.disabled
  + ' / hideOthers=' + App.hideOthers + '）');
check(byId.btnOthers.title.indexOf('固定显示') >= 0, '③ 按钮 title 说明原因：' + byId.btnOthers.title);
/* ① 静态帧只允许用右上角的条目导航，下面的播放控制面板整块禁用（用户 m03089 ①） */
var cbtns = byId.controls.querySelectorAll('button');
var ctrlAllOff = true;
for (var ci = 0; ci < cbtns.length; ci++) { if (!cbtns[ci].disabled) { ctrlAllOff = false; } }
check(byId.controls.classList.contains('locked'), '① 静态帧时控制面板带 .locked 类');
check(ctrlAllOff, '① 静态帧时控制面板 ' + cbtns.length + ' 个按钮全部禁用');
check(byId.btnNextItem.disabled === false, '① 条目导航按钮仍可用（下一条目）');
clickAct('next');   /* 控制面板上的按钮不该再响应 */
check(App.view === 'replay' && byId.frameKey.textContent === ROW0.label,
  '① 静态帧时点控制面板的「下一步」不会跳帧（仍是条目帧 ' + byId.frameKey.textContent + '）');
/* ③ 静态帧（牌谱检索 / 全部浏览）主视角固定切到当前决策者 + 禁用「切换主视角」（用户 m03343 ③） */
var decSeat = App.frameSeatOf(App.rounds[App.roundIndex][App.frameIndex].state);
check(decSeat !== null && App.viewRot[0] === decSeat && App.selfSeat === decSeat,
  '③ 静态帧主视角 = 当前决策者（决策者 ' + decSeat + ' / 旋转向量 [' + App.viewRot.join(',') + ']）');
check(byId.btnView.disabled === true, '③ 静态帧时「切换主视角」按钮禁用');
check(byId.btnView.title.indexOf('固定') >= 0, '③ 按钮 title 说明原因：' + byId.btnView.title);
var decName = App.rounds[App.roundIndex][App.frameIndex].state.players[decSeat].name;
check(!!decName && byId.board.querySelector('.cell-bottom').textContent.indexOf(decName) >= 0,
  '③ 决策者画在下方主视角位置：' + decName);

/* 8.5 上一条目 / 下一条目（换到另一个牌谱，走 /api/read） */
byId.btnNextItem.fire('click');
check(App.itemIndex === 1, 'itemIndex = ' + App.itemIndex);
var readReq = null;
for (var rqi = reqs.length - 1; rqi >= 0; rqi--) {
  if (reqs[rqi].url.indexOf('/api/read') === 0) { readReq = reqs[rqi]; break; }
}
check(!!readReq, '跨牌谱时通过 /api/read 载入：' + (readReq ? readReq.url.slice(0, 40) : '（没有 /api/read 请求）'));
check(App.roundIndex === ROW1.round_index && App.frameIndex === ROW1.frame_index, '跳帧跟随条目');
check(byId.frameKey.textContent === ROW1.label, '特征串 = "' + byId.frameKey.textContent + '"');
check(App.fileName === LOG2 + '.tenhou', '已切换到 ' + App.fileName);
byId.btnNextItem.fire('click');
check(App.itemIndex === 1 && byId.btnNextItem.disabled === true, '最后一条目时「下一条目」禁用');
byId.btnPrevItem.fire('click');
check(App.itemIndex === 0, '「上一条目」回到第 1 条');
check(App.fileName === f.replace(/\.xml$/, '.tenhou'), '回退时切回前一个牌谱 ' + App.fileName);
check(App.roundIndex === ROW0.round_index, '回退后回到前一个牌谱的帧');

/* 8.6 全部浏览 */
byId.btnBrowseAll.fire('click');
var breq = reqs[reqs.length - 1];
check(breq.url === '/api/browse' && breq.body.limit === App.searchState.pageSize,
  '「全部浏览」也按段载入（limit = ' + App.searchState.pageSize + ' 条，用户 m09339 ②）');
check(App.itemSource === 'browse' && App.items.length === 2, '浏览条目 ' + App.items.length + ' 个');
check(!byId.controls.classList.contains('locked'), '① 退出条目模式后控制面板恢复可用（不带 .locked）');
byId.scResultList.childNodes[0].fire('click');
check(byId.itemInfo.textContent.indexOf('全部浏览') >= 0, '条目导航标注来源：' + byId.itemInfo.textContent);

/* 8.7 检索分段载入（用户 m09339 ②）：每段 1000 条、翻段时替换上一段、条目号跨段连续 */
function segThen(o) { return { then: function (cb) { cb(o); return segThen(o); },
                              'catch': function () { return segThen(o); } }; }
function segRow(g) {
  return { kind: 'draw', log_id: 'L' + g, round_index: 0, frame_index: 0, seat: 0,
           label: 'L' + g + ' 東一局 0本場 1巡目 東家', log_path: 'data/paipu/L' + g + '.tenhou' };
}
var SEG_TOTAL = 8, segCalls = [];
check(App.searchState.pageSize === 1000, '检索每段载入 1000 条（用户 m09339 ②）：' + App.searchState.pageSize);
App.searchState.fetch = function (offset) {
  segCalls.push(offset);
  var rows = [];
  for (var i = 0; i < App.searchState.pageSize && offset + i < SEG_TOTAL; i++) { rows.push(segRow(offset + i)); }
  return segThen({ rows: rows, total: SEG_TOTAL });
};
App.itemSource = 'query'; App.itemIndex = -1;
App.items = []; App.searchState.base = -1; App.searchState.total = 0;   /* 清掉上一节（全部浏览）留下的段 */
App.loadSegment(0);
check(segCalls.join(',') === '0' && App.searchState.base === 0 && App.searchState.total === SEG_TOTAL
  && App.items.length === SEG_TOTAL, '第一段载入全部 ' + SEG_TOTAL + ' 条（offset=0）');
App.itemIndex = SEG_TOTAL - 1; App.syncItemNav();
check(byId.itemInfo.textContent.indexOf(SEG_TOTAL + ' / ' + SEG_TOTAL) >= 0 && byId.btnNextItem.disabled === true,
  '末条显示 ' + SEG_TOTAL + ' / ' + SEG_TOTAL + '、下一条目置灰：' + byId.itemInfo.textContent);
App.loadSegment(0);
check(segCalls.join(',') === '0', '同一段已在内存、不重复取数');
App.searchState.pageSize = 3;
App.loadSegment(3);
check(segCalls.join(',') === '0,3' && App.searchState.base === 3 && App.items.length === 3
  && App.items[0].log_id === 'L3', '翻到第 4 条起 ⇒ 载入第二段（offset=3）、第一段被替换（首条 L3）');
App.itemIndex = 2; App.syncItemNav();
check(byId.itemInfo.textContent.indexOf('6 / ' + SEG_TOTAL) >= 0 && byId.btnNextItem.disabled === false,
  '第二段末条 = 6 / 8、仍可「下一条目」：' + byId.itemInfo.textContent);
App.itemIndex = 0; App.syncItemNav();
check(byId.itemInfo.textContent.indexOf('4 / ' + SEG_TOTAL) >= 0 && byId.btnPrevItem.disabled === false,
  '第二段首条 = 4 / 8、仍可「上一条目」：' + byId.itemInfo.textContent);
App.searchState.pageSize = 1000; App.searchState.fetch = null;
App.searchState.base = 0; App.searchState.total = 0;
App.items = []; App.itemIndex = -1; App.syncItemNav();


/* 8.8 副露帧条目（第 13 轮新增主体） */
inp.value = 'call';
inp.fire('input');
byId.btnRunQuery.fire('click');
check(App.items.length === 2 && App.items[0].kind === recCall.kind, '副露帧条目 ' + App.items.length + ' 个，kind = ' + App.items[0].kind);
byId.scResultList.childNodes[0].fire('click');
check(App.frameIndex === ROWCALL.frame_index && App.roundIndex === ROWCALL.round_index,
      '跳到副露帧 局' + App.roundIndex + ' / 帧' + App.frameIndex);
check(byId.frameKey.textContent === ROWCALL.label, '副露帧静态帧特征串 = "' + byId.frameKey.textContent + '"');
check(byId.itemInfo.textContent.indexOf('食后帧') >= 0 || byId.itemInfo.textContent.indexOf('碰后帧') >= 0,
      '条目导航标注副露帧：' + byId.itemInfo.textContent);
/* 8.7 错误提示 */
inp.value = 'boom';
inp.fire('input');
byId.btnRunQuery.fire('click');
check(byId.scMsg.textContent.indexOf('检索失败') >= 0, '坏条件提示：' + byId.scMsg.textContent);

/* 8.9 互斥取值特征改走下拉选取（第 14 轮） */
byId.btnClearConds.fire('click');
check(App.searchState.conds.length === 0, '清空条件');
byId.scFeatSelect.value = 'oya_meld';
byId.btnAddFeat.fire('click');
check(App.searchState.conds.length === 1 && App.searchState.conds[0].key === 'oya_meld',
      '添加「亲家（他家）副露状态」条件');
var sel = byId.scCondList.querySelector('.cond-select');
check(!!sel && sel.tagName === 'SELECT', '互斥取值特征渲染为下拉：' + (sel ? sel.tagName : '无'));
check(sel.childNodes.length === 3, '下拉项 = 占位 + 2 个取值（当前 ' + sel.childNodes.length + ' 项）');
check(sel.childNodes[0].value === '' && sel.childNodes[0].textContent === '请选择', '第一项是占位「请选择」');
check(sel.childNodes[1].value === '是' && sel.childNodes[2].value === '否', '取值项 = 是 / 否');
check(byId.scCondList.textContent.indexOf('副露状态') >= 0,
      '行名已改为「亲家（他家）副露状态」：' + byId.scCondList.textContent);
byId.btnRunQuery.fire('click');
check(byId.scMsg.textContent.indexOf('还没选择') >= 0, '没选下拉被拦下：' + byId.scMsg.textContent);
sel.value = '是';
sel.fire('change');
byId.btnRunQuery.fire('click');
var ereq = reqs[reqs.length - 1];
check(ereq.url === '/api/query' && ereq.body.conds.length === 1 && ereq.body.conds[0].key === 'oya_meld'
      && ereq.body.conds[0].expr === '是', '下拉取值进入检索条件：' + JSON.stringify(ereq.body.conds));
byId.btnClearConds.fire('click');
byId.scFeatSelect.value = 'junme';
byId.btnAddFeat.fire('click');
var tinp = byId.scCondList.querySelector('.cond-input');
check(!!tinp && tinp.tagName === 'INPUT' && tinp.placeholder.indexOf('整数') >= 0,
      '整数特征仍是文本框：' + (tinp ? tinp.placeholder : '无'));
byId.btnClearConds.fire('click');
/* 8.10 第二类特征接入 / 帧特征面板 / 分析进度 / 牌谱下载（第 21 轮） */
console.log('\n=== 8.10 第二类特征 / 帧特征面板 / 分析进度 / 牌谱下载（第 21 轮） ===');

/* (1) 42 个特征（7 第零类 + 17 第一类 + 17 第二类 + 1 第三类；第 36 轮新增立直家（他家）一发巡，第 52 轮新增第零类三项，
   第 59 轮再补 Mortal 避四 / 争一，第 62 轮新增「等待鸣牌」，第 63 轮把「等待鸣牌」编为第三类特征，
   第 74 轮补新版 NAGA 避四 / 争一，用户 m05937 ② / m07289 / m09507） */
byId.btnClearConds.fire('click');
check(MJSFEAT.FEATURES.length === 42, '前端特征注册表 ' + MJSFEAT.FEATURES.length + ' 项 = 42（7 第零类 + 17 第一类 + 17 第二类 + 1 第三类）');
check(byId.scFeatSelect.childNodes.length === 34, '特征下拉 ' + byId.scFeatSelect.childNodes.length + ' 项 = 42 − 7 − 1（第零类与第三类不进下拉）');
var fkeys = MJSFEAT.FEATURES.map(function (f5) { return f5.key; });
check(fkeys.indexOf('shanten_mentsu') >= 0 && fkeys.indexOf('damaten_tsumo_score') >= 0
      && fkeys.indexOf('riichi_others_danger_suji') >= 0 && fkeys.indexOf('riichi_others_danger_ryanmen') >= 0,
      '第二类特征已注册：面子手向听 / 默听自摸期望打点 / 危险筋组 / 危险两面组');
check(MJSFEAT.AI_FEATURES.length === 7 && MJSFEAT.FEATURES[0].key === 'ai_balance'
      && MJSFEAT.FEATURES[0].name === 'NAGA-平衡 分析' && MJSFEAT.FEATURES[0].values.join('/') === '是/否'
      && MJSFEAT.FEATURES[1].key === 'ai_superhuro' && MJSFEAT.FEATURES[1].name === 'NAGA-超副露 分析'
      && MJSFEAT.FEATURES[2].key === 'ai_naga_avoid4' && MJSFEAT.FEATURES[2].name === 'NAGA-避四 分析'
      && MJSFEAT.FEATURES[3].key === 'ai_naga_aggressive' && MJSFEAT.FEATURES[3].name === 'NAGA-争一 分析'
      && MJSFEAT.FEATURES[4].key === 'ai_mortal41a' && MJSFEAT.FEATURES[4].name === 'Mortal-4.1-避四 分析'
      && MJSFEAT.FEATURES[5].key === 'ai_mortal41b' && MJSFEAT.FEATURES[5].name === 'Mortal-4.1-平衡 分析'
      && MJSFEAT.FEATURES[6].key === 'ai_mortal41c' && MJSFEAT.FEATURES[6].name === 'Mortal-4.1-争一 分析',
      '前 7 项 = 第零类特征（NAGA-平衡 / NAGA-超副露 / NAGA-避四 / NAGA-争一 / Mortal-4.1-避四 / Mortal-4.1-平衡 / Mortal-4.1-争一，取值 是/否，用户 m05937 ② / m09507）');
check(fkeys.indexOf('naga') < 0, '旧第一类特征「NAGA决策」（key = naga）已移入第零类（用户 m04556 ②）');
check(fkeys.indexOf('ippatsu') >= 0 && MJSFEAT.FEATURES[16].key === 'riichi_others_n'
      && MJSFEAT.FEATURES[17].key === 'ippatsu' && MJSFEAT.FEATURES[17].name === '立直家（他家）一发巡'
      && MJSFEAT.FEATURES[17].values.join('/') === '是/否',
      '立直家（他家）一发巡紧随「立直家（他家）数量」（下标 16 / 17，前 7 项是第零类）');
check(MJSFEAT.FEATURES[12].key === 'rank' && MJSFEAT.FEATURES[13].key === 'riichi_self',
      '「顺位」之后紧跟第一类「自家立直状态」（「等待鸣牌」已移出第一类，用户 m07289）');
check(MJSFEAT.THIRD_FEATURES.length === 1 && MJSFEAT.THIRD_FEATURES[0].key === 'meld_wait'
      && MJSFEAT.THIRD_FEATURES[0].name === '等待鸣牌' && MJSFEAT.THIRD_FEATURES[0].values.join('/') === '是/否'
      && MJSFEAT.FIRST_FEATURES.length === 17 && MJSFEAT.SECOND_FEATURES.length === 17
      && MJSFEAT.FEATURES[41].key === 'meld_wait' && fkeys.indexOf('meld_wait') === 41,
      '「等待鸣牌」独立成第三类（1 项，排在 42 项最后：7 + 17 + 17 + 1，用户 m07289）');
check(byId.scFeatSelect.textContent.indexOf('等待鸣牌') < 0, '第三类特征不出现在检索下拉里（用户 m07289）');

/* (2) 实数特征走文本框 + 小数条件提示 */
byId.scFeatSelect.value = 'junme';
byId.btnAddFeat.fire('click');
byId.scFeatSelect.value = 'damaten_tsumo_score';
byId.btnAddFeat.fire('click');
var finps = byId.scCondList.querySelectorAll('.cond-input');
check(finps.length === 2, '两个文本框条件：' + finps.length + ' 行（巡目 / 实数特征）');
check(!!finps[1] && finps[1].placeholder.indexOf('实数') >= 0, '实数特征提示：' + (finps[1] ? finps[1].placeholder : '无'));
check(byId.scCondList.textContent.indexOf('默听自摸期望打点') >= 0, '实数特征行名 = 默听自摸期望打点');

/* (3) 帧特征面板：条目模式走 /api/detail，34 行（42 − 第零类 7 项 − 第三类 1 项）+ 检索用到的特征高亮（用户 m05937 ② / m07289） */
byId.scDbPath.value = 'data/db/paipu.sqlite';
finps[0].value = 'call';          /* 第 1 条条件走假接口的 call 分支 */
finps[0].fire('input');
finps[1].value = '0.5';
finps[1].fire('input');
byId.btnRunQuery.fire('click');
check(App.items.length === 2 && App.items[0].kind !== 'draw', '再次拿到副露帧条目 ' + App.items.length + ' 个');
FAKE.detailRow = { idx: App.items[0].idx, log_id: App.items[0].log_id, label: App.items[0].label, feats: FAKE_FEATS };
App.featPanelState.key = '';   /* 8.8 用同一 idx 缓存过（当时假响应还是 null），置空让面板重新拉一次 */
byId.scResultList.childNodes[0].fire('click');
var dreq = null;
for (var di = reqs.length - 1; di >= 0; di--) { if (reqs[di].url.indexOf('/api/detail') === 0) { dreq = reqs[di]; break; } }
check(!!dreq && dreq.body.idx === App.items[0].idx && dreq.body.db === 'data/db/paipu.sqlite',
      '条目模式走 /api/detail 且带同一个数据库（m03580 修复）：' + JSON.stringify(dreq ? dreq.body : null));
var frows = byId.featPanelList.querySelectorAll('.feat-row');
check(frows.length === 34, '帧特征面板 ' + frows.length + ' 行 = 34 个特征（42 − 第零类 7 项 − 第三类 1 项）');
var firstShown = MJSFEAT.FEATURES[MJSFEAT.AI_FEATURES.length];   /* 第零类之后的第一项特征 */
check(frows[0].querySelector('.feat-name').textContent === firstShown.name,
      '第 1 行特征名 = ' + frows[0].querySelector('.feat-name').textContent + '（第零类不列在这里）');
check(frows[0].querySelector('.feat-value').textContent === FAKE_FEATS[firstShown.key],
      '第 1 行取值 = ' + frows[0].querySelector('.feat-value').textContent);
check(byId.featPanelList.textContent.indexOf('NAGA-平衡 分析') < 0
      && byId.featPanelList.textContent.indexOf('Mortal-4.1-') < 0,
      '面板里不出现任何第零类特征名（用户 m05937 ②）');
check(byId.featPanelList.textContent.indexOf('等待鸣牌') < 0,
      '面板里不出现第三类特征名（改由面板底部的局面文字体现，用户 m07289）');
var usedRows = byId.featPanelList.querySelectorAll('.feat-row.used');
check(usedRows.length === 2, '高亮 ' + usedRows.length + ' 行 = 当前检索用到的特征数');
check(usedRows.length === 2 && usedRows[0].getAttribute('data-key') === 'junme'
      && usedRows[1].getAttribute('data-key') === 'damaten_tsumo_score',
      '高亮行 = ' + usedRows.map(function (r4) { return r4.getAttribute('data-key'); }).join(','));
check(byId.featPanelInfo.textContent.indexOf('本場') >= 0, '面板标题带当前帧特征串：' + byId.featPanelInfo.textContent);
check(byId.featPanelList.textContent.indexOf('共 ') < 0
      && byId.featPanelList.textContent.indexOf('不在此列出') < 0,
      '面板底部不再有「共 N 个特征…」说明文字（用户 m07289：改成大号居中的局面文字）');
var _modeTxt = byId.featPanelMode ? byId.featPanelMode.textContent : '(没有 #featPanelMode)';
check(_modeTxt === '出牌局面' || _modeTxt === '鸣牌响应局面',
      '面板底部局面文字 = ' + _modeTxt + '（第三类特征的展示方式，用户 m07289）');
check(_modeTxt === '鸣牌响应局面', '假行「等待鸣牌」= 是 ⇒ 局面文字 = 鸣牌响应局面（用户 m07289）');

/* (4) 手动播放（非条目模式）走 /api/frame-feats */
FAKE.frameFeats = FAKE_FEATS;
App.itemIndex = -1;
App.setRound(RC0.round_index, RC0.frame_index);
var freq = null;
for (var fi2 = reqs.length - 1; fi2 >= 0; fi2--) { if (reqs[fi2].url.indexOf('/api/frame-feats') === 0) { freq = reqs[fi2]; break; } }
check(!!freq && freq.body.frame_index === RC0.frame_index && freq.body.seat === RC0.seat
      && freq.body.db === 'data/db/paipu.sqlite',
      '手动播放走 /api/frame-feats：' + JSON.stringify(freq ? freq.body : null));
check(byId.featPanelList.querySelectorAll('.feat-row').length === 34, '手动播放时面板同样 34 行');

/* (4b) m03580：版本号 / 扩充现有数据库 / --full 说明 */
check(byId.anTool === undefined, '打点工具选择已删除（m03580）');
App.loadMeta();   /* init() 时假服务还没装好，这里显式重拉一次 /api/features */
check(App.version === '1.4.3', 'App.version = ' + App.version);
check(App.version === '1.4.3' && byId.appVer.textContent === 'v1.4.3',
      '标题栏显示版本号：' + byId.appVer.textContent);
check(byId.anFullNote.textContent.indexOf('勾选') >= 0 && byId.anFullNote.textContent.length > 20,
      '--full 说明来自 /api/features：' + byId.anFullNote.textContent.slice(0, 24) + '…');
App.fillExtendSelect([
  { name: 'paipu', size: 400000, app_version: '0.2.0', compatible: true, meta: { record_count: '2679' } },
  { name: 'old', size: 1000, app_version: '0.0.9', compatible: false, meta: { record_count: '10' } }
]);
check(byId.anExtendDb.childNodes.length === 2, '扩充下拉 ' + byId.anExtendDb.childNodes.length + ' 个库');
check(byId.anExtendDb.childNodes[0].textContent.indexOf('v0.2.0') >= 0
      && byId.anExtendDb.childNodes[1].textContent.indexOf('版本不兼容') >= 0,
      '扩充下拉显示版本 / 不匹配标记：' + byId.anExtendDb.childNodes[1].textContent);
App.anSetMode('extend');
check(App.analyzeState.mode === 'extend' && !byId.anExtendRow.classList.contains('hidden')
      && byId.anDbName.disabled === true, '扩充模式：显示下拉、禁用数据库名输入（互斥）');
var tgt = App.anTargetDb();
check(tgt.extend === true && tgt.db_name === 'paipu', '扩充模式提交目标：' + JSON.stringify(tgt));
byId.btnAnalyze.fire('click');
var ereq = null;
for (var ei = 0; ei < reqs.length; ei++) { if (reqs[ei].url === '/api/analyze') { ereq = reqs[ei]; } }
check(!!ereq && ereq.body.extend === true && ereq.body.db_name === 'paipu' && ereq.body.tool === undefined,
      '扩充提交带 extend、不带 tool：' + JSON.stringify(ereq ? ereq.body : null));
check(byId.anMsg.textContent.indexOf('扩充') >= 0, '扩充结果提示：' + byId.anMsg.textContent);
App.anSetMode('new');
check(App.analyzeState.mode === 'new' && byId.anExtendRow.classList.contains('hidden')
      && byId.anDbName.disabled === false, '新建模式：隐藏下拉、数据库名可用');
check(App.anTargetDb().extend === false, '新建模式提交目标不带 extend');

/* (5) 分析进度条 */
FAKE.anProgress = { running: true, files_total: 2, files_done: 1, current: f.replace(/\.xml$/, ''),
                    rounds_total: 10, rounds_done: 3, records: 120, elapsed_ms: 1500, stage: '打点' };
App.anProgressStart();
App.anProgressTick();
check(byId.anProgressText.textContent.indexOf('已完成 1 / 2 个牌谱') >= 0, '进度文本：' + byId.anProgressText.textContent);
check(byId.anProgressText.textContent.indexOf('当前 ' + f.replace(/\.xml$/, '')) >= 0, '进度显示当前牌谱特征码');
check(byId.anProgressText.textContent.indexOf('阶段') < 0
      && byId.anProgressText.textContent.indexOf('打点') < 0,
      '进度文本不再显示「阶段」与「打点 N 行」（m03580）：' + byId.anProgressText.textContent);
var preq = null;
for (var pi2 = reqs.length - 1; pi2 >= 0; pi2--) { if (reqs[pi2].url.indexOf('/api/analyze-progress') === 0) { preq = reqs[pi2]; break; } }
check(!!preq, '进度条轮询 /api/analyze-progress');
App.anProgressDone(true, '分析完成：2 个牌谱 ｜ 1.5 s');
check(byId.anProgressText.textContent.indexOf('分析完成') >= 0, '分析结束文本：' + byId.anProgressText.textContent);

/* (6) 牌谱下载 */
byId.btnGoDownload.fire('click');
check(App.view === 'download' && !byId['view-download'].classList.contains('hidden'), '进入牌谱下载视图');
App.dlFillDefaultDir();
check(/^\d{8}-\d{6}$/.test(byId.dlSubdir.value), '默认存储目录 = ' + byId.dlSubdir.value + '（data/paipu/<时间戳>）');
App.dlSetMode('file');
check(byId.dlUrlRow.classList.contains('hidden') && !byId.dlFileRow.classList.contains('hidden'), '切到「文本文件」模式');
App.dlSetMode('url');
check(!byId.dlUrlRow.classList.contains('hidden') && byId.dlFileRow.classList.contains('hidden'), '切回「单个 URL」模式');
byId.btnDownload.fire('click');
check(byId.dlMsg.textContent.indexOf('请先输入一个牌谱 URL') >= 0, '空 URL 被拦下：' + byId.dlMsg.textContent);
byId.dlUrl.value = 'http://tenhou.net/0/?log=2026082919gm-00a9-0000-4e40cd3e&tw=0';
FAKE.dlProgress = { running: false, done: true, total: 2, done_n: 2, saved: 2, failed: 0,
                    dir: 'data/paipu/' + byId.dlSubdir.value, elapsed_ms: 800 };
byId.btnDownload.fire('click');
var dlreq = null;
for (var li2 = reqs.length - 1; li2 >= 0; li2--) {
  if (reqs[li2].url === '/api/download') { dlreq = reqs[li2]; break; }
}
check(!!dlreq && dlreq.body.subdir === byId.dlSubdir.value && dlreq.body.url.indexOf('2026082919gm') >= 0,
      '下载请求 = ' + JSON.stringify(dlreq ? dlreq.body : null));
check(byId.dlCounts.textContent.indexOf('待下载 2 个') >= 0, '展示待下载数量：' + byId.dlCounts.textContent);
check(byId.dlMsg.textContent.indexOf('下载完成：成功 2 / 2') >= 0, '下载完成提示：' + byId.dlMsg.textContent);
check(byId.dlCounts.textContent.indexOf('成功 2') >= 0 && byId.dlCounts.textContent.indexOf('失败 0') >= 0,
      '展示下载成功数量：' + byId.dlCounts.textContent);
check(byId.dlList.textContent.indexOf('data/paipu/' + byId.dlSubdir.value) >= 0, '下载目录列表：' + byId.dlList.textContent);
var pickReq = null;
for (var pi = reqs.length - 1; pi >= 0; pi--) {
  if (reqs[pi].url.indexOf('/api/paipu-browse') === 0) { pickReq = reqs[pi]; break; }
}
check(byId.anSourceDir.tagName === 'SELECT' && !!pickReq
      && decodeURIComponent(pickReq.url).indexOf('data/paipu/' + byId.dlSubdir.value) >= 0,
      '分析面板的牌谱目录下拉跟随下载目录刷新：' + (pickReq ? pickReq.url : '(没有请求)'));

/* ============================================================ 15. 本地数据管理（用户 m00178 第 9 条） */
console.log('\n=== 15. 本地数据管理 ===');

/* 15.1 入口与布局：页签第五位 + 首页第五张卡片（3 x 2，最后一张独占整行） */
check(VIEWS_ATTR.length === 6 && VIEWS_ATTR[5] === 'data',
      '页签顺序 = ' + VIEWS_ATTR.join(' / ') + '（「本地数据管理」在第五位）');
var dmTabs = document.querySelectorAll('.tab'), dmDataTab = null;
for (var dt = 0; dt < dmTabs.length; dt++) {
  if (dmTabs[dt].getAttribute('data-view') === 'data') { dmDataTab = dmTabs[dt]; }
}
check(!!dmDataTab, '存在「本地数据管理」页签');
var dmCards = homeHtml.match(/class="card(?: span)?"/g) || [];
check(dmCards.length === 5 && dmCards[4] === 'class="card span"',
      '首页 5 张卡片、第 5 张独占整行：' + dmCards.join(' / '));
check(homeHtml.indexOf('牌谱检索') < homeHtml.indexOf('本地数据管理'),
      '首页卡片顺序：本地数据管理排在牌谱检索之后');
check(homeHtml.indexOf('btnGoData') >= 0 && homeHtml.indexOf('dmDirs') < 0
      && homeHtml.indexOf('dmFiles') < 0 && homeHtml.indexOf('dmMkdir') < 0,
      '首页只放「进入本地数据管理」入口，管理界面不直接暴露');
check(/\.cards > \.card\.span\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/.test(cssTxt),
      '第五张卡片跨两列（.cards > .card.span）');
check(byId['view-data'].classList.contains('hidden'), '本地数据管理视图初始隐藏');

/* 15.2 假服务：健康检查 / 扫描 / 读文件 + 数据管理接口（内存里的目录树） */
function dmJson(obj, code) {
  return syncOk({ ok: (code || 200) < 400, status: code || 200,
                  text: function () { return syncOk(JSON.stringify(obj)); } });
}
var DM_ROOT_ABS = 'C:/Users/tester/AppData/Local/tenhou-paipu-analysis';
var DM = {
  paipu: {
    '': { dirs: ['20261007-165558'], files: [{ name: f, path: f, size: 1200, mtime: '2026-10-07 16:00' }] },
    '20261007-165558': { dirs: ['sub'], files: [{ name: LOG2 + '.xml', path: '20261007-165558/' + LOG2 + '.xml', size: 900, mtime: '2026-10-07 16:01' }] },
    '20261007-165558/sub': { dirs: [], files: [] }
  },
  db: { '': { dirs: [], files: [{ name: 'paipu.sqlite', path: 'paipu.sqlite', size: 4096, mtime: '2026-10-07 16:02', sqlite: true }] } }
};
var dmReqs = [];
function dmListing(root, rel) {
  var node = DM[root][rel] || { dirs: [], files: [] };
  var dirs = node.dirs.map(function (d) {
    var k = rel ? rel + '/' + d : d, n = DM[root][k] || { dirs: [], files: [] };
    return { name: d, path: k, entries: n.dirs.length + n.files.length };
  });
  var all = [''];
  Object.keys(DM[root]).forEach(function (k) { if (k) { all.push(k); } });
  return { ok: true, root: root,
           roots: [{ id: 'paipu', label: '牌谱（data/paipu）' }, { id: 'db', label: '数据库（data/db）' }],
           root_dir: DM_ROOT_ABS + '/data/' + root, dir: rel,
           parent: rel ? (rel.indexOf('/') < 0 ? '' : rel.slice(0, rel.lastIndexOf('/'))) : null,
           dirs: dirs, files: node.files.slice(), all_dirs: all.sort() };
}
function dmLast(prefix) {
  for (var i = dmReqs.length - 1; i >= 0; i--) { if (dmReqs[i].url.indexOf(prefix) === 0) { return dmReqs[i]; } }
  return null;
}
function dmStub(url, opt) {
  var path = String(url).replace(/^https?:\/\/[^/]+/, '');
  var body = (opt && opt.body) ? JSON.parse(opt.body) : null;
  dmReqs.push({ url: path, method: (opt && opt.method) || 'GET', body: body });
  function qv(k) { var m = new RegExp('[?&]' + k + '=([^&]*)').exec(path); return m ? decodeURIComponent(m[1]) : ''; }
  if (path.indexOf('/api/health') === 0) {
    return dmJson({ ok: true, name: '天凤牌谱分析', version: '0.2.0', root: 'C:/app',
                    data_root: DM_ROOT_ABS, db_dir: DM_ROOT_ABS + '/data/db',
                    paipu_dir: DM_ROOT_ABS + '/data/paipu' });
  }
  if (path.indexOf('/api/scan') === 0) {
    return dmJson({ ok: true, dir: qv('dir'), count: 2,
                    files: [DM_ROOT_ABS + '/data/paipu/' + f, CORPUS[1]] });
  }
  if (path.indexOf('/api/read') === 0) {
    var p = qv('path'), id = p.split('/').pop().replace(/\.xml$/, '');
    return dmJson({ ok: true, path: p, text: fs.readFileSync(xmlPath(id), 'utf8') });
  }
  if (path.indexOf('/api/fs-list') === 0) { return dmJson(dmListing(qv('root') || 'paipu', qv('rel'))); }
  if (path.indexOf('/api/fs-mkdir') === 0) {
    var r0 = body.root, rel0 = body.rel || '', key0 = rel0 ? rel0 + '/' + body.name : body.name;
    if (!body.name) { return dmJson({ ok: false, error: '目录名不能为空' }, 400); }
    if (DM[r0][key0]) { return dmJson({ ok: false, error: '已存在同名目录：' + key0 }, 400); }
    DM[r0][key0] = { dirs: [], files: [] };
    DM[r0][rel0].dirs.push(body.name);
    return dmJson({ ok: true, root: r0, dir: key0, created: body.name });
  }
  if (path.indexOf('/api/fs-move') === 0) {
    var r1 = body.root, rel1 = body.rel, dest = body.dest || '';
    if (dest === rel1) { return dmJson({ ok: false, error: '目标目录和原位置相同' }, 400); }
    if (dest.indexOf(rel1 + '/') === 0) { return dmJson({ ok: false, error: '不能把目录移动到它自己的子目录里：' + rel1 }, 400); }
    var par = rel1.indexOf('/') < 0 ? '' : rel1.slice(0, rel1.lastIndexOf('/'));
    var nm = rel1.split('/').pop(), isDir = !!DM[r1][rel1];
    if (isDir) {
      var pi = DM[r1][par].dirs.indexOf(nm);
      if (pi >= 0) { DM[r1][par].dirs.splice(pi, 1); }
      Object.keys(DM[r1]).filter(function (k) { return k === rel1 || k.indexOf(rel1 + '/') === 0; })
        .forEach(function (k) {
          var nk = (dest ? dest + '/' : '') + nm + k.slice(rel1.length);
          DM[r1][nk] = DM[r1][k]; delete DM[r1][k];
        });
      DM[r1][dest || ''].dirs.push(nm);
    } else {
      DM[r1][par].files = DM[r1][par].files.filter(function (x) { return x.name !== nm; });
      DM[r1][dest || ''].files.push({ name: nm, path: (dest ? dest + '/' : '') + nm, size: 900, mtime: '2026-10-07 16:01' });
    }
    return dmJson({ ok: true, root: r1, moved: rel1, to: (dest ? dest + '/' : '') + nm });
  }
  if (path.indexOf('/api/fs-delete') === 0) {
    var r2 = body.root, rel2 = body.rel;
    if (DM[r2][rel2]) { return dmJson({ ok: false, error: '「' + rel2 + '」是目录，请用「删除子目录」。' }, 400); }
    var par2 = rel2.indexOf('/') < 0 ? '' : rel2.slice(0, rel2.lastIndexOf('/'));
    DM[r2][par2].files = DM[r2][par2].files.filter(function (x) { return x.name !== rel2.split('/').pop(); });
    return dmJson({ ok: true, root: r2, deleted: rel2 });
  }
  if (path.indexOf('/api/fs-rmdir') === 0) {
    var r3 = body.root, rel3 = body.rel;
    if (!rel3) { return dmJson({ ok: false, error: '不能删除数据根目录' }, 400); }
    if (!DM[r3][rel3]) { return dmJson({ ok: false, error: '目录不存在：' + rel3 }, 400); }
    var par3 = rel3.indexOf('/') < 0 ? '' : rel3.slice(0, rel3.lastIndexOf('/'));
    var i3 = DM[r3][par3].dirs.indexOf(rel3.split('/').pop());
    if (i3 >= 0) { DM[r3][par3].dirs.splice(i3, 1); }
    var n3 = 0;
    Object.keys(DM[r3]).forEach(function (k) {
      if (k === rel3 || k.indexOf(rel3 + '/') === 0) { n3 += DM[r3][k].files.length; delete DM[r3][k]; }
    });
    return dmJson({ ok: true, root: r3, deleted: rel3, files: n3 });
  }
  return dmJson({ ok: false, error: '未知接口 ' + path }, 404);
}
var dmPrevFetch = global.fetch;
global.fetch = dmStub;

/* 15.3 进入视图 + 列目录 */
byId.btnGoData.fire('click', { target: byId.btnGoData });
check(App.view === 'data' && !byId['view-data'].classList.contains('hidden'),
      '点首页「进入本地数据管理」切到该视图');
var dml = dmLast('/api/fs-list');
check(!!dml && dml.url === '/api/fs-list?root=paipu&rel=',
      '进入时按「牌谱区 + 数据根」列目录：' + (dml ? dml.url : '（没有请求）'));
check(byId.dmAbs.textContent.indexOf('/data/paipu') > 0, '显示数据目录绝对路径：' + byId.dmAbs.textContent);
check(byId.dmPath.textContent === '/', '当前位置显示为「/」：' + byId.dmPath.textContent);
check(byId.dmDirs.textContent.indexOf('20261007-165558') > 0, '目录列表：' + byId.dmDirs.textContent);
check(byId.dmFiles.textContent.indexOf('.xml') > 0, '文件列表：' + byId.dmFiles.textContent);

/* 15.4 进入子目录（点行尾的「进入」） */
var dmDirRow = byId.dmDirs.childNodes[0];
check(dmDirRow.getAttribute('data-kind') === 'dir' && dmDirRow.textContent.indexOf('（2 项）') > 0,
      '目录行带条目数：' + dmDirRow.textContent);
var dmGo = dmDirRow.childNodes[2];
check(dmGo.getAttribute('data-act') === 'enter', '目录行有「进入」按钮');
dmGo.fire('click', { target: dmGo });
check(App.dataManagerState.rel === '20261007-165558', '进入子目录：' + App.dataManagerState.rel);
var dml2 = dmLast('/api/fs-list');
check(!!dml2 && dml2.url === '/api/fs-list?root=paipu&rel=20261007-165558',
      '列子目录请求：' + (dml2 ? dml2.url : ''));
check(byId.dmPath.textContent === '/20261007-165558', '当前位置：' + byId.dmPath.textContent);
check(byId.dmFiles.childNodes[0].textContent.indexOf(LOG2) > 0, '子目录里的文件：' + byId.dmFiles.textContent);

/* 15.5 选中文件 → 移动到上一级（数据根） */
var dmFileRow = byId.dmFiles.childNodes[0];
dmFileRow.fire('click', { target: dmFileRow });
check(App.dataManagerState.sel && App.dataManagerState.sel.path === '20261007-165558/' + LOG2 + '.xml',
      '选中文件：' + JSON.stringify(App.dataManagerState.sel));
check(byId.dmSelInfo.textContent.indexOf('已选中文件') === 0, '选中提示：' + byId.dmSelInfo.textContent);
byId.dmDest.value = '';
byId.dmMove.fire('click', { target: byId.dmMove });
var dmm = dmLast('/api/fs-move');
check(!!dmm && dmm.method === 'POST' && dmm.body.root === 'paipu'
      && dmm.body.rel === '20261007-165558/' + LOG2 + '.xml' && dmm.body.dest === '',
      '移动到上级（数据根）请求：' + JSON.stringify(dmm ? dmm.body : null));
check(byId.dmMsg.textContent.indexOf('已移动到') === 0, '移动成功提示：' + byId.dmMsg.textContent);
check(byId.dmFiles.textContent.indexOf('没有文件') > 0, '移动后该目录已无文件：' + byId.dmFiles.textContent);

/* 15.6 新建目录 + 重名被拒 */
byId.dmNewName.value = 'newdir';
byId.dmMkdir.fire('click', { target: byId.dmMkdir });
var dmk = dmLast('/api/fs-mkdir');
check(!!dmk && dmk.body.root === 'paipu' && dmk.body.rel === '20261007-165558' && dmk.body.name === 'newdir',
      '新建目录请求：' + JSON.stringify(dmk ? dmk.body : null));
check(byId.dmNewName.value === '', '新建成功后清空输入框');
check(byId.dmMsg.textContent.indexOf('已新建目录') === 0, '新建成功提示：' + byId.dmMsg.textContent);
check(byId.dmDirs.textContent.indexOf('newdir') > 0, '目录列表出现新目录：' + byId.dmDirs.textContent);
byId.dmNewName.value = 'newdir';
byId.dmMkdir.fire('click', { target: byId.dmMkdir });
check(byId.dmMsg.textContent.indexOf('新建目录失败') === 0 && byId.dmMsg.textContent.indexOf('已存在同名目录') > 0,
      '重名被服务端拒绝并提示：' + byId.dmMsg.textContent);

/* 15.7 「上一级」回到数据根；选中目录时「删除文件」被拦下 */
byId.dmUp.fire('click', { target: byId.dmUp });
check(App.dataManagerState.rel === '' && byId.dmPath.textContent === '/', '「上一级」回到数据根');
byId.dmUp.fire('click', { target: byId.dmUp });
check(byId.dmMsg.textContent.indexOf('已经在数据根目录了') === 0, '数据根再点「上一级」给出提示：' + byId.dmMsg.textContent);
var dmDirRow2 = byId.dmDirs.childNodes[0];
dmDirRow2.fire('click', { target: dmDirRow2 });
check(App.dataManagerState.sel && App.dataManagerState.sel.kind === 'dir',
      '选中目录：' + JSON.stringify(App.dataManagerState.sel));
byId.dmDelete.fire('click', { target: byId.dmDelete });
check(byId.dmMsg.textContent.indexOf('请用「删除选中子目录」') > 0,
      '选中的是目录时「删除文件」被拦下：' + byId.dmMsg.textContent);

/* 15.8 把目录移进它自己的子目录 → 服务端 400 */
byId.dmDest.value = '20261007-165558/sub';
byId.dmMove.fire('click', { target: byId.dmMove });
check(byId.dmMsg.textContent.indexOf('移动失败') === 0
      && byId.dmMsg.textContent.indexOf('不能把目录移动到它自己的子目录里') > 0,
      '移进自己的子目录被拒：' + byId.dmMsg.textContent);

/* 15.9 删除子目录（连同子目录内容） */
byId.dmRmdir.fire('click', { target: byId.dmRmdir });
var dmr = dmLast('/api/fs-rmdir');
check(!!dmr && dmr.method === 'POST' && dmr.body.root === 'paipu' && dmr.body.rel === '20261007-165558',
      '删除子目录请求：' + JSON.stringify(dmr ? dmr.body : null));
check(byId.dmMsg.textContent.indexOf('已删除子目录') === 0, '删除成功提示：' + byId.dmMsg.textContent);
check(byId.dmDirs.textContent.indexOf('20261007-165558') < 0 && byId.dmDirs.textContent.indexOf('没有子目录') > 0,
      '删除后目录列表清空：' + byId.dmDirs.textContent);
check(byId.dmFiles.textContent.indexOf(f) > 0, '数据根仍保留原有文件：' + byId.dmFiles.textContent);

/* 15.10 切到数据库区：绝对路径 / 数据库标记 / 删除文件 */
byId.dmRoot.value = 'db';
byId.dmRoot.fire('change', { target: byId.dmRoot });
var dml3 = dmLast('/api/fs-list');
check(!!dml3 && dml3.url === '/api/fs-list?root=db&rel=', '切到数据库区后重新列目录：' + (dml3 ? dml3.url : ''));
check(byId.dmAbs.textContent.indexOf('/data/db') > 0, '显示数据库目录绝对路径：' + byId.dmAbs.textContent);
var dmDbRow = byId.dmFiles.childNodes[0];
check(dmDbRow.textContent.indexOf('paipu.sqlite') > 0 && dmDbRow.textContent.indexOf('数据库') > 0,
      '数据库文件行带「数据库」标记：' + dmDbRow.textContent);
dmDbRow.fire('click', { target: dmDbRow });
byId.dmDelete.fire('click', { target: byId.dmDelete });
var dmd = dmLast('/api/fs-delete');
check(!!dmd && dmd.method === 'POST' && dmd.body.root === 'db' && dmd.body.rel === 'paipu.sqlite',
      '删除数据库文件请求：' + JSON.stringify(dmd ? dmd.body : null));
check(byId.dmFiles.textContent.indexOf('没有文件') > 0, '删除后文件列表清空：' + byId.dmFiles.textContent);

/* 15.11 用户 m03175 ④⑤：按特征码搜索 —— 清单来自 /api/scan?kind=all，规则 = 连续子串完全匹配 */
App.loadHealth();
check(App.paipuDir === DM_ROOT_ABS + '/data/paipu', '从 /api/health 拿到牌谱目录：' + App.paipuDir);
byId.rpModeSearch.checked = true;
byId.rpModeSearch.fire('change', { target: byId.rpModeSearch });
check(byId.btnPickFile.disabled === true && byId.codeInput.disabled === false,
      '切到「按特征码搜索」后「浏览选择…」禁用、输入框可用（两种方式互斥）');
var codeReq = dmLast('/api/scan');
check(!!codeReq && codeReq.url === '/api/scan?dir=' + encodeURIComponent(DM_ROOT_ABS + '/data/paipu') + '&kind=all',
      '搜索清单来自 /api/scan?kind=all：' + (codeReq ? codeReq.url : ''));
check(App.codeIndex.length === 2, '牌谱清单 ' + App.codeIndex.length + ' 项');
byId.codeInput.value = '2026083020gm';
byId.codeInput.fire('input', { target: byId.codeInput });
var codeRows = byId.codeResults.querySelectorAll('.code-row');
check(codeRows.length === 1 && codeRows[0].textContent === f,
      '连续子串匹配到 1 条：' + byId.codeResults.textContent);
check(codeRows[0].querySelectorAll('.code-hit').length === 1
      && codeRows[0].querySelector('.code-hit').textContent === '2026083020gm',
      '匹配到的子串用 .code-hit 标出（用户 m03319）');
byId.codeInput.value = '00a9';
byId.codeInput.fire('input', { target: byId.codeInput });
var hiRow = byId.codeResults.querySelector('.code-row');
check(!!hiRow && hiRow.querySelectorAll('.code-hit').length === 1
      && hiRow.querySelector('.code-hit').textContent === '00a9'
      && hiRow.textContent === f,
      '匹配位于文件名中间时也高亮（整行文本不变）：' + (hiRow ? hiRow.textContent : ''));
byId.codeInput.value = '2026083020gm';
byId.codeInput.fire('input', { target: byId.codeInput });
byId.codeInput.value = 'zzzz';
byId.codeInput.fire('input', { target: byId.codeInput });
check(byId.codeResults.querySelectorAll('.code-row').length === 0
      && byId.codeResults.textContent.indexOf('没有找到') >= 0,
      '没有匹配时给出可读提示：' + byId.codeResults.textContent);
byId.codeInput.value = '2026083020gm';
byId.codeInput.fire('input', { target: byId.codeInput });
codeRows = byId.codeResults.querySelectorAll('.code-row');
codeRows[0].fire('click', { target: codeRows[0] });
var dmr2 = dmLast('/api/read');
check(!!dmr2 && dmr2.url === '/api/read?path=' + encodeURIComponent(DM_ROOT_ABS + '/data/paipu/' + f),
      '点搜索结果走 /api/read 绝对路径：' + (dmr2 ? dmr2.url : ''));
check(App.rounds.length === 9 && App.view === 'replay', '点搜索结果进入正常播放视图（' + App.rounds.length + ' 局）');
check(App.itemIndex === -1 && !byId.controls.classList.contains('locked'),
      '搜索结果不是静态帧模式：控制面板可用（用户 m03175 ⑤）');
check(byId.fileInfo.textContent.indexOf(f) >= 0, '文件信息更新：' + byId.fileInfo.textContent);
byId.rpModeBrowse.checked = true;
byId.rpModeBrowse.fire('change', { target: byId.rpModeBrowse });
check(byId.btnPickFile.disabled === false && byId.codeInput.disabled === true,
      '切回「浏览选择」后按钮恢复、输入框禁用');

global.fetch = dmPrevFetch;
global.fetch = function () { return new SyncThen(new Error('down'), true); };
byId.btnScan.fire('click');
check(byId.anMsg.textContent.indexOf('连不上本地服务') >= 0, '服务没起来时给出可读提示：' + byId.anMsg.textContent);

/* ============================================================ 16. 「选择牌谱文件…」默认目录（用户 m01084） */
console.log('\n=== 16. 「选择牌谱文件…」默认目录 ===');

/* 16.1 浏览器模式（没有 Electron 桥）：照旧点隐藏的 <input type=file>，行为不变 */
var fileInputClicks = 0;
byId.fileInput.click = function () { fileInputClicks++; };
delete global.window.tenhouDesktop;
byId.btnPickFile.fire('click', { target: byId.btnPickFile });
check(fileInputClicks === 1, '浏览器模式退回 <input type=file>（点了 ' + fileInputClicks + ' 次）');

/* 16.2 桌面模式：把 /api/health 的 paipu_dir 交给主进程当对话框默认目录，选中路径走 /api/read */
var pickCalls = [];
var PICKED = DM_ROOT_ABS + '/data/paipu/' + f;
global.fetch = dmStub;
global.window.tenhouDesktop = {
  isDesktop: true,
  pickPaipuFile: function (dir) { pickCalls.push(dir); return syncOk({ canceled: false, filePath: PICKED }); }
};
App.paipuDir = '';                       /* 模拟 /api/health 还没回来 */
App.rounds = [];
byId.fileInfo.textContent = '';
byId.btnPickFile.fire('click', { target: byId.btnPickFile });
check(pickCalls.length === 1 && pickCalls[0] === DM_ROOT_ABS + '/data/paipu',
      '对话框默认目录 = /api/health 给的 paipu_dir：' + JSON.stringify(pickCalls));
check(fileInputClicks === 1, '桌面模式不再点 <input type=file>');
var pickRead = dmLast('/api/read');
check(!!pickRead && pickRead.url === '/api/read?path=' + encodeURIComponent(PICKED),
      '选中的绝对路径走 /api/read：' + (pickRead ? pickRead.url : ''));
check(App.rounds.length === 9 && App.view === 'replay', '选中的牌谱真的载入（' + App.rounds.length + ' 局）');
check(byId.fileInfo.textContent.indexOf(f) >= 0, '文件信息更新：' + byId.fileInfo.textContent);

/* 16.3 取消对话框：不动当前牌谱 */
pickCalls.length = 0;
var roundsBefore = App.rounds.length;
global.window.tenhouDesktop = {
  isDesktop: true,
  pickPaipuFile: function (dir) { pickCalls.push(dir); return syncOk({ canceled: true, filePath: '' }); }
};
byId.btnPickFile.fire('click', { target: byId.btnPickFile });
check(pickCalls.length === 1 && App.rounds.length === roundsBefore, '取消对话框后保持原牌谱不变');

/* 16.4 桌面壳静态检查：preload 暴露桥 + 主进程注册 IPC 并设 defaultPath + 打包带上 desktop/ */
var mainJs = fs.readFileSync(base + '/desktop/main.js', 'utf8');
var preloadJs = fs.readFileSync(base + '/desktop/preload.js', 'utf8');
var pkgJson = JSON.parse(fs.readFileSync(base + '/package.json', 'utf8'));
check(/preload:\s*path\.join\(__dirname,\s*'preload\.js'\)/.test(mainJs),
      '主进程给 BrowserWindow 挂了 desktop/preload.js');
check(/ipcMain\.handle\('pick-paipu-file'/.test(mainJs) && /defaultPath/.test(mainJs),
      '主进程注册 pick-paipu-file 并设置 defaultPath');
check(/exposeInMainWorld\('tenhouDesktop'/.test(preloadJs) && /pickPaipuFile/.test(preloadJs),
      'preload 通过 contextBridge 暴露 pickPaipuFile');
check((pkgJson.build.files || []).indexOf('desktop/**/*') >= 0,
      'package.json 的 build.files 含 desktop/**/*（preload.js 会进包）');

delete global.window.tenhouDesktop;
global.fetch = dmPrevFetch;

/* ============================================================ 结果 */
console.log('\n===== 结果 =====');
if (problems.length) {
  problems.slice(0, 30).forEach(function (m) { console.log('!! ' + m); });
  console.log('共 ' + problems.length + ' 个问题');
  process.exitCode = 1;
} else {
  console.log('全部通过');
}

/* 本文件里有进度轮询的 setTimeout：报告完后主动退出，避免残留定时器拖住进程 */
setTimeout(function () { process.exit(problems.length ? 1 : 0); }, 0);
