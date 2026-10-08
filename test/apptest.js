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
    else if (/\.xml$/.test(n)) { out.push(p); }
  });
  return out;
}
var CORPUS = walkXml(base + '/data', []).sort();
function xmlPath(id) {
  for (var xi = 0; xi < CORPUS.length; xi++) {
    if (CORPUS[xi].split(/[\\/]/).pop() === id + '.xml') { return CORPUS[xi]; }
  }
  throw new Error('data 下找不到 ' + id + '.xml（共 ' + CORPUS.length + ' 个牌谱）');
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
check(byId.sampleSelect.childNodes.length === 5, '示例下拉框有 ' + byId.sampleSelect.childNodes.length + ' 项（服务不可用时用固定清单兜底）');
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
check(byId.eventListBody.childNodes.length === App.rounds[0].length, '事件列表行数 ' + byId.eventListBody.childNodes.length + ' = 帧数 ' + App.rounds[0].length);
check(byId.rpDesc.textContent === '开局 · 配牌', '描述栏 = "' + byId.rpDesc.textContent + '"');
check(boardPlayer(0).querySelector('.tiles') !== null, '自家面板存在手牌区');

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
check(byId.rpDesc.textContent.indexOf('摸牌') >= 0, '描述 = "' + byId.rpDesc.textContent + '"');
clickAct('next');
clickAct('prev');
check(App.frameIndex === 1, '上一步回到 frameIndex = ' + App.frameIndex);
clickAct('prev');
check(App.frameIndex === 0, '再上一步到 0');
var bPrev = document.querySelector('#controls button[data-act="prev"]');
check(bPrev.disabled === true, '第 0 帧时「上一步」被禁用');
clickAct('prev');
check(App.frameIndex === 0, '越界不会跑到 -1');
clickAct('last');
check(App.frameIndex === App.rounds[0].length - 1, '「本局结束」跳到末帧 = ' + App.frameIndex);
check(curFrame().state.phase !== 'playing', '末帧 phase = ' + curFrame().state.phase);
var bNext = document.querySelector('#controls button[data-act="next"]');
check(bNext.disabled === true, '末帧时「下一步」被禁用');
clickAct('first');
check(App.frameIndex === 0, '「开局」回到 0');

/* ============================================================ 4. 关键事件 */
console.log('\n=== 4. 关键事件跳转 ===');
var KEY = { discard: 1, call: 1, reach: 1, dora: 1, agari: 1, ryuukyoku: 1 };
clickAct('nextKey');
var found = null;
for (var i = 1; i < App.rounds[0].length; i++) { if (KEY[App.rounds[0][i].ev.type]) { found = i; break; } }
check(App.frameIndex === found && App.rounds[0][found].ev.type === 'discard',
  '「下一关键」跳到首个出牌帧 ' + found + '（type=' + App.rounds[0][found].ev.type + '）');
var expect2 = null;
for (var q = 3; q < App.rounds[0].length; q++) { if (KEY[App.rounds[0][q].ev.type]) { expect2 = q; break; } }
clickAct('nextKey');
check(App.frameIndex === expect2, '第二次「下一关键」到下一个关键帧 ' + expect2 + ' (type=' + App.rounds[0][expect2].ev.type + ')，实际 ' + App.frameIndex);
clickAct('prevKey');
check(App.frameIndex === found, '「上一关键」回退到首个关键帧 ' + found + '（实际 ' + App.frameIndex + '）');
clickAct('first');
/* 逐个关键事件走完一整局 */
var visited = 0;
for (var z = 0; z < 200; z++) {
  var before = App.frameIndex;
  clickAct('nextKey');
  if (App.frameIndex === before) { break; }
  visited++;
  if (App.frameIndex === App.rounds[0].length - 1) { break; }
}
check(App.frameIndex === App.rounds[0].length - 1 && curFrame().state.phase !== 'playing',
  '连点「下一关键」能走到本局终局（访问了 ' + visited + ' 个关键帧，末帧 phase=' + curFrame().state.phase + '）');

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

console.log('\n=== 7c. 中央区（只留 局/余/供托/宝牌）===');
var cen = byId.board.querySelector('.cell-center');
check(cen.querySelector('.c-round') !== null, '局数框 = "' + cen.querySelector('.c-round').textContent + '"');
check(cen.querySelector('.c-left') !== null, '剩余牌数 = "' + cen.querySelector('.c-left').textContent + '"');
check(cen.querySelector('.c-kyotaku') !== null, '供托行 = "' + cen.querySelector('.c-kyotaku').textContent + '"');
check(cen.querySelector('.c-dora') !== null, '宝牌指示牌行存在（' + countTiles(cen.querySelector('.c-dora')) + ' 张）');
check(cen.querySelector('.c-scores') === null, '中央不再重复显示四家点数列表');

console.log('\n=== 7d. 牌河分行（6 张一排）===');
var maxRow = 0, rows = 0;
['top', 'left', 'right', 'bottom'].forEach(function (a) {
  var rv = byId.board.querySelector('.cell-' + a + ' .p-river');
  if (!rv) { return; }
  var rws = rv.querySelectorAll('.river-row');
  rows += rws.length;
  rws.forEach(function (r) { maxRow = Math.max(maxRow, r.querySelectorAll('.tile').length); });
});
check(rows > 0, '牌河按 .river-row 分行渲染，共 ' + rows + ' 排');
check(maxRow <= 6, '每排最多 ' + maxRow + ' 张（要求 ≤6）');
/* 走到本局末帧，牌河最长，检查分行与 4 排预留 */
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
  if (rws.length !== Math.ceil(n / 6)) { okRows = false; }
  if (per.some(function (v) { return v > 6 || v <= 0; })) { okRows = false; }
});
check(okRows && maxLen > 6, '末帧牌河分行正确（最长 ' + maxLen + ' 张）：' + detail.join('  '));
clickAct('first');

console.log('\n=== 7e. 事件列表开关 ===');
byId.chkList.checked = false;
byId.chkList.fire('change', { target: byId.chkList });
check(byId.eventList.classList.contains('off'), '取消「事件列表」后侧栏隐藏');
byId.chkList.checked = true;
byId.chkList.fire('change', { target: byId.chkList });
check(!byId.eventList.classList.contains('off'), '重新勾选后侧栏显示');

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
check(kd > 0 && KEY[App.rounds[App.roundIndex][kd].ev.type], '↓「下一关键」-> ' + kd + ' (' + App.rounds[App.roundIndex][kd].ev.type + ')');
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

/* ============================================================ 9. 自动播放 */
console.log('\n=== 9. 自动播放 ===');
clickAct('auto');
check(App.auto === true && App.timer !== null, '自动播放已启动');
check(document.querySelector('#controls button[data-act="auto"]').classList.contains('on'), '按钮高亮');
clickAct('auto');
check(App.auto === false && App.timer === null, '再次点击已停止');

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
check(rpHtml.indexOf('btnPickFile') >= 0 && rpHtml.indexOf('dropZone') >= 0 && rpHtml.indexOf('sampleSelect') >= 0
      && rpHtml.indexOf('homeMsg') >= 0, '选择文件 / 拖拽区 / 示例下拉 / 提示都搬进播放视图');
var cssTxt = fs.readFileSync(base + '/web/style.css', 'utf8');
check(homeHtml.indexOf('牌谱下载') < homeHtml.indexOf('牌谱播放')
      && homeHtml.indexOf('牌谱播放') < homeHtml.indexOf('牌谱分析')
      && homeHtml.indexOf('牌谱分析') < homeHtml.indexOf('牌谱检索'),
      '首页四张卡片顺序 = 下载 / 播放 / 分析 / 检索');
check(/\.cards\s*\{[^}]*repeat\(2,/.test(cssTxt), '首页五个入口按 2 列排布（.cards 两列网格，第五张卡跨两列）');
byId.btnGoReplay.fire('click', { target: byId.btnGoReplay });
check(App.view === 'replay' && !byId.rpOpenBar.classList.contains('hidden'),
      '点「开始播放」进入播放视图并展开「选择牌谱文件」栏');
byId.btnOpenPicker.fire('click', { target: byId.btnOpenPicker });
check(byId.rpOpenBar.classList.contains('hidden'), '「打开牌谱…」可以收起该栏');
byId.btnOpenPicker.fire('click', { target: byId.btnOpenPicker });
check(!byId.rpOpenBar.classList.contains('hidden'), '再点一次又展开');

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
var cssText = fs.readFileSync(base + '/web/style.css', 'utf8');
var boardCss = cssRule(cssText, '.board');
var riverCss = cssRule(cssText, '.p-river');
check(/var\(--tile-w\)/.test(boardCss), '牌桌轨道宽度以 --tile-w 为单位（各分辨率同一观感）');
check(boardCss.indexOf('1fr') < 0, '牌桌基础轨道不再用 1fr 拉伸（避免大屏留白）');
check(/(^|[^-])column\s*;/.test(riverCss) && !/column-reverse/.test(riverCss), '牌河第 1 排靠中央信息框（flex-direction: column）');
check(/min-height:\s*calc\(var\(--tile-h\)\s*\*\s*4/.test(riverCss), '牌河预留 4 排高度');
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
  var mnode = rot0.querySelector('.meld-' + type);
  var mt = tilesIn(mnode), mr = rotIn(mnode);
  check(mt.length === hit.m.tiles.length, type + '：副露渲染 ' + mt.length + ' 张 = 状态 ' + hit.m.tiles.length + ' 张');
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
for (var ci = 0; ci < recsCur.length; ci++) { if (recsCur[ci].kind !== 'draw') { recCall = recsCur[ci]; break; } }
var ROWCALL = recCall ? dbRow(recCall, f.replace(/\.xml$/, '')) : null;
/* 第 21 轮：假数据库行的 33 个特征值（枚举 '是' / 实数 0.5 / 整数 1） */
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
                                    app_version: '0.1.0', compatible: true }] });
  }
  if (path.indexOf('/api/features') === 0) {
    return json({ ok: true, name: '天凤牌谱分析', version: '0.1.0', schema_version: 3,
                  features: MJSFEAT.FEATURES,
                  full_note: '勾选：把每一帧的原始数据写进 frame_full 表，以后新增特征可以直接用旧牌谱重算；'
                    + '不勾选：只写 33 个特征值，数据库更小，但新增特征时必须重新分析牌谱。' });
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

/* 8.3 牌谱检索：添加特征 / 不能重复 */
byId.btnGoSearch.fire('click');
check(App.view === 'search', '进入牌谱检索视图');
check(byId.scFeatSelect.childNodes.length === MJSFEAT.FEATURES.length,
      '特征下拉 ' + byId.scFeatSelect.childNodes.length + ' 项 = 第一类特征数');
byId.btnRunQuery.fire('click');
check(byId.scMsg.textContent.indexOf('空的') >= 0, '空条件被拦下：' + byId.scMsg.textContent);
byId.scFeatSelect.value = 'junme';
byId.btnAddFeat.fire('click');
check(App.searchState.conds.length === 1 && App.searchState.conds[0].key === 'junme', '添加「巡目」条件');
check(byId.scCondList.querySelectorAll('.cond-row').length === 1, '条件列表 1 行');
check(byId.scFeatSelect.childNodes.length === MJSFEAT.FEATURES.length - 1, '已添加的特征不再出现在下拉里');
byId.btnRunQuery.fire('click');
check(byId.scMsg.textContent.indexOf('还没填写') >= 0, '没填条件被拦下：' + byId.scMsg.textContent);

/* 8.4 检索 -> 结果条目 -> 跳帧 */
var inp = byId.scCondList.querySelector('.cond-input');
inp.value = '3';
inp.fire('input');
byId.btnRunQuery.fire('click');
var qreq = reqs[reqs.length - 1];
check(qreq.url === '/api/query' && qreq.body.conds[0].expr === '3', '检索条件 = ' + JSON.stringify(qreq.body.conds));
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
check(App.fileName === LOG2 + '.xml', '已切换到 ' + App.fileName);
byId.btnNextItem.fire('click');
check(App.itemIndex === 1 && byId.btnNextItem.disabled === true, '最后一条目时「下一条目」禁用');
byId.btnPrevItem.fire('click');
check(App.itemIndex === 0, '「上一条目」回到第 1 条');
check(App.fileName === f, '回退时切回前一个牌谱 ' + App.fileName);
check(App.roundIndex === ROW0.round_index, '回退后回到前一个牌谱的帧');

/* 8.6 全部浏览 */
byId.btnBrowseAll.fire('click');
var breq = reqs[reqs.length - 1];
check(breq.url === '/api/browse' && breq.body.limit === 0, '「全部浏览」请求 limit=0（不限行数）');
check(App.itemSource === 'browse' && App.items.length === 2, '浏览条目 ' + App.items.length + ' 个');
byId.scResultList.childNodes[0].fire('click');
check(byId.itemInfo.textContent.indexOf('全部浏览') >= 0, '条目导航标注来源：' + byId.itemInfo.textContent);

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

/* (1) 33 个特征都在下拉里（16 第一类 + 17 第二类） */
byId.btnClearConds.fire('click');
check(MJSFEAT.FEATURES.length === 33, '前端特征注册表 ' + MJSFEAT.FEATURES.length + ' 项 = 33（16 第一类 + 17 第二类）');
check(byId.scFeatSelect.childNodes.length === 33, '特征下拉 ' + byId.scFeatSelect.childNodes.length + ' 项');
var fkeys = MJSFEAT.FEATURES.map(function (f5) { return f5.key; });
check(fkeys.indexOf('shanten_mentsu') >= 0 && fkeys.indexOf('damaten_tsumo_score') >= 0
      && fkeys.indexOf('riichi_others_danger_suji') >= 0 && fkeys.indexOf('riichi_others_danger_ryanmen') >= 0,
      '第二类特征已注册：面子手向听 / 默听自摸期望打点 / 危险筋组 / 危险两面组');

/* (2) 实数特征走文本框 + 小数条件提示 */
byId.scFeatSelect.value = 'junme';
byId.btnAddFeat.fire('click');
byId.scFeatSelect.value = 'damaten_tsumo_score';
byId.btnAddFeat.fire('click');
var finps = byId.scCondList.querySelectorAll('.cond-input');
check(finps.length === 2, '两个文本框条件：' + finps.length + ' 行（巡目 / 实数特征）');
check(!!finps[1] && finps[1].placeholder.indexOf('实数') >= 0, '实数特征提示：' + (finps[1] ? finps[1].placeholder : '无'));
check(byId.scCondList.textContent.indexOf('默听自摸期望打点') >= 0, '实数特征行名 = 默听自摸期望打点');

/* (3) 帧特征面板：条目模式走 /api/detail，33 行 + 检索用到的特征高亮 */
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
check(frows.length === 33, '帧特征面板 ' + frows.length + ' 行 = 33 个特征');
check(frows[0].querySelector('.feat-name').textContent === MJSFEAT.FEATURES[0].name,
      '第 1 行特征名 = ' + frows[0].querySelector('.feat-name').textContent);
check(frows[0].querySelector('.feat-value').textContent === FAKE_FEATS[MJSFEAT.FEATURES[0].key],
      '第 1 行取值 = ' + frows[0].querySelector('.feat-value').textContent);
var usedRows = byId.featPanelList.querySelectorAll('.feat-row.used');
check(usedRows.length === 2, '高亮 ' + usedRows.length + ' 行 = 当前检索用到的特征数');
check(usedRows.length === 2 && usedRows[0].getAttribute('data-key') === 'junme'
      && usedRows[1].getAttribute('data-key') === 'damaten_tsumo_score',
      '高亮行 = ' + usedRows.map(function (r4) { return r4.getAttribute('data-key'); }).join(','));
check(byId.featPanelInfo.textContent.indexOf('本場') >= 0, '面板标题带当前帧特征串：' + byId.featPanelInfo.textContent);
check(byId.featPanelList.textContent.indexOf('共 33 个特征') >= 0, '面板尾部统计行');

/* (4) 手动播放（非条目模式）走 /api/frame-feats */
FAKE.frameFeats = FAKE_FEATS;
App.itemIndex = -1;
App.setRound(RC0.round_index, RC0.frame_index);
var freq = null;
for (var fi2 = reqs.length - 1; fi2 >= 0; fi2--) { if (reqs[fi2].url.indexOf('/api/frame-feats') === 0) { freq = reqs[fi2]; break; } }
check(!!freq && freq.body.frame_index === RC0.frame_index && freq.body.seat === RC0.seat
      && freq.body.db === 'data/db/paipu.sqlite',
      '手动播放走 /api/frame-feats：' + JSON.stringify(freq ? freq.body : null));
check(byId.featPanelList.querySelectorAll('.feat-row').length === 33, '手动播放时面板同样 33 行');

/* (4b) m03580：版本号 / 扩充现有数据库 / --full 说明 */
check(byId.anTool === undefined, '打点工具选择已删除（m03580）');
App.loadMeta();   /* init() 时假服务还没装好，这里显式重拉一次 /api/features */
check(App.version === '0.1.0', 'App.version = ' + App.version);
check(App.version === '0.1.0' && byId.appVer.textContent === 'v0.1.0',
      '标题栏显示版本号：' + byId.appVer.textContent);
check(byId.anFullNote.textContent.indexOf('勾选') >= 0 && byId.anFullNote.textContent.length > 20,
      '--full 说明来自 /api/features：' + byId.anFullNote.textContent.slice(0, 24) + '…');
App.fillExtendSelect([
  { name: 'paipu', size: 400000, app_version: '0.1.0', compatible: true, meta: { record_count: '2679' } },
  { name: 'old', size: 1000, app_version: '0.0.9', compatible: false, meta: { record_count: '10' } }
]);
check(byId.anExtendDb.childNodes.length === 2, '扩充下拉 ' + byId.anExtendDb.childNodes.length + ' 个库');
check(byId.anExtendDb.childNodes[0].textContent.indexOf('v0.1.0') >= 0
      && byId.anExtendDb.childNodes[1].textContent.indexOf('版本不匹配') >= 0,
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
check(byId.anSourceDir.value === 'data/paipu/' + byId.dlSubdir.value,
      '分析面板的牌谱目录预填为下载目录：' + byId.anSourceDir.value);

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
    return dmJson({ ok: true, name: '天凤牌谱分析', version: '0.1.0', root: 'C:/app',
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

/* 15.11 用户 m00178 第 8 条：示例牌谱改走 /api/health + /api/scan + /api/read 的绝对路径 */
App.samples = [];
App.loadSamples();
check(App.paipuDir === DM_ROOT_ABS + '/data/paipu', '从 /api/health 拿到牌谱目录：' + App.paipuDir);
check(App.samples.length === 2 && App.samples.indexOf(DM_ROOT_ABS + '/data/paipu/' + f) >= 0,
      '示例清单改成绝对路径：' + JSON.stringify(App.samples));
check(byId.sampleSelect.childNodes.length === 2, '示例下拉框 ' + byId.sampleSelect.childNodes.length + ' 项');
var dmSelVals = [];
for (var oi = 0; oi < byId.sampleSelect.childNodes.length; oi++) { dmSelVals.push(byId.sampleSelect.childNodes[oi].value); }
check(dmSelVals.indexOf(DM_ROOT_ABS + '/data/paipu/' + f) >= 0,
      '下拉项 value = 服务端给的绝对路径：' + JSON.stringify(dmSelVals));
var dmRelVals = dmSelVals.filter(function (v) { return !/^[A-Za-z]:[\\/]|^\//.test(v); });
check(dmRelVals.length === 0, '下拉项里没有相对路径（旧 bug 就是裸文件名）：' + JSON.stringify(dmRelVals));
byId.sampleSelect.value = DM_ROOT_ABS + '/data/paipu/' + f;
byId.btnLoadSample.fire('click', { target: byId.btnLoadSample });
var dmr2 = dmLast('/api/read');
check(!!dmr2 && dmr2.url === '/api/read?path=' + encodeURIComponent(DM_ROOT_ABS + '/data/paipu/' + f),
      '载入示例改走 /api/read 绝对路径：' + (dmr2 ? dmr2.url : ''));
check(App.rounds.length === 9 && App.view === 'replay', '示例牌谱真的载入成功（' + App.rounds.length + ' 局）');
check(byId.fileInfo.textContent.indexOf(f) >= 0, '文件信息更新：' + byId.fileInfo.textContent);

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
