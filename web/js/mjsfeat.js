/* mjsfeat.js — 第一类特征打点（浏览器 + Node 通用，零依赖）
 *
 * 打点对象：**非自摸的摸牌帧**；打点视角：**摸牌者自己**
 * 本文件与 Python 端 mjscore/feats.py 的 16 个「第一类特征」、口径、字段名逐项对齐，
 * test/mjscore_test.py 会交叉校验「Node 打点」与「Python 打点」的结果完全一致。
 *
 * 第 21 轮（m02959）把 17 个「第二类特征」（3 个向听数 + 12 个期望枚数/打点 + 2 个危险筋组·两面组）
 * 也登记在 FEATURES 里：浏览器只用它们的 key / 中文名 / 值域（检索下拉 + 帧特征面板显示）；
 * 这些值由 Python 端算好后入库（js 侧没有实现；--tool node 时由 cli.py 用 Python 补列）。
 * 三个向听数的内部取值 3 表示「>=3」，界面上一律显示成 >=3（用户 m04115②）。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(require('./mjlog.js'), require('./replay.js')); }
  else { root.MJSFEAT = factory(root.MJLOG, root.REPLAY); }
})(typeof self !== 'undefined' ? self : this, function (MJLOG, REPLAY) {
  'use strict';

  var YES = '是', NO = '否', DEALER = '亲家', CHILD = '子家';
  /* 会破坏「门前」的副露（拔北不计入副露数量，暗杠计入） */
  var OPEN_CALLS = { chi: 1, pon: 1, kakan: 1, daiminkan: 1, ankan: 1 };

  /* 特征注册表：与 mjscore/feats.py 的 FEATURES 一致（key / 中文名 / 值域） */
  var FEATURES = [
    { key: 'joukyoku', name: '局况', kind: 'enum', values: (function () {
        var out = [], bs = MJLOG.DIRECTIONS, ks = MJLOG.NUM_KANJI, i, j;
        for (i = 0; i < bs.length; i++) { for (j = 0; j < ks.length; j++) { out.push(bs[i] + ks[j] + '局'); } }
        return out;
      })() },
    { key: 'minami3', name: '是否南三局及以后', kind: 'enum', values: [YES, NO] },
    { key: 'junme', name: '巡目', kind: 'int', min: 1, max: 30 },
    { key: 'kyotaku', name: '供托', kind: 'int', min: 0, max: 30000, step: 100 },
    { key: 'oyako', name: '自家', kind: 'enum', values: [DEALER, CHILD] },
    { key: 'rank', name: '顺位', kind: 'int', min: 1, max: 4 },
    { key: 'riichi_self', name: '自家立直状态', kind: 'enum', values: [YES, NO] },
    { key: 'meld_self', name: '自家副露状态', kind: 'enum', values: [YES, NO] },
    { key: 'meld_self_n', name: '自家副露数量', kind: 'int', min: 0, max: 4 },
    { key: 'riichi_others_n', name: '立直家（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'meld_others_n', name: '副露家（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'meld2_others_n', name: '两副露以上（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'meld3_others_n', name: '三副露以上（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'oya_riichi', name: '亲家（他家）立直状态', kind: 'enum', values: [YES, NO] },
    { key: 'oya_meld', name: '亲家（他家）副露状态', kind: 'enum', values: [YES, NO] },
    { key: 'oya_meld_n', name: '亲家（他家）副露数量', kind: 'int', min: 0, max: 4 },

    /* ---- 第二类特征（第 21 轮，m02959）：值由 Python 端算好后入库，这里只登记定义 ---- */
    { key: 'shanten_kokushi', name: '国士無双向听数', kind: 'int', min: -1, max: 3 },
    { key: 'shanten_chiitoi', name: '七対子向听数', kind: 'int', min: -1, max: 3 },
    { key: 'shanten_mentsu', name: '面子手向听数', kind: 'int', min: -1, max: 3 },
    { key: 'furo_tsumo_tenpai_expect', name: '副露自摸期望听牌枚数', kind: 'float', min: 0, max: 100000 },
    { key: 'furo_tsumo_tenpai_abs', name: '副露自摸期望听牌绝对枚数', kind: 'float', min: 0, max: 100000 },
    { key: 'furo_ron_tenpai_expect', name: '副露荣和期望听牌枚数', kind: 'float', min: 0, max: 100000 },
    { key: 'furo_ron_tenpai_abs', name: '副露荣和期望听牌绝对枚数', kind: 'float', min: 0, max: 100000 },
    { key: 'menzen_tenpai_expect', name: '立直/默听期望听牌枚数', kind: 'float', min: 0, max: 100000 },
    { key: 'menzen_tenpai_abs', name: '立直/默听期望听牌绝对枚数', kind: 'float', min: 0, max: 100000 },
    { key: 'furo_ron_score', name: '副露荣和期望打点', kind: 'float', min: 0, max: 100000 },
    { key: 'furo_tsumo_score', name: '副露自摸期望打点', kind: 'float', min: 0, max: 100000 },
    { key: 'riichi_ron_score', name: '立直荣和期望打点', kind: 'float', min: 0, max: 100000 },
    { key: 'riichi_tsumo_score', name: '立直自摸期望打点', kind: 'float', min: 0, max: 100000 },
    { key: 'damaten_ron_score', name: '默听荣和期望打点', kind: 'float', min: 0, max: 100000 },
    { key: 'damaten_tsumo_score', name: '默听自摸期望打点', kind: 'float', min: 0, max: 100000 },
    { key: 'riichi_others_danger_suji', name: '立直家（他家）危险筋组数量', kind: 'int', min: -1, max: 18 },
    { key: 'riichi_others_danger_ryanmen', name: '立直家（他家）危险两面组数', kind: 'int', min: -1, max: 288 }
  ];

  /** 副露组数（拔北不计，暗杠计入） */
  function meldCount(p) {
    var n = 0, i, c;
    for (i = 0; i < p.melds.length; i++) { c = p.melds[i].callType; if (OPEN_CALLS[c]) { n += 1; } }
    return n;
  }
  function isRiichi(p) { return !!(p.riichi || p.riichiPending); }

  /** 按分数降序算顺位；同分时按自风顺序（相对起家的座次）排先 */
  function calcRank(scores, oya) {
    var order = [0, 1, 2, 3].sort(function (a, b) {
      if (scores[a] !== scores[b]) { return scores[b] - scores[a]; }
      return ((a - oya + 4) % 4) - ((b - oya + 4) % 4);
    });
    var rank = [0, 0, 0, 0];
    for (var i = 0; i < order.length; i++) { rank[order[i]] = i + 1; }
    return rank;
  }

  /** 供托 = 立直棒×1000 + 本场×300 */
  function kyotakuTotal(st) { return st.kyotaku * 1000 + st.honba * 300; }

  /** 从当前帧状态 st 提取 16 个特征（视角 = seat） */
  function extract(st, seat) {
    var oya = st.oya, me = st.players[seat], others = [], i, s, myMelds, othMelds = {}, othRiichi = 0, othCnt = 0, oth2 = 0, oth3 = 0;
    for (s = 0; s < 4; s++) { if (s !== seat) { others.push(s); } }
    myMelds = meldCount(me);
    for (i = 0; i < others.length; i++) {
      s = others[i];
      othMelds[s] = meldCount(st.players[s]);
      if (isRiichi(st.players[s])) { othRiichi += 1; }
      if (othMelds[s] > 0) { othCnt += 1; }
      if (othMelds[s] >= 2) { oth2 += 1; }
      if (othMelds[s] >= 3) { oth3 += 1; }
    }
    var oyaRiichi = NO, oyaMeld = NO, oyaMeldN = 0;
    if (oya !== seat) {
      oyaMeldN = meldCount(st.players[oya]);
      oyaRiichi = isRiichi(st.players[oya]) ? YES : NO;
      oyaMeld = oyaMeldN > 0 ? YES : NO;
    }
    return {
      joukyoku: MJLOG.joukyokuLabel(st.round),
      minami3: st.round >= 6 ? YES : NO,
      junme: me.turns + 1,   /* 巡目 = 该家已出牌次数 + 1（当前这一手） */
      kyotaku: kyotakuTotal(st),
      oyako: seat === oya ? DEALER : CHILD,
      rank: calcRank(st.scores, oya)[seat],
      riichi_self: isRiichi(me) ? YES : NO,
      meld_self: myMelds > 0 ? YES : NO,
      meld_self_n: myMelds,
      riichi_others_n: othRiichi,
      meld_others_n: othCnt,
      meld2_others_n: oth2,
      meld3_others_n: oth3,
      oya_riichi: oyaRiichi,
      oya_meld: oyaMeld,
      oya_meld_n: oyaMeldN
    };
  }

  /** 组装一个打点行（16 特征 + 事实字段）。kind = draw / chi / pon；drawn = 摸到的牌或 null。
      字段与 Python 端 mjscore/feats.py make_record() 一致 */
  function makeRecord(game, roundIndex, evIndex, st, seat, kind, drawn) {
    var logId = game.logId || '';
    var me = st.players[seat];
    var melds = [], i;
    for (i = 0; i < me.melds.length; i++) {
      melds.push([me.melds[i].callType, me.melds[i].tiles.slice()]);
    }
    var names = [], sc = [];
    for (i = 0; i < 4; i++) { names.push(st.players[i].name); sc.push(st.scores[i]); }
    return {
      log_id: logId,
      url: 'http://tenhou.net/0/?log=' + logId + '&tw=0',
      round_index: roundIndex,
      frame_index: evIndex + 1,
      ev_index: evIndex,
      seat: seat,
      round: st.round,
      honba: st.honba,
      kyotaku_raw: st.kyotaku,
      score: me.score,
      oya: st.oya,
      joukyoku: MJLOG.joukyokuLabel(st.round),
      wind: REPLAY.seatWind(seat, st.oya),
      junme: me.turns + 1,   /* 巡目 = 该家已出牌次数 + 1（当前这一手） */
      dealer: seat === st.oya ? 1 : 0,
      rank: calcRank(st.scores, st.oya)[seat],
      kyotaku_total: kyotakuTotal(st),
      drawn: drawn,
      hand_size: me.hand.length,
      kind: kind,
      tiles: me.hand.slice(),
      melds: melds,
      dora: st.dora.slice(),
      scores: sc,
      names: names,
      feats: extract(st, seat)
    };
  }

  /** 非自摸的摸牌帧（kind='draw'） */
  function drawRecord(game, roundIndex, evIndex, st, ev, seat) {
    return makeRecord(game, roundIndex, evIndex, st, seat, 'draw', ev.tile);
  }

  /** 吃 / 碰之后「等待出牌」的那一帧（kind = 'chi' / 'pon'） */
  function callRecord(game, roundIndex, evIndex, st, ev, seat) {
    return makeRecord(game, roundIndex, evIndex, st, seat, ev.callType, null);
  }

  /** 本局所有打点行（非自摸的摸牌帧 + 吃/碰后等待出牌的帧） */
  function recordsForRound(game, roundIndex) {
    var events = game.rounds[roundIndex].events;
    var st = REPLAY.initialState(game, roundIndex);
    var out = [], i, ev, nxt;
    for (i = 0; i < events.length; i++) {
      ev = events[i];
      REPLAY.applyEvent(st, ev);
      st.evIndex = i;
      if (ev.type === 'draw') {
        nxt = i + 1 < events.length ? events[i + 1] : null;
        if (nxt && nxt.type === 'agari' && nxt.winner === ev.player && nxt.fromWho === ev.player) { continue; }
        out.push(drawRecord(game, roundIndex, i, st, ev, ev.player));
      } else if (ev.type === 'call' && (ev.callType === 'chi' || ev.callType === 'pon')) {
        /* 摆出副露牌后、等待出牌的那一帧。暗杠 / 加杠 / 大明杠没有这一帧（它们紧接着摸岭上牌）。 */
        out.push(callRecord(game, roundIndex, i, st, ev, ev.player));
      }
    }
    return out;
  }

  function recordsForGame(game) {
    var out = [], ri;
    for (ri = 0; ri < game.rounds.length; ri++) { out = out.concat(recordsForRound(game, ri)); }
    return out;
  }

  /** 检索结果条目名：牌谱特征码 + 局况 + 本场 + 巡目 + 风位 */
  function rowLabel(rec) {
    return rec.log_id + ' ' + rec.joukyoku + ' ' + rec.honba + '本場 ' + rec.junme + '巡目 ' + rec.wind + '家';
  }

  return { FEATURES: FEATURES, meldCount: meldCount, calcRank: calcRank, kyotakuTotal: kyotakuTotal,
           extract: extract, makeRecord: makeRecord, drawRecord: drawRecord, callRecord: callRecord,
           recordsForRound: recordsForRound,
           recordsForGame: recordsForGame, rowLabel: rowLabel };
});