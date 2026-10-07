/* mjlog.js — 天凤 mjlog XML 解析器（浏览器 + Node 通用，零依赖）
 *
 * 本文件不使用 DOMParser，改用正则分词，因此既可在浏览器 <script> 中使用，
 * 也可在 Node 里 require 后做离线自检（牌谱文件为 UTF-8 XML，通常无换行，
 * 所有子节点均为自闭合标签，属性值中不含双引号与 '>'）。
 *
 * 鸣牌 <N who m> 的 m 属性解码移植自 references/mjlog2mjai_parse.py。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.MJLOG = factory(); }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var SUIT_CHAR = ['m', 'p', 's', 'z'];

  // ------------------------------------------------------------------ 牌
  function kindOf(id) { return id >> 2; }
  function suitOf(id) { return Math.floor(kindOf(id) / 9); }
  function isRed(id) { return kindOf(id) < 27 && (id & 3) === 0 && (kindOf(id) % 9) === 4; }
  function tileName(id) {
    var k = kindOf(id), s = Math.floor(k / 9);
    if (s === 3) { return (k - 26) + 'z'; }
    var n = (k % 9) + 1;
    if (n === 5 && (id & 3) === 0) { return '0' + SUIT_CHAR[s]; }
    return n + SUIT_CHAR[s];
  }

  // ------------------------------------------------------------------ XML 分词
  var TAG_RE = /<([A-Za-z][A-Za-z0-9]*)((?:\s+[A-Za-z0-9_]+="[^"]*")*)\s*\/?>/g;
  var ATTR_RE = /([A-Za-z0-9_]+)="([^"]*)"/g;

  function parseAttrs(str) {
    var out = {}, m;
    ATTR_RE.lastIndex = 0;
    while ((m = ATTR_RE.exec(str)) !== null) { out[m[1]] = m[2]; }
    return out;
  }
  function tokenize(text) {
    var nodes = [], m;
    TAG_RE.lastIndex = 0;
    while ((m = TAG_RE.exec(text)) !== null) {
      nodes.push({ tag: m[1], attr: parseAttrs(m[2] || '') });
    }
    return nodes;
  }

  // ------------------------------------------------------------------ 工具
  function ints(s) {
    if (!s) { return []; }
    var a = s.split(','), out = [];
    for (var i = 0; i < a.length; i++) { if (a[i] !== '') { out.push(parseInt(a[i], 10)); } }
    return out;
  }
  function floats(s) {
    if (!s) { return []; }
    return s.split(',').map(parseFloat);
  }
  function nestPairs(a) {
    var r = [];
    for (var i = 0; i + 1 < a.length; i += 2) { r.push([a[i], a[i + 1]]); }
    return r;
  }
  function unq(s) {
    try { return decodeURIComponent(s); } catch (e) { return s; }
  }
  function scorePairs(sc) {
    var before = [], gain = [];
    for (var i = 0; i + 1 < sc.length; i += 2) { before.push(sc[i] * 100); gain.push(sc[i + 1] * 100); }
    return { before: before, gain: gain };
  }

  // ------------------------------------------------------------------ 鸣牌解码
  // 顺子（吃）解码：返回 3 个牌 id（按出牌顺序）
  function decodeChi(m) {
    var t = (m & 0xfc00) >> 10, r = t % 3;
    t = Math.floor(t / 3);
    t = 9 * Math.floor(t / 7) + (t % 7);
    t *= 4;
    var h = [t + ((m & 0x0018) >> 3), t + 4 + ((m & 0x0060) >> 5), t + 8 + ((m & 0x0180) >> 7)];
    if (r === 1) { h = [h[1], h[0], h[2]]; } else if (r === 2) { h = [h[2], h[0], h[1]]; }
    return h;
  }
  // 刻子（碰）解码：返回 3 个牌 id
  function decodePon(m) {
    var unused = (m & 0x0060) >> 5, t = (m & 0xfe00) >> 9, r = t % 3;
    t = Math.floor(t / 3) * 4;
    var h = [t, t, t];
    if (unused === 0) { h[0] += 1; h[1] += 2; h[2] += 3; }
    else if (unused === 1) { h[1] += 2; h[2] += 3; }
    else if (unused === 2) { h[1] += 1; h[2] += 3; }
    else { h[1] += 1; h[2] += 2; }
    if (r === 1) { h = [h[1], h[0], h[2]]; } else if (r === 2) { h = [h[2], h[0], h[1]]; }
    return h;
  }
  // 加杠解码：返回 4 个牌 id（首个为加进去的那张）
  function decodeKakan(m) {
    var added = (m & 0x0060) >> 5, t = (m & 0xfe00) >> 9, r = t % 3;
    t = Math.floor(t / 3) * 4;
    var h = [t, t, t];
    if (added === 0) { h[0] += 1; h[1] += 2; h[2] += 3; }
    else if (added === 1) { h[1] += 2; h[2] += 3; }
    else if (added === 2) { h[1] += 1; h[2] += 3; }
    else { h[1] += 1; h[2] += 2; }
    if (r === 1) { h = [h[1], h[0], h[2]]; } else if (r === 2) { h = [h[2], h[0], h[1]]; }
    return [t + added].concat(h);
  }
  // 杠（暗杠 / 大明杠）解码：返回 4 个牌 id
  function decodeKan(m) {
    var hai0 = (m & 0xff00) >> 8, kui = m & 0x3;
    if (!kui) { hai0 = (hai0 & ~3) + 3; }
    var t = Math.floor(hai0 / 4) * 4;
    var h = [t, t, t];
    var rem = hai0 % 4;
    if (rem === 0) { h[0] += 1; h[1] += 2; h[2] += 3; }
    else if (rem === 1) { h[1] += 2; h[2] += 3; }
    else if (rem === 2) { h[1] += 1; h[2] += 3; }
    else { h[1] += 1; h[2] += 2; }
    return [hai0].concat(h);
  }

  function parseCall(attr) {
    var caller = parseInt(attr.who, 10), m = parseInt(attr.m, 10), rel = m & 3;
    var ev = { type: 'call', player: caller, callee: (caller + rel) % 4, rel: rel, m: m };
    if (m & (1 << 2)) { ev.callType = 'chi'; ev.tiles = decodeChi(m); }
    else if (m & (1 << 3)) { ev.callType = 'pon'; ev.tiles = decodePon(m); }
    else if (m & (1 << 4)) { ev.callType = 'kakan'; ev.tiles = decodeKakan(m); }
    else if (m & (1 << 5)) { ev.callType = 'nuki'; ev.tiles = [m >> 8]; }
    else { ev.callType = rel ? 'daiminkan' : 'ankan'; ev.tiles = decodeKan(m); }
    return ev;
  }

  // ------------------------------------------------------------------ 具名标签
  function parseGo(attr) {
    var t = parseInt(attr.type, 10);
    return {
      red: ((t & 2) >> 1) === 0, kui: ((t & 4) >> 2) === 0, tonnan: ((t & 8) >> 3) === 1,
      sanma: ((t & 16) >> 4) === 1, soku: ((t & 64) >> 6) === 1, type: t,
      lobby: attr.lobby === undefined ? null : parseInt(attr.lobby, 10)
    };
  }
  function parseUn(attr) {
    var names = [], i;
    for (i = 0; i < 4; i++) { names.push(attr['n' + i] === undefined ? ('P' + i) : unq(attr['n' + i])); }
    return { names: names, dan: ints(attr.dan), rate: floats(attr.rate),
             sex: attr.sx ? attr.sx.split(',') : [] };
  }
  function parseInit(attr) {
    var seed = ints(attr.seed);
    return {
      round: seed[0], combo: seed[1], kyotaku: seed[2], dices: [seed[3], seed[4]], dora: seed[5],
      scores: ints(attr.ten).map(function (x) { return x * 100; }),
      oya: parseInt(attr.oya, 10),
      hands: [0, 1, 2, 3].map(function (i) { return attr['hai' + i] ? ints(attr['hai' + i]) : []; })
    };
  }
  function parseReach(attr) {
    var ev = { type: 'reach', player: parseInt(attr.who, 10), step: parseInt(attr.step, 10) };
    if (attr.ten) { ev.scores = ints(attr.ten).map(function (x) { return x * 100; }); }
    return ev;
  }
  function parseAgari(attr) {
    var sp = scorePairs(ints(attr.sc));
    return {
      type: 'agari', winner: parseInt(attr.who, 10), fromWho: parseInt(attr.fromWho, 10),
      hand: ints(attr.hai), machi: ints(attr.machi), dora: ints(attr.doraHai), ura: ints(attr.doraHaiUra),
      yaku: nestPairs(ints(attr.yaku)), yakuman: ints(attr.yakuman), ten: ints(attr.ten),
      ba: ints(attr.ba), before: sp.before, gain: sp.gain,
      owari: attr.owari ? floats(attr.owari) : null
    };
  }
  /* RYUUKYOKU 的 type 属性 -> 流局名（空 / 未知 = 荒牌流局）。tenhou 的取值：
   * yao9=九種九牌、kaze4=四風連打、reach4=四家立直、rck4=四槓散了、nm=流局満貫（流し満貫）、tripleRon=三家和了。 */
  var REASON_NAME = { yao9: '九種九牌', kaze4: '四風連打', reach4: '四家立直', rck4: '四槓散了', nm: '流局満貫', tripleRon: '三家和了' };

  function parseRyuukyoku(attr) {
    var sp = scorePairs(ints(attr.sc));
    return {
      type: 'ryuukyoku', reason: attr.type || '',
      /* who：mjlog 不一定会写（九種九牌 / 三家和了 的宣告者），没有就 null，由 replay 推断 */
      who: (attr.who === undefined || attr.who === '') ? null : parseInt(attr.who, 10),
      hands: [0, 1, 2, 3].map(function (i) { return attr['hai' + i] ? ints(attr['hai' + i]) : null; }),
      ba: ints(attr.ba), before: sp.before, gain: sp.gain,
      owari: attr.owari ? floats(attr.owari) : null
    };
  }

  // ------------------------------------------------------------------ 主入口
  /** 解析 mjlog 文本 -> { meta, rounds:[{init, events}] } */
  function parse(text) {
    var nodes = tokenize(text);
    var meta = { names: [], dan: [], rate: [], sex: [], config: null, oya: 0 };
    var rounds = [], cur = null, i, tag, attr, c;
    for (i = 0; i < nodes.length; i++) {
      tag = nodes[i].tag; attr = nodes[i].attr;
      if (tag === 'GO') { meta.config = parseGo(attr); continue; }
      if (tag === 'UN') {
        if (Object.keys(attr).length > 1) {
          var u = parseUn(attr); meta.names = u.names; meta.dan = u.dan; meta.rate = u.rate; meta.sex = u.sex;
        }
        continue;
      }
      if (tag === 'TAIKYOKU') { meta.oya = parseInt(attr.oya, 10); continue; }
      if (tag === 'SHUFFLE') { continue; }
      if (tag === 'INIT') { cur = { init: parseInit(attr), events: [] }; rounds.push(cur); continue; }
      if (!cur) { continue; }
      if (tag === 'N') { cur.events.push(parseCall(attr)); continue; }
      if (tag === 'REACH') { cur.events.push(parseReach(attr)); continue; }
      if (tag === 'DORA') { cur.events.push({ type: 'dora', tile: parseInt(attr.hai, 10) }); continue; }
      if (tag === 'AGARI') { cur.events.push(parseAgari(attr)); continue; }
      if (tag === 'RYUUKYOKU') { cur.events.push(parseRyuukyoku(attr)); continue; }
      if (tag.length < 2) { continue; }
      c = tag.charCodeAt(0);
      if (c >= 84 && c <= 87) { cur.events.push({ type: 'draw', player: c - 84, tile: parseInt(tag.slice(1), 10) }); continue; }      // T U V W
      if (c >= 68 && c <= 71) { cur.events.push({ type: 'discard', player: c - 68, tile: parseInt(tag.slice(1), 10) }); continue; }   // D E F G
    }
    return { meta: meta, rounds: rounds };
  }

  var DIRECTIONS = ['東', '南', '西', '北'];
  var NUM_KANJI = ['一', '二', '三', '四'];
  /** 局序号 -> 场风/局数，如 0 -> {bakaze:'東', kyoku:1}；0..15 覆盖 東南西北 四圈（延长战） */
  function roundLabel(round) { return { bakaze: DIRECTIONS[Math.floor(round / 4) % 4], kyoku: (round % 4) + 1 }; }
  /** 局序号 -> 中文局况，如 5 -> '南二局'（与 Python 端 mjscore/mjlog.py 的 joukyoku_label 一致） */
  function joukyokuLabel(round) { var l = roundLabel(round); return l.bakaze + NUM_KANJI[l.kyoku - 1] + '局'; }

  return {
    parse: parse, roundLabel: roundLabel, joukyokuLabel: joukyokuLabel,
    DIRECTIONS: DIRECTIONS, NUM_KANJI: NUM_KANJI,
    kindOf: kindOf, suitOf: suitOf, isRed: isRed, tileName: tileName,
    decodeChi: decodeChi, decodePon: decodePon, decodeKakan: decodeKakan, decodeKan: decodeKan,
    parseCall: parseCall, tokenize: tokenize, REASON_NAME: REASON_NAME
  };
});