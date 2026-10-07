/* selftest.js — Node 离线自检（无浏览器依赖）
 * 用法: node test/selftest.js [牌谱文件名...]
 *
 * 校验内容：
 *   1. mjlog 可解析，rounds/meta 合理；
 *   2. 回放每一帧的物理不变量：
 *        - 每张牌 id(0..135) 在 手牌∪副露∪牌河∪宝牌指示牌 中至多出现一次
 *        - 每种 kind 至多 4 张
 *        - 手牌+副露 张数 ∈ {13,14}（按副露类型修正）
 *        - 分数总和 + 供托×1000 守恒
 *   3. 输出每个事件的逐帧时间线到 test/out/
 */
'use strict';
var fs = require('fs');
var path = require('path');
var MJLOG = require(path.join(__dirname, '..', 'web', 'js', 'mjlog.js'));
var REPLAY = require(path.join(__dirname, '..', 'web', 'js', 'replay.js'));

var ROOT = path.join(__dirname, '..');
var DATA = path.join(ROOT, 'data');
var OUT = path.join(__dirname, 'out');
if (!fs.existsSync(OUT)) { fs.mkdirSync(OUT, { recursive: true }); }

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

var problems = [];
function fail(msg) { problems.push(msg); }

// --------------------------------------------------------------- 不变量检查
function checkFrame(st, ctx) {
  var seen = Object.create(null);
  function add(id, where) {
    if (seen[id] !== undefined) { fail(ctx + ': 牌 ' + id + '(' + MJLOG.tileName(id) + ') 重复出现: ' + seen[id] + ' 与 ' + where); }
    else { seen[id] = where; }
  }
  var ourOwn = 0;
  st.players.forEach(function (pl, i) {
    pl.hand.forEach(function (t) { add(t, 'P' + i + '.手牌'); });
    pl.melds.forEach(function (m, j) {
      m.tiles.forEach(function (t) { add(t, 'P' + i + '.副露' + j + '(' + m.callType + ')'); });
    });
    pl.river.forEach(function (r, j) { if (!r.called) { add(r.tile, 'P' + i + '.牌河' + j); } });
  });
  st.dora.forEach(function (t) { add(t, '宝牌指示牌'); });

  var kinds = Object.create(null), count = 0;
  Object.keys(seen).forEach(function (id) { var k = MJLOG.kindOf(+id); kinds[k] = (kinds[k] || 0) + 1; count++; });
  Object.keys(kinds).forEach(function (k) { if (kinds[k] > 4) { fail(ctx + ': kind ' + k + ' 共 ' + kinds[k] + ' 张(>4)'); } });

  // 手持张数 = 手牌 + 所有副露实体张数。
  // 结构张数固定为 13（手牌 + 3×副露数），但每个「杠」副露有第 4 张实体牌，
  // 因此 基准 = 13 + K（K = 4 张牌的副露数，即暗杠/加杠/大明杠）。
  // 「刚摸牌尚未打牌」时再 +1。
  if (st.phase === 'playing') {
    st.players.forEach(function (pl, i) {
      var n = pl.hand.length, K = 0;
      pl.melds.forEach(function (m) { n += m.tiles.length; if (m.tiles.length === 4) { K++; } });
      var base = 13 + K;
      if (n !== base && n !== base + 1) { fail(ctx + ': P' + i + ' 手持张数 = ' + n + ' (基准 ' + base + '/' + (base + 1) + ')'); }
    });
  }

  // 分数守恒
  var sum = st.scores.reduce(function (a, b) { return a + b; }, 0) + st.kyotaku * 1000;
  if (st._base === undefined) { st._base = sum; }
  if (sum !== st._base) { fail(ctx + ': 分数守恒破坏 sum+供托 = ' + sum + ' (基准 ' + st._base + ')'); }
  return count;
}

// --------------------------------------------------------------- 时间线
function fmtScores(st) {
  return st.scores.map(function (s) { return (s / 100).toFixed(1); }).join('/');
}
function line(frame) {
  var st = frame.state, ev = frame.ev;
  var s = '[' + String(frame.index).padStart(4, ' ') + '] ';
  s += (st.desc || '(开局)');
  var extra = '';
  if (ev && ev.type === 'agari') {
    extra = ' | 手牌 ' + ev.hand.map(MJLOG.tileName).join('') + ' 待ち ' + ev.machi.map(MJLOG.tileName).join('')
          + ' 宝牌 ' + ev.dora.map(MJLOG.tileName).join('') + ' 里 ' + (ev.ura || []).map(MJLOG.tileName).join('')
          + ' 役 ' + ev.yaku.map(function (p) { return p[0]; }).join(',') + ' ' + ev.ten.join('/') + '点';
  } else if (ev && ev.type === 'ryuukyoku') {
    extra = ' | ' + ev.hands.map(function (h, i) { return 'P' + i + ':' + (h ? h.map(MJLOG.tileName).join('') : '-'); }).join(' ');
  } else if (ev && ev.type === 'call') {
    extra = ' | ' + ev.tiles.map(MJLOG.tileName).join(' ') + ' callee=' + ev.callee;
  } else if (ev && ev.type === 'reach' && ev.step === 2 && ev.scores) {
    extra = ' | ten=' + ev.scores.map(function (x) { return x / 100; }).join(',');
  }
  s += extra;
  s += '   {' + fmtScores(st) + '} 供托' + st.kyotaku + ' 本场' + st.honba;
  if (st.warnings.length) { s += '  ⚠' + st.warnings[st.warnings.length - 1]; }
  return s;
}
function handDump(st) {
  var out = [];
  st.players.forEach(function (pl, i) {
    var melds = pl.melds.map(function (m) { return '[' + m.callType + ' ' + m.tiles.map(MJLOG.tileName).join(' ') + ']'; }).join('');
    out.push('  P' + i + ' ' + (pl.name || '') + ' ' + (pl.riichi ? 'R' : ' ') + ' 手牌(' + pl.hand.length + ') '
      + pl.hand.slice().sort(function (a, b) { return a - b; }).map(MJLOG.tileName).join(' ') + ' ' + melds
      + ' 河 ' + pl.river.map(function (r) { return MJLOG.tileName(r.tile) + (r.tsumogiri ? '*' : '') + (r.riichi ? '!' : ''); }).join(' ')
      + ' ' + (pl.score / 100));
  });
  out.push('  宝牌指示牌 ' + st.dora.map(MJLOG.tileName).join(' ') + ' | 余 ' + st.tilesLeft + ' | ' + st.phase);
  return out.join('\n');
}

// --------------------------------------------------------------- 主流程
var files = process.argv.slice(2);
if (!files.length) { files = pickBase(walkXml(DATA, [])); }
console.log('默认牌谱 ' + files.length + ' 个：' + files.join(', '));

var grand = { files: 0, rounds: 0, frames: 0, draws: 0, discards: 0, calls: 0, reaches: 0, doras: 0, agari: 0, ryuu: 0 };
files.forEach(function (f) {
  var full = path.isAbsolute(f) ? f : path.join(DATA, f);
  var text = fs.readFileSync(full, 'utf8');
  var game = MJLOG.parse(text);
  var tagCount = MJLOG.tokenize(text).length;
  console.log('\n===== ' + f + ' (' + text.length + ' chars, ' + tagCount + ' tags) =====');
  console.log('  玩家: ' + game.meta.names.join(' / '));
  console.log('  段位: ' + game.meta.dan.join('/') + '  rate: ' + game.meta.rate.join('/') + '  sex: ' + game.meta.sex.join('/'));
  console.log('  规则: ' + JSON.stringify(game.meta.config) + '  起家 oya=' + game.meta.oya);
  console.log('  局数: ' + game.rounds.length);

  var lines = [];
  lines.push('# ' + f);
  lines.push('# 玩家 ' + game.meta.names.join(' / '));
  lines.push('# 规则 ' + JSON.stringify(game.meta.config));
  var counts = {};
  game.rounds.forEach(function (r, ri) {
    var lbl = MJLOG.roundLabel(r.init.round);
    var evs = r.events;
    var stat = {};
    evs.forEach(function (e) { stat[e.type] = (stat[e.type] || 0) + 1; (e.callType ? stat['call:' + e.callType] = (stat['call:' + e.callType] || 0) + 1 : 0); });
    console.log('  -- 第' + (ri + 1) + '局 ' + lbl.bakaze + lbl.kyoku + '局 ' + r.init.combo + '本场 供托' + r.init.kyotaku
      + ' 起手 P0=' + r.init.hands[0].map(MJLOG.tileName).join('') + ' ドラ表示=' + MJLOG.tileName(r.init.dora)
      + ' | ' + JSON.stringify(stat));
    grand.rounds++;
    grand.draws += stat.draw || 0; grand.discards += stat.discard || 0; grand.calls += stat.call || 0;
    grand.reaches += stat.reach || 0; grand.doras += stat.dora || 0; grand.agari += stat.agari || 0; grand.ryuu += stat.ryuukyoku || 0;
    Object.keys(stat).forEach(function (k) { counts[k] = (counts[k] || 0) + stat[k]; });

    var frames = REPLAY.buildFrames(game, ri);
    grand.frames += frames.length;
    frames[0].state._base = frames[0].state.scores.reduce(function (a, b) { return a + b; }, 0) + frames[0].state.kyotaku * 1000;
    var base = frames[0].state._base;
    var prevWarn = 0;
    frames.forEach(function (fr) {
      fr.state._base = base;
      checkFrame(fr.state, f + ' 第' + (ri + 1) + '局 帧' + fr.index + ' (' + (fr.state.desc || '开局') + ')');
      if (fr.state.warnings.length > prevWarn) {
        fail(f + ' 第' + (ri + 1) + '局 帧' + fr.index + ' (' + (fr.state.desc || '开局') + '): 警告 ' + fr.state.warnings[fr.state.warnings.length - 1]);
        prevWarn = fr.state.warnings.length;
      }
    });
    lines.push('');
    lines.push('## 第' + (ri + 1) + '局 ' + lbl.bakaze + lbl.kyoku + '局 ' + r.init.combo + '本场  事件数 ' + r.events.length + ' 帧数 ' + frames.length);
    lines.push('  INIT: 分数 ' + r.init.scores.map(function (x) { return x / 100; }).join('/') + ' 供托 ' + r.init.kyotaku
      + ' 骰子 ' + r.init.dices.join(',') + ' ドラ ' + MJLOG.tileName(r.init.dora) + ' oya=' + r.init.oya);
    r.init.hands.forEach(function (h, i) { lines.push('  起手 P' + i + ' ' + h.map(MJLOG.tileName).join('')); });
    frames.forEach(function (fr) { lines.push(line(fr)); });
    lines.push('');
    lines.push('### 终局状态');
    lines.push(handDump(frames[frames.length - 1].state));
  });
  console.log('  事件合计: ' + JSON.stringify(counts));
  grand.files++;
  /* 用 basename：f 现在可能是 `paipu/<时间戳>/xxx.xml` 这样的相对路径 */
  fs.writeFileSync(path.join(OUT, 'timeline_' + path.basename(f).replace(/\.xml$/i, '') + '.txt'), lines.join('\n'), 'utf8');
});

console.log('\n================ 汇总 ================');
console.log(JSON.stringify(grand, null, 2));
if (problems.length) {
  var cat = {}, order = [];
  problems.forEach(function (p) {
    var k = p.replace(/^[^ ]+\.xml 第\d+局 帧\d+ \([^)]*\): /, '').replace(/= \d+ /, '= N ').replace(/\(\d+\)/, '');
    k = k.replace(/帧\d+/g, '帧N').replace(/P\d/g, 'Pn');
    if (cat[k] === undefined) { cat[k] = 0; order.push(k); }
    cat[k]++;
  });
  console.log('\n!!! 发现 ' + problems.length + ' 个问题，按类别:');
  order.forEach(function (k) { console.log('  [' + cat[k] + '] ' + k); });
  console.log('\n  样例（每类 3 条）:');
  var shown = {};
  problems.forEach(function (p) {
    var k = p.replace(/^[^ ]+\.xml 第\d+局 帧\d+ \([^)]*\): /, '').replace(/= \d+ /, '= N ').replace(/\(\d+\)/, '');
    k = k.replace(/帧\d+/g, '帧N').replace(/P\d/g, 'Pn');
    shown[k] = (shown[k] || 0);
    if (shown[k] < 3) { console.log('    ' + p); shown[k]++; }
  });
  process.exitCode = 1;
} else {
  console.log('\n[OK] 全部不变量通过');
}