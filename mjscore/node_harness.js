#!/usr/bin/env node
/* node_harness.js — Node 端牌谱处理工具（零依赖）
 *
 * 复用前端同款 web/js/mjlog.js + web/js/replay.js + web/js/mjsfeat.js，因此 Node 这一路
 * 与浏览器里跑的代码是同一份，用来：
 *   --records  <牌谱.xml>...  逐行输出「非自摸摸牌帧」打点行（JSONL）-> tools/analyze.py --tool node 入库
 *   --frames   <牌谱.xml>...  逐行输出每一帧的状态快照（JSONL）-> 测试 fixture / 算法交叉校验
 *   --invariants <牌谱.xml>... 逐帧校验牌张不变量，输出 {log_id, frames, errors}
 *   --summary  <牌谱.xml>...  逐行输出每个牌谱的事件统计
 * 参数：
 *   --out FILE   写入文件（默认 stdout）—— 本环境 PowerShell 无法捕获原生命令 stdout，务必用 --out
 *   --pretty     人类可读的 JSON（仅 --summary / --invariants 建议使用）
 */
'use strict';

var fs = require('fs');
var path = require('path');

var JS_DIR = path.join(__dirname, '..', 'web', 'js');
var MJLOG = require(path.join(JS_DIR, 'mjlog.js'));
var REPLAY = require(path.join(JS_DIR, 'replay.js'));
var MJSFEAT = require(path.join(JS_DIR, 'mjsfeat.js'));

var TILE_KIND = function (t) { return t >> 2; };

function loadGame(file) {
  var text = fs.readFileSync(file, 'utf8');
  var game = MJLOG.parse(text);
  game.path = path.resolve(file);
  game.logId = path.basename(file).replace(/\.xml$/i, '');
  return game;
}

/* 逐帧校验牌张不变量（与 test/selftest.js 同款口径） */
function checkInvariants(game) {
  var errors = [], frames = 0, ri, i, rnd, st, ev, seen, kinds;
  function bump(t) {
    seen[t] = (seen[t] || 0) + 1;
    kinds[TILE_KIND(t)] = (kinds[TILE_KIND(t)] || 0) + 1;
  }
  function snap(st) {
    seen = {}; kinds = {};
    var s, k, j;
    for (s = 0; s < 4; s++) {
      var p = st.players[s];
      for (j = 0; j < p.hand.length; j++) { bump(p.hand[j]); }
      for (j = 0; j < p.melds.length; j++) { for (k = 0; k < p.melds[j].tiles.length; k++) { bump(p.melds[j].tiles[k]); } }
      for (j = 0; j < p.river.length; j++) { if (!p.river[j].called) { bump(p.river[j].tile); } }
    }
    for (j = 0; j < st.dora.length; j++) { bump(st.dora[j]); }
  }
  for (ri = 0; ri < game.rounds.length; ri++) {
    st = REPLAY.initialState(game, ri);
    rnd = game.rounds[ri];
    for (i = 0; i < rnd.events.length; i++) {
      ev = rnd.events[i];
      REPLAY.applyEvent(st, ev);
      st.evIndex = i;
      frames += 1;
      snap(st);
      var t;
      for (t in seen) { if (seen[t] > 1) { errors.push('局' + ri + ' 帧' + (i + 1) + '：牌 ' + MJLOG.tileName(+t) + ' 出现 ' + seen[t] + ' 次'); } }
      for (t in kinds) { if (kinds[t] > 4) { errors.push('局' + ri + ' 帧' + (i + 1) + '：kind ' + t + ' 出现 ' + kinds[t] + ' 次'); } }
      var w;
      for (w = 0; w < st.warnings.length; w++) { errors.push('局' + ri + ' 帧' + (i + 1) + '：' + st.warnings[w]); }
    }
  }
  return { log_id: game.logId, rounds: game.rounds.length, frames: frames, errors: errors };
}

function emit(records, mode, outPath) {
  var lines = [];
  for (var i = 0; i < records.length; i++) { lines.push(JSON.stringify(records[i])); }
  var text = lines.length ? lines.join('\n') + '\n' : '';
  if (outPath && outPath !== '-') { fs.writeFileSync(outPath, text, 'utf8'); }
  else { process.stdout.write(text); }
}

function main(argv) {
  var mode = 'records', files = [], out = null;
  for (var i = 0; i < argv.length; i++) {
    var a = argv[i];
    if (a === '--records' || a === '--frames' || a === '--summary' || a === '--invariants') { mode = a.slice(2); }
    else if (a === '--out') { out = argv[++i]; }
    else if (a === '--help' || a === '-h') {
      process.stdout.write('用法: node mjscore/node_harness.js [--records|--frames|--summary|--invariants] [--out FILE] <牌谱.xml>...\n');
      return 0;
    } else { files.push(a); }
  }
  if (!files.length) { process.stderr.write('缺少牌谱文件参数（绝对路径）\n'); return 2; }
  var all = [], total = 0, failed = 0;
  for (i = 0; i < files.length; i++) {
    var game = loadGame(files[i]);
    if (mode === 'records') {
      var recs = MJSFEAT.recordsForGame(game);
      total += recs.length;
      all = all.concat(recs);
    } else if (mode === 'frames') {
      for (var ri = 0; ri < game.rounds.length; ri++) {
        var frames = REPLAY.buildFrames(game, ri);
        for (var k = 0; k < frames.length; k++) {
          all.push({ log_id: game.logId, round_index: ri, index: k, ev: frames[k].ev, state: frames[k].state });
        }
      }
    } else if (mode === 'invariants') {
      var chk = checkInvariants(game);
      if (chk.errors.length) { failed += 1; }
      all.push(chk);
    } else {
      var stat = { draw: 0, discard: 0, call: 0, reach: 0, dora: 0, agari: 0, ryuukyoku: 0 };
      for (var r2 = 0; r2 < game.rounds.length; r2++) {
        var evs = game.rounds[r2].events;
        for (var e = 0; e < evs.length; e++) { stat[evs[e].type] += 1; }
      }
      all.push({ log_id: game.logId, rounds: game.rounds.length, events: stat,
                 annotations: MJSFEAT.recordsForGame(game).length });
    }
  }
  emit(all, mode, out);
  if (mode === 'invariants') {
    process.stderr.write('[node] 校验 ' + all.length + ' 个牌谱，失败 ' + failed + ' 个\n');
    return failed ? 1 : 0;
  }
  if (mode === 'records') { process.stderr.write('[node] 打点行 ' + total + '\n'); }
  return 0;
}

process.exitCode = main(process.argv.slice(2));