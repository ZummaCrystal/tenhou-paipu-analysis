/* mjsfeat.js — 特征打点（浏览器 + Node 通用，零依赖）
 *
 * 打点对象：**非自摸的摸牌帧**；打点视角：**摸牌者自己**
 * 本文件与 Python 端 mjscore/feats.py 的「第一类特征」、口径、字段名逐项对齐，
 * test/mjscore_test.py 会交叉校验「Node 打点」与「Python 打点」的结果完全一致。
 *
 * 第 21 轮（m02959）把 17 个「第二类特征」（3 个向听数 + 12 个期望枚数/打点 + 2 个危险筋组·两面组）
 * 也登记在 FEATURES 里：浏览器只用它们的 key / 中文名 / 值域（检索下拉 + 帧特征面板显示）；
 * 这些值由 Python 端算好后入库（js 侧没有实现；--tool node 时由 cli.py 用 Python 补列）。
 * 三个向听数的内部取值 3 表示「>=3」，界面上一律显示成 >=3（用户 m04115②）。
 * 第 52 轮（用户 m04556 ②）把原来的第一类特征「NAGA决策」改名「NAGA-平衡 分析」并移到
 * 「第零类特征」；第 59 轮（用户 m05937 ②）补齐 Mortal 的避四 / 争一；第 74 轮（用户 m09507）
 * 再补新版 NAGA 的避四（アナンタ）/ 争一（ウロボロス），共 7 项：NAGA-平衡 分析 /
 * NAGA-超副露 分析 / NAGA-避四 分析 / NAGA-争一 分析 / Mortal-4.1-避四 分析 /
 * Mortal-4.1-平衡 分析 / Mortal-4.1-争一 分析：
 * 值由 cli.fill_ai 按牌谱来源补（js 侧没有报告解析器），这里只登记定义。
 * 第 36 轮（用户 m02227 ②、m02356）新增第一类特征「立直家（他家）一发巡」（是/否，
 * = 另外三家的「一发」状态逻辑或）：
 * 状态由 web/js/replay.js 维护（与 mjscore/replay.py 同款），extract() 直接读 st.ippatsu。
 * 用户 m02357 规定顺序：NAGA决策 置首，「立直家（他家）一发巡」紧随「立直家（他家）数量」之后。
 * 第 63 轮（用户 m07289）：原来的第一类特征「等待鸣牌」单独编为**第三类特征**（THIRD_FEATURES）——
 * 不进检索页的特征词条下拉、也不在「当前帧特征」面板里与一、二类一起展示；检索改用必选单选
 * 「出牌 / 鸣牌响应」。同轮把 kind='wait' 的行改成「**可能被他家鸣牌**的那一家各一行」
 * （判据见 responders()：碰/大明杠 = 非立直家同种 ≥2；吃 = 只有下家、且过食替禁止），
 * 与 mjscore/feats.py 的 responders() 逐项对齐。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(require('./mjlog.js'), require('./replay.js')); }
  else { root.MJSFEAT = factory(root.MJLOG, root.REPLAY); }
})(typeof self !== 'undefined' ? self : this, function (MJLOG, REPLAY) {
  'use strict';

  var YES = '是', NO = '否', DEALER = '亲家', CHILD = '子家';
  /* 会破坏「门前」的副露（拔北不计入副露数量，暗杠计入） */
  var OPEN_CALLS = { chi: 1, pon: 1, kakan: 1, daiminkan: 1, ankan: 1 };

  /* 第零类特征 5 项（第 52 轮 / 第 59 轮，用户 m04556 ② / m05937 ②）：牌谱文件里含哪些 AI 模型的
     分析结果，值「是 / 否」。天凤牌谱五项都是「否」；NAGA / Mortal 报告按报告里的模型标签判定
     （规范名见 mjscore/ai_models.py）。
     第零类**不参与**「添加特征词条再填取值」的选取方式 —— 检索走四种互斥方案（用户 m04556 ③）；
     播放界面也不把它列进「当前帧特征」面板（用户 m05937 ②，见 app.js 的 renderFeatPanel）。 */
  var AI_FEATURES = [
    { key: 'ai_balance', name: 'NAGA-平衡 分析', kind: 'enum', values: [YES, NO] },
    { key: 'ai_superhuro', name: 'NAGA-超副露 分析', kind: 'enum', values: [YES, NO] },
    { key: 'ai_naga_avoid4', name: 'NAGA-避四 分析', kind: 'enum', values: [YES, NO] },
    { key: 'ai_naga_aggressive', name: 'NAGA-争一 分析', kind: 'enum', values: [YES, NO] },
    { key: 'ai_mortal41a', name: 'Mortal-4.1-避四 分析', kind: 'enum', values: [YES, NO] },
    { key: 'ai_mortal41b', name: 'Mortal-4.1-平衡 分析', kind: 'enum', values: [YES, NO] },
    { key: 'ai_mortal41c', name: 'Mortal-4.1-争一 分析', kind: 'enum', values: [YES, NO] }
  ];

  /* 特征注册表：与 mjscore/feats.py 的 FEATURES 一致（key / 中文名 / 值域）。
     顺序 = 第零类 7 项（AI_FEATURES）→ 第一类 17 项 → 第二类 17 项 → 第三类 1 项（共 42 项）。
     第一类 17 项：局况 … 顺位 → 自家立直状态 → …
     立直家（他家）数量 → 立直家（他家）一发巡 → 副露家（他家）数量 … 亲家（他家）副露数量。 */
  var FIRST_FEATURES = [
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
    /* ---- 立直家（他家）一发巡（第 36 轮，用户 m02227 ② / m02356 改名 / m02357 位置）---- */
    { key: 'ippatsu', name: '立直家（他家）一发巡', kind: 'enum', values: [YES, NO] },
    { key: 'meld_others_n', name: '副露家（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'meld2_others_n', name: '两副露以上（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'meld3_others_n', name: '三副露以上（他家）数量', kind: 'int', min: 0, max: 3 },
    { key: 'oya_riichi', name: '亲家（他家）立直状态', kind: 'enum', values: [YES, NO] },
    { key: 'oya_meld', name: '亲家（他家）副露状态', kind: 'enum', values: [YES, NO] },
    { key: 'oya_meld_n', name: '亲家（他家）副露数量', kind: 'int', min: 0, max: 4 }
  ];

  /* ---- 第二类特征（第 21 轮，m02959）：值由 Python 端算好后入库，这里只登记定义 ---- */
  var SECOND_FEATURES = [
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

  /* 第三类特征 1 项（第 63 轮，用户 m07289 的补充要求）：「等待鸣牌」不适合作为普通第一类特征 ——
     它单独编为第三类，**不进检索页的特征词条下拉**、也**不在「当前帧特征」面板里与一、二类一起展示**；
     检索改用第零类框右端的必选单选「出牌」（f_meld_wait = 否）/「鸣牌响应」（= 是），默认「出牌」。 */
  var THIRD_FEATURES = [
    { key: 'meld_wait', name: '等待鸣牌', kind: 'enum', values: [YES, NO] }
  ];

  /* 顺序 = 第零类 7 项 + 第一类 17 项 + 第二类 17 项 + 第三类 1 项
     （与 mjscore/feats.py 的 FEATURES 一致，共 42 项） */
  var FEATURES = AI_FEATURES.concat(FIRST_FEATURES).concat(SECOND_FEATURES).concat(THIRD_FEATURES);

  /** 「立直家（他家）一发巡」（用户 m02227 ② / m02356）：另外三家只要有一家有「一发」状态就是 是 */
  function ippOthers(st, others) {
    var ipp = st.ippatsu || [false, false, false, false];
    for (var i = 0; i < others.length; i++) { if (ipp[others[i]]) { return YES; } }
    return NO;
  }

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

  /* ---------------- 「可能被他家鸣牌」判据（第 63 轮，用户 m07289 ①②）---------------- */

  /** {kind: 张数}（红 5 与普通 5 同 kind） */
  function kindCounts(tiles) {
    var out = {}, i, k;
    tiles = tiles || [];
    for (i = 0; i < tiles.length; i++) {
      k = MJLOG.kindOf(tiles[i]);
      if (k === null || k === undefined) { continue; }
      out[k] = (out[k] || 0) + 1;
    }
    return out;
  }

  /** 吃这张牌时另外两张牌可能的 kind（返回 [[a, b]]，a < b）。字牌不能吃。 */
  function chiPairs(kind) {
    if (kind === null || kind === undefined || kind >= 27) { return []; }
    var num = kind % 9, out = [];
    if (num >= 2) { out.push([kind - 2, kind - 1]); }
    if (num >= 1 && num <= 7) { out.push([kind - 1, kind + 1]); }
    if (num <= 6) { out.push([kind + 1, kind + 2]); }
    return out;
  }

  /** 吃了 a、b 两张之后不能立刻打出的牌（食替禁止，用户 m07289 ②）：
      「能与被吃的两张牌组成顺子」的那些 kind（其中就含被吃进来的那张牌本身）。 */
  function chiForbidden(a, b) {
    var lo = a < b ? a : b, hi = a < b ? b : a, out = {};
    if (hi === lo + 1) {
      if (lo % 9 >= 1) { out[lo - 1] = 1; }
      if (hi % 9 <= 7) { out[hi + 1] = 1; }
    } else if (hi === lo + 2) {
      out[lo + 1] = 1;
    }
    return out;
  }

  /** 能否吃这张牌：手牌里有两张能凑成顺子，且吃后还剩至少一张可以打出的牌（食替禁止）。 */
  function canChi(hand, kind) {
    var cnt = kindCounts(hand), pairs = chiPairs(kind), i, a, b, rest, bad, k;
    for (i = 0; i < pairs.length; i++) {
      a = pairs[i][0]; b = pairs[i][1];
      if ((cnt[a] || 0) < 1 || (cnt[b] || 0) < 1) { continue; }
      rest = {};
      for (k in cnt) { rest[k] = cnt[k]; }
      rest[a] -= 1; rest[b] -= 1;
      bad = chiForbidden(a, b);
      for (k in rest) { if (rest[k] > 0 && !bad[k]) { return true; } }
    }
    return false;
  }

  /** 能否碰这张牌（同种 ≥2 张；大明杠要 3 张，但「碰」已经构成可能鸣牌）。 */
  function canPon(hand, kind) {
    if (kind === null || kind === undefined) { return false; }
    return (kindCounts(hand)[kind] || 0) >= 2;
  }

  /** 打出 kind 这张牌之后**可能**鸣牌的所有家（用户 m07289 ①②）。
      判据 = 「可能被他家鸣牌」，与牌谱里实际有没有出现鸣牌无关：
        * 立直家（含刚宣告、还没打出牌的）不能鸣牌；
        * 任何一家手里同种牌 ≥2 张 ⇒ 可能碰 / 大明杠；
        * 只有下家 (discarder + 1) % 4 可能吃，且要过食替禁止（chiForbidden）。
      返回升序座位号列表（不含出牌者）。 */
  function responders(st, discarder, kind) {
    var out = [], s, pl, hand;
    if (kind === null || kind === undefined || !st || !st.players) { return out; }
    for (s = 0; s < 4; s++) {
      if (s === discarder) { continue; }
      pl = st.players[s];
      if (isRiichi(pl)) { continue; }
      hand = pl.hand || [];
      if (canPon(hand, kind) || (s === (discarder + 1) % 4 && canChi(hand, kind))) { out.push(s); }
    }
    return out;
  }

  /** 这张牌有没有可能被他家鸣牌（用户 m07289 ① 的关键帧判据）。 */
  function meldPossible(st, discarder, kind) { return responders(st, discarder, kind).length > 0; }

  /** 从当前帧状态 st 提取第一类 17 项 + 第三类 1 项（视角 = seat = 当前决策者）；
      第零类 5 项由 cli.fill_ai 按帧补（用户 m06323 ①），第二类 17 项由 Python 端算。
      kind = 这一帧的打点种类（draw / chi / pon / wait，用户 m06832 / m07289） */
  function extract(st, seat, kind) {
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
      meld_wait: (kind === 'wait') ? YES : NO,   /* 第三类「等待鸣牌」（用户 m07289） */
      riichi_self: isRiichi(me) ? YES : NO,
      meld_self: myMelds > 0 ? YES : NO,
      meld_self_n: myMelds,
      riichi_others_n: othRiichi,
      ippatsu: ippOthers(st, others),   /* 立直家（他家）一发巡：紧随「立直家（他家）数量」（用户 m02357） */
      meld_others_n: othCnt,
      meld2_others_n: oth2,
      meld3_others_n: oth3,
      oya_riichi: oyaRiichi,
      oya_meld: oyaMeld,
      oya_meld_n: oyaMeldN
    };
  }

  /** 组装一个打点行（第一类 17 个 + 第三类 1 个特征 + 事实字段；第零类 5 项由 cli.fill_ai 补，
      第二类 17 项由 Python 端补）。kind = draw / chi / pon / wait；drawn = 摸到的牌或 null。
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
      feats: extract(st, seat, kind)
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

  /** 「鸣牌响应」的一行（kind='wait'，seat = **可能鸣牌**的那一家，用户 m07289） */
  function waitRecord(game, roundIndex, evIndex, st, ev, seat) {
    return makeRecord(game, roundIndex, evIndex, st, seat, 'wait', null);
  }

  /** 本局所有打点行（非自摸的摸牌帧 + 吃/碰后等待出牌的帧 + 鸣牌响应帧） */
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
      } else if (ev.type === 'discard') {
        /* 鸣牌响应帧（用户 m07289 ①②）：判据 =「**可能**被他家鸣牌」（与牌谱里实际有没有鸣牌无关）——
           碰 / 大明杠 = 非立直家手里同种 ≥2 张；吃 = 只有下家、且吃后还剩可打出的牌（食替禁止）。
           可能鸣牌的那一家各出一行（不再是固定 3 行）；判据与播放视图的关键帧完全一致。 */
        var waitKind = MJLOG.kindOf(ev.tile);
        var waitSeats = responders(st, ev.player, waitKind);
        for (var w = 0; w < waitSeats.length; w++) {
          out.push(waitRecord(game, roundIndex, i, st, ev, waitSeats[w]));
        }
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

  return { FEATURES: FEATURES, AI_FEATURES: AI_FEATURES,
           FIRST_FEATURES: FIRST_FEATURES, SECOND_FEATURES: SECOND_FEATURES,
           THIRD_FEATURES: THIRD_FEATURES,
           responders: responders, meldPossible: meldPossible,
           canChi: canChi, canPon: canPon, chiPairs: chiPairs, chiForbidden: chiForbidden,
           meldCount: meldCount, calcRank: calcRank, kyotakuTotal: kyotakuTotal,
           extract: extract, makeRecord: makeRecord, drawRecord: drawRecord, callRecord: callRecord,
           waitRecord: waitRecord,
           recordsForRound: recordsForRound,
           recordsForGame: recordsForGame, rowLabel: rowLabel };
});
