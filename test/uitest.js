/* uitest.js — 无浏览器环境下验证 ui.js 的渲染逻辑
 *
 * 用一个极简的假 DOM 跑 ui.js 的 renderBoard / renderEventList，
 * 检查：① 渲染不抛异常；② 生成的 <img src> 全部指向真实存在的素材文件；
 * ③ 渲染出的牌数量与状态一致。
 */
'use strict';
var fs = require('fs');
var path = require('path');
var base = 'D:/coding/dsh_workspace/simple/tenhou-paipu-analysis';

/* 牌谱可能放在 data/ 的子目录里（如 data/paipu/<时间戳>/xxx.xml），递归找。
   返回相对于 root 的路径。 */
function walkXml(root, out, baseRoot) {
  var base = baseRoot || root;      /* 路径一律相对最初的 root，别用当前递归层 */
  var ents;
  try { ents = fs.readdirSync(root, { withFileTypes: true }); } catch (e) { return out; }
  ents.forEach(function (e) {
    var p = path.join(root, e.name);
    if (e.isDirectory()) { walkXml(p, out, base); }
    else if (/\.xml$/i.test(e.name)) { out.push(path.relative(base, p)); }
  });
  return out.sort();
}

/* 默认跑这 5 个基础牌谱（按特征码挑选，与存放目录无关）。 */
var BASE_IDS = ['2026082919gm-00a9-0000-4e40cd3e', '2026082920gm-00a9-0000-5db954e6',
                '2026082921gm-00a9-0000-d2e544e6', '2026083020gm-00a9-0000-e9ce1efe',
                '2026083021gm-00a9-0000-d0810acf'];

function pickBase(all) {
  var pick = [];
  BASE_IDS.forEach(function (id) {
    var hit = all.filter(function (p) { return path.basename(p) === id + '.xml'; })[0];
    if (hit) { pick.push(hit); }
  });
  return pick.length ? pick : all;
}

/* ------------------------------------------------------------- 假 DOM */
var ALL_CLASSES = {};

function El(tag) {
  this.tagName = String(tag).toUpperCase();
  this.childNodes = [];
  this._cls = [];
  this.attrs = {};
  this._text = '';
  this.src = '';
  /* 供 renderEventList 使用 */
  this.scrollTop = 0;
  this.offsetTop = 0;
  this.offsetHeight = 20;
  this.clientHeight = 1000;
}
Object.defineProperty(El.prototype, 'className', {
  get: function () { return this._cls.join(' '); },
  set: function (v) { this._cls = String(v).split(/\s+/).filter(Boolean); }
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
  get: function () {
    var s = this._text;
    for (var i = 0; i < this.childNodes.length; i++) { s += this.childNodes[i].textContent; }
    return s;
  },
  set: function (v) { this._text = String(v); this.childNodes = []; }
});
El.prototype.appendChild = function (c) { this.childNodes.push(c); return c; };
El.prototype.removeChild = function (c) { var i = this.childNodes.indexOf(c); if (i >= 0) { this.childNodes.splice(i, 1); } return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return this.attrs[k]; };
El.prototype.querySelector = function (sel) {
  /* 只支持 renderEventList 需要的 '.ev-row.cur' */
  var want = sel.split('.').filter(Boolean);
  var found = null;
  (function walk(n) {
    if (found) { return; }
    if (n._cls && want.every(function (c) { return n._cls.indexOf(c) >= 0; })) { found = n; return; }
    for (var i = 0; i < n.childNodes.length; i++) { walk(n.childNodes[i]); }
  })(this);
  return found;
};

global.document = { createElement: function (t) { return new El(t); } };

/* ------------------------------------------------------------- 加载模块 */
var MJLOG = require(base + '/web/js/mjlog.js');
var REPLAY = require(base + '/web/js/replay.js');
var UI = require(base + '/web/js/ui.js');

/* ------------------------------------------------------------- 工具 */
function collectImgs(node, out) {
  if (node.tagName === 'IMG') { out.push(node.src); }
  for (var i = 0; i < node.childNodes.length; i++) { collectImgs(node.childNodes[i], out); }
  return out;
}
function countTiles(node) {
  var n = 0;
  (function walk(x) { if (x._cls && x._cls.indexOf('tile') >= 0) { n++; } for (var i = 0; i < x.childNodes.length; i++) { walk(x.childNodes[i]); } })(node);
  return n;
}
function outline(node, depth, maxDepth, lines) {
  var pad = new Array(depth + 1).join('  ');
  var cls = node._cls.join('.');
  var txt = node._text ? ' "' + node._text + '"' : '';
  var extra = node.tagName === 'IMG' ? ' src=' + node.src : '';
  lines.push(pad + (cls ? '.' + cls : node.tagName.toLowerCase()) + extra + txt);
  if (depth >= maxDepth) { return; }
  for (var i = 0; i < node.childNodes.length; i++) { outline(node.childNodes[i], depth + 1, maxDepth, lines); }
}

/** 和了/流局的中央结果框里额外展示的ドラ・裏ドラ牌 */
function resultTiles(st) {
  if (!st.result) { return 0; }
  var n = 0;
  if (st.result.dora) { n += st.result.dora.length; }
  if (st.result.ura) { n += st.result.ura.length; }
  return n;
}

var problems = [];
function check(ok, msg) { if (!ok) { problems.push(msg); } console.log((ok ? '  OK   ' : '  FAIL ') + msg); }

/* ------------------------------------------------------------- 跑测试 */
var files = pickBase(walkXml(path.join(base, 'data'), []));
console.log('data/ 下牌谱：' + files.join(', '));

files.forEach(function (f) {
  var txt = fs.readFileSync(base + '/data/' + f, 'utf8');
  var game = MJLOG.parse(txt);
  console.log('\n=== ' + f + ' : ' + game.rounds.length + ' 局 ===');

  var rounds = REPLAY.buildGame(game);
  var allImgs = [];
  var tileTotal = 0;

  rounds.forEach(function (frames, ri) {
    /* 每局只抽查若干帧，控制输出量 */
    var probes = [0, Math.floor(frames.length / 3), Math.floor((frames.length * 2) / 3), frames.length - 1];
    probes.forEach(function (fi) {
      var st = frames[fi].state;
      var board = new El('div');

      /* --- 正常渲染 --- */
      UI.renderBoard(board, st, { selfSeat: 0, hideOthers: false });

      /* 牌数核对：4 家手牌 + 副露 + 牌河 + 宝牌指示牌 */
      var expected = st.dora.length + resultTiles(st);
      for (var s = 0; s < 4; s++) {
        expected += st.players[s].hand.length;
        expected += st.players[s].river.length;
        st.players[s].melds.forEach(function (m) { expected += m.tiles.length; });
      }
      var got = countTiles(board);
      if (got !== expected) {
        problems.push(f + ' R' + ri + ' F' + fi + ': 渲染牌数 ' + got + ' != 期望 ' + expected);
      }
      tileTotal += got;
      collectImgs(board, allImgs);

      /* --- 隐藏他家手牌：他家的手牌只出牌背，但张数必须一致 --- */
      var board2 = new El('div');
      UI.renderBoard(board2, st, { selfSeat: 0, hideOthers: true });
      var got2 = countTiles(board2);
      if (got2 !== expected) {
        problems.push(f + ' R' + ri + ' F' + fi + ': 隐藏他家手牌时渲染牌数 ' + got2 + ' != 期望 ' + expected);
      }
      collectImgs(board2, allImgs);
    });

    /* --- 事件列表 --- */
    var list = new El('div');
    UI.renderEventList(list, frames, Math.min(3, frames.length - 1));
    var rows = list.childNodes.length;
    if (rows !== frames.length) {
      problems.push(f + ' R' + ri + ': 事件列表行数 ' + rows + ' != 帧数 ' + frames.length);
    }
  });

  /* 素材存在性：img src 必须指向真实文件 */
  var uniq = {};
  allImgs.forEach(function (s) { uniq[s] = (uniq[s] || 0) + 1; });
  var missing = [];
  Object.keys(uniq).forEach(function (s) {
    var fp = base + '/' + s;
    if (!fs.existsSync(fp)) { missing.push(s); }
  });
  var expectTileCount = 0;
  rounds.forEach(function (frames, ri) {
    [0, frames.length - 1].forEach(function (fi) {
      var st = frames[fi].state;
      for (var s = 0; s < 4; s++) {
        expectTileCount += st.players[s].hand.length + st.players[s].river.length;
        st.players[s].melds.forEach(function (m) { expectTileCount += m.tiles.length; });
      }
    });
  });
  check(missing.length === 0, f + ': 所有 img src 均存在于磁盘（缺失 ' + missing.length + ' 个' + (missing.length ? ' -> ' + missing.join(', ') : '') + '）');
  check(allImgs.length > 0, f + ': 渲染产生 ' + allImgs.length + ' 个 <img>，' + Object.keys(uniq).length + ' 种素材');
  console.log('       抽查帧渲染牌总数 = ' + tileTotal + '（末帧合计约 ' + expectTileCount + '）');
});

/* ------------------------------------------------------------- 输出样例 */
console.log('\n===== 渲染样例：第 1 个牌谱 · 第 1 局 · 末帧（中央信息 + 自家面板）=====');
(function () {
  var txt = fs.readFileSync(base + '/data/' + files[0], 'utf8');
  var game = MJLOG.parse(txt);
  var frames = REPLAY.buildFrames(game, 0);
  var st = frames[frames.length - 1].state;
  var board = new El('div');
  UI.renderBoard(board, st, { selfSeat: 0, hideOthers: false });
  var lines = [];
  outline(board, 0, 3, lines);
  lines.slice(0, 80).forEach(function (l) { console.log(l); });
  console.log('… 共 ' + lines.length + ' 行');
  console.log('当前帧 desc = ' + st.desc);
})();

console.log('\n===== 结果 =====');
if (problems.length) {
  problems.slice(0, 40).forEach(function (m) { console.log('!! ' + m); });
  console.log('共 ' + problems.length + ' 个问题');
  process.exitCode = 1;
} else {
  console.log('全部通过');
}