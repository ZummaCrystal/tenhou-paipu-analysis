/* replay.js — 牌谱回放引擎（浏览器 + Node 通用）
 *
 * 把一局的原始事件流展开为「逐帧快照」：frames[0] 为开局（INIT 后）状态，
 * frames[i+1] 为处理完第 i 个事件后的状态。前端只需按索引取帧渲染，
 * 即可实现「上一步 / 下一步」的顺序播放与回退。
 *
 * 状态维护的物理不变量（自检脚本会验证）：
 *   - 每张牌 id(0..135) 在「手牌 ∪ 副露 ∪ 牌河(被鸣走的除外) ∪ 宝牌指示牌」中至多出现一次；
 *   - 每种 kind 至多 4 张（被鸣走的那张同时留在牌河与副露里，只算一张）。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(require('./mjlog.js')); }
  else { root.REPLAY = factory(root.MJLOG); }
})(typeof self !== 'undefined' ? self : this, function (MJLOG) {
  'use strict';

  var kindOf = MJLOG.kindOf, isRed = MJLOG.isRed, tileName = MJLOG.tileName;
  var CALL_NAME = { chi: '吃', pon: '碰', kakan: '加杠', daiminkan: '大明杠', ankan: '暗杠', nuki: '拔北' };
  var WINDS = ['東', '南', '西', '北'];

  function seatWind(seat, oya) { return WINDS[(seat - oya + 4) % 4]; }

  // --------------------------------------------------------------- 深拷贝
  function clonePlayer(p) {
    return {
      hand: p.hand.slice(),
      melds: p.melds.map(function (m) {
        return { callType: m.callType, tiles: m.tiles.slice(), calledId: m.calledId, from: m.from, open: m.open };
      }),
      river: p.river.map(function (r) {
        return { tile: r.tile, tsumogiri: r.tsumogiri, riichi: r.riichi, called: r.called, win: r.win };
      }),
      riichi: p.riichi, riichiPending: p.riichiPending, score: p.score, name: p.name, turns: p.turns
    };
  }
  function cloneState(s) {
    return {
      roundIndex: s.roundIndex, round: s.round, honba: s.honba, kyotaku: s.kyotaku, oya: s.oya,
      scores: s.scores.slice(), players: s.players.map(clonePlayer),
      dora: s.dora.slice(), dices: s.dices, drawn: s.drawn, tilesLeft: s.tilesLeft,
      phase: s.phase, result: s.result, reveal: (s.reveal || []).slice(), desc: s.desc, evIndex: s.evIndex, warnings: s.warnings.slice()
    };
  }

  // --------------------------------------------------------------- 手牌操作
  /** 从手牌移除指定 kind 的一张（优先移除普通牌，保留赤宝牌） */
  function takeKind(hand, k) {
    var plain = -1, red = -1, i;
    for (i = 0; i < hand.length; i++) {
      if (kindOf(hand[i]) === k) { if (isRed(hand[i])) { red = i; } else { plain = i; break; } }
    }
    var idx = plain >= 0 ? plain : red;
    if (idx < 0) { return null; }
    return hand.splice(idx, 1)[0];
  }

  /** 按牌 id 精确移除；找不到则退回按 kind 移除（并返回 null 表示未精确命中） */
  function takeExact(hand, id) {
    var i = hand.indexOf(id);
    if (i >= 0) { return hand.splice(i, 1)[0]; }
    return takeKind(hand, kindOf(id));
  }

  // --------------------------------------------------------------- 初始状态
  function initialState(game, roundIndex) {
    var round = game.rounds[roundIndex], init = round.init;
    return {
      roundIndex: roundIndex,
      round: init.round, honba: init.combo, kyotaku: init.kyotaku, oya: init.oya,
      scores: init.scores.slice(),
      players: [0, 1, 2, 3].map(function (i) {
        return {
          hand: init.hands[i].slice(), melds: [], river: [],
          riichi: false, riichiPending: false,
          score: init.scores[i], name: game.meta.names[i] || ('P' + i), turns: 0
        };
      }),
      dora: [init.dora], dices: init.dices, drawn: null, tilesLeft: 70,
      phase: 'playing', result: null, reveal: [], desc: '开局 · 配牌', evIndex: -1, warnings: []
    };
  }

  // --------------------------------------------------------------- 事件处理
  function applyCall(st, ev) {
    var p = ev.player, pl = st.players[p], i;
    var calledId = null;

    if (ev.callType === 'chi' || ev.callType === 'pon' || ev.callType === 'daiminkan') {
      var cp = st.players[ev.callee];
      if (cp.river.length) {
        /* 被鸣的牌不从牌河移除：原地打 called 标记（UI 用红框标出），
         * 它与副露里那张是同一张实体牌，校验不变量时只计一次。 */
        var last = cp.river[cp.river.length - 1];
        last.called = true;
        calledId = last.tile;
      }
    }

    var nm = CALL_NAME[ev.callType] || ev.callType;
    if (ev.callType === 'nuki' || ev.callType === 'kakan') {
      // 拔北 / 加杠：第 4 张（或北）来自手牌
      if (takeExact(pl.hand, ev.tiles[0]) === null) {
        st.warnings.push(nm + ': 手牌中找不到 ' + tileName(ev.tiles[0]));
      }
    } else {
      // 吃 / 碰 / 大明杠：tiles[0] 就是被鸣的那张（来自牌河），其余来自手牌
      // 暗杠：calledId 为 null，4 张全部来自手牌
      if (calledId !== null && ev.tiles.indexOf(calledId) < 0) {
        st.warnings.push(nm + ': 副露[' + ev.tiles.map(tileName).join(' ') + '] 与牌河 ' + tileName(calledId) + ' 不一致');
      }
      for (i = 0; i < ev.tiles.length; i++) {
        if (ev.tiles[i] === calledId) { continue; }
        if (takeExact(pl.hand, ev.tiles[i]) === null) {
          st.warnings.push(nm + ': 手牌中找不到 ' + tileName(ev.tiles[i]));
        }
      }
    }

    if (ev.callType === 'kakan') {
      // 把已有的碰升级为加杠
      var found = false;
      for (i = 0; i < pl.melds.length; i++) {
        if (pl.melds[i].callType === 'pon' && kindOf(pl.melds[i].tiles[0]) === kindOf(ev.tiles[0])) {
          pl.melds[i].callType = 'kakan'; pl.melds[i].tiles = ev.tiles.slice(); found = true; break;
        }
      }
      if (!found) { pl.melds.push({ callType: 'kakan', tiles: ev.tiles.slice(), calledId: null, from: null, open: true }); }
    } else {
      pl.melds.push({
        callType: ev.callType, tiles: ev.tiles.slice(), calledId: calledId,
        from: ev.callee, open: ev.callType !== 'ankan'
      });
    }

    if (ev.callType === 'ankan' || ev.callType === 'kakan') {
      /* 暗杠 / 加杠的动作视为出了一次牌（巡目 +1）；吃 / 碰 / 大明杠不算 */
      pl.turns += 1;
    }

    st.drawn = null;
    st.desc = pl.name + ' ' + (CALL_NAME[ev.callType] || ev.callType);
    if (calledId !== null) { st.desc += '（来自 ' + st.players[ev.callee].name + ' 的 ' + tileName(calledId) + '）'; }
  }

  function applyEvent(st, ev) {
    var p, pl, i;
    switch (ev.type) {
      case 'draw':
        p = ev.player; pl = st.players[p];
        pl.hand.push(ev.tile);
        /* 摸牌不加巡目：巡目按「出牌」计（与 mjscore/replay.py 对齐） */
        st.drawn = { player: p, tile: ev.tile };
        st.tilesLeft = Math.max(0, st.tilesLeft - 1);
        st.desc = pl.name + ' 摸牌 ' + tileName(ev.tile);
        break;

      case 'discard':
        p = ev.player; pl = st.players[p];
        var tsumogiri = !!(st.drawn && st.drawn.player === p && st.drawn.tile === ev.tile);
        var idx = pl.hand.indexOf(ev.tile);
        if (idx >= 0) { pl.hand.splice(idx, 1); }
        else if (!takeKind(pl.hand, kindOf(ev.tile))) { st.warnings.push('打牌: 手牌中找不到 ' + tileName(ev.tile)); }
        var entry = { tile: ev.tile, tsumogiri: tsumogiri, riichi: false, called: false };
        if (pl.riichiPending) { entry.riichi = true; pl.riichiPending = false; }
        pl.river.push(entry);
        pl.turns += 1;   /* 出牌一次 +1（巡目口径） */
        st.drawn = null;
        st.desc = pl.name + (tsumogiri ? ' 摸切 ' : ' 打牌 ') + tileName(ev.tile);
        break;

      case 'call':
        applyCall(st, ev);
        break;

      case 'reach':
        p = ev.player; pl = st.players[p];
        if (ev.step === 1) {
          pl.riichiPending = true;
          st.desc = pl.name + ' 立直宣告';
        } else {
          pl.riichi = true; pl.riichiPending = false;
          if (ev.scores) { st.scores = ev.scores.slice(); for (i = 0; i < 4; i++) { st.players[i].score = st.scores[i]; } }
          st.kyotaku += 1;
          st.desc = pl.name + ' 立直（供托 +1000）';
        }
        break;

      case 'dora':
        st.dora.push(ev.tile);
        st.desc = '新宝牌指示牌 ' + tileName(ev.tile);
        break;

      case 'agari':
        st.phase = 'agari';
        for (i = 0; i < 4; i++) { st.scores[i] = ev.before[i] + ev.gain[i]; st.players[i].score = st.scores[i]; }
        /* 和了牌（m00569 ①）：自摸 = 刚摸到的那张；荣和 = 放铳者牌河的最后一张。
         * 铳牌不从牌河拿走、也不塞进和了者手牌，只给牌河那一张打 win 标记（渲染成绿框）。 */
        var winTile = null;
        if (ev.winner === ev.fromWho) {
          if (st.drawn && st.drawn.player === ev.winner) { winTile = st.drawn.tile; }
        } else {
          var dp = st.players[ev.fromWho];
          if (dp.river.length) {
            var e2 = dp.river[dp.river.length - 1];
            e2.win = true;
            winTile = e2.tile;
          }
        }
        ev.winTile = winTile;
        /* 展示用的手牌保持「上一帧」的摆法（m00569 ①②），不再用 mjlog 的 hai 覆盖：
         *   - 荣和：手牌仍是 13 张，铳牌留在放铳者牌河里（绿框）
         *   - 自摸：手牌仍是 13 张 + st.drawn 单摆的摸牌（与上一帧同一个摆法）
         * mjlog 的权威手牌（含和了牌）仍在 st.result.hand 里可取。 */
        /* 要摊开手牌的座位名单（一炮双响 / 三响会逐帧累加）：和了帧只摊开名单里的家 */
        st.reveal = (st.reveal || []).concat([ev.winner]);
        st.result = ev;
        st.kyotaku = 0;
        st.desc = st.players[ev.winner].name + (ev.winner === ev.fromWho ? ' 自摸和了' : ' 荣和（放铳：' + st.players[ev.fromWho].name + '）');
        break;

      case 'ryuukyoku':
        /* m00635 ①：流局帧与和了帧一样是「显示 / 隐藏」的特例：只摊开 st.reveal 名单里的家，
         * 其余一律隐藏（含自家），与「隐藏他家手牌」按钮无关；下一局开始自动恢复用户选项。
         * 名单按流局种类算：
         *   荒牌流局            -> 只摊开听牌家（mjlog 的 haiN 属性就是听牌家的手牌）
         *   流局満貫(nm)        -> 満貫者视为和了，只摊开満貫者（不论他是否听牌）
         *   九種九牌(yao9)      -> 只摊开宣告者（mjlog 一般不写 who，退化为「最后摸牌的那家」）
         *   四家立直(reach4)    -> 强制摊开四家
         *   四風連打(kaze4) / 四槓散了(rck4) -> 强制隐藏四家（reveal = []）
         *   三家和了(tripleRon) -> 摊开三家荣和者、隐藏放铳家（mjlog 的 who 视为放铳家，
         *                        缺失时退化为「最后打牌的那家」；无真实样本，未做数据验证）
         * 注意：5 个测试牌谱里只有荒牌流局（7 次），満貫 / 途中流局的三个分支没有真实样本。 */
        st.phase = 'ryuukyoku';
        for (i = 0; i < 4; i++) { st.scores[i] = ev.before[i] + ev.gain[i]; st.players[i].score = st.scores[i]; }
        for (i = 0; i < 4; i++) { if (ev.hands[i] && ev.hands[i].length) { st.players[i].hand = ev.hands[i].slice(); } }
        var rkReason = ev.reason || '', rkDeclarer = -1;
        ev.tenpai = [];
        ev.nagashi = [];
        for (i = 0; i < 4; i++) {
          if (ev.hands[i] && ev.hands[i].length) { ev.tenpai.push(i); }
          /* 満貫者：只有流局満貫（nm）才用「点数为正」判断 —— 荒牌流局的听牌家也会拿到 +1000/1500，
           * 不能用 gain > 0 当満貫者，否则荒牌流局会被误显示成「流局満貫」。 */
          if (rkReason === 'nm' && ev.gain[i] > 0) { ev.nagashi.push(i); }
        }
        rkDeclarer = (ev.who === null || ev.who === undefined)
          ? ((st.drawn && st.drawn.player !== undefined) ? st.drawn.player : -1) : ev.who;
        if (rkReason === 'nm') { st.reveal = ev.nagashi.slice(); }
        else if (rkReason === 'yao9') { st.reveal = (rkDeclarer >= 0) ? [rkDeclarer] : []; }
        else if (rkReason === 'reach4') { st.reveal = [0, 1, 2, 3]; }
        else if (rkReason === 'kaze4' || rkReason === 'rck4') { st.reveal = []; }
        /* m00739：三家和了 = 三家荣和同一张牌 -> 摊开被荣和的三家，隐藏放铳家 */
        else if (rkReason === 'tripleRon') {
          st.reveal = (rkDeclarer >= 0) ? [0, 1, 2, 3].filter(function (s) { return s !== rkDeclarer; }) : [];
        }
        else { st.reveal = ev.tenpai.slice(); }
        st.result = ev;
        /* 事件列表的描述用正确的流局名（原来的 kaze4 / nm 映射是错的） */
        st.desc = '流局（' + (MJLOG.REASON_NAME[rkReason] || '荒牌流局') + '）';
        break;
    }
  }

  /** 展开一局 -> frames 数组；frames[0] 为开局帧 */
  function buildFrames(game, roundIndex) {
    var st = initialState(game, roundIndex);
    var frames = [{ state: cloneState(st), ev: null, index: 0 }];
    var evs = game.rounds[roundIndex].events;
    for (var i = 0; i < evs.length; i++) {
      applyEvent(st, evs[i]);
      st.evIndex = i;
      frames.push({ state: cloneState(st), ev: evs[i], index: i + 1 });
    }
    return frames;
  }

  /** 整局游戏的全部帧：[[frames],[frames],...] */
  function buildGame(game) {
    var out = [];
    for (var i = 0; i < game.rounds.length; i++) { out.push(buildFrames(game, i)); }
    return out;
  }

  return {
    buildFrames: buildFrames, buildGame: buildGame, initialState: initialState,
    applyEvent: applyEvent, applyCall: applyCall, cloneState: cloneState,
    seatWind: seatWind, CALL_NAME: CALL_NAME
  };
});
