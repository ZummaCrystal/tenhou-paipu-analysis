/* ui.js — 把 replay 引擎产出的「帧状态(state)」渲染成 DOM
 *
 * 依赖：tiles.js（牌 id -> 素材/名称）、mjlog.js（局标签）。
 * 设计要点：
 *   - 无框架、无动画：每次渲染整块重建，切换帧＝重新渲染一次；
 *   - 四家面板统一按「自家视角」排版：抬头 -> 牌河 -> 手牌+副露（最外侧一行），
 *     再把整块旋转到自己的方位。旋转后牌面朝向、点数方向、牌河生长方向自动与真实牌桌一致；
 *   - 牌河 6 张一排、朝中心方向生长，CSS 预留 4 排高度；
 *   - 副露摆在手牌右侧（先鸣的靠右），被鸣的那张横放；被鸣走的牌仍留在牌河里用红框标出；
 *   - 中央只放「局数 / 供托 / 剩余牌数 / 宝牌指示牌 / 本局结果」，不再重复四家信息；
 *   - 所有交互由 app.js 绑定，本文件只负责画。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('./tiles.js'), require('./mjlog.js'));
  } else {
    root.UI = factory(root.Tiles, root.MJLOG);
  }
})(typeof self !== 'undefined' ? self : this, function (Tiles, MJLOG) {
  'use strict';

  /* 同 tiles.js 的 TILE_DIR：服务打开用网站根，file:// 用上一级 */
  var BACK_SRC = (typeof location !== 'undefined' && location.protocol === 'file:')
    ? '../media/tiles/back.svg' : '/media/tiles/back.svg';
  var WINDS = ['東', '南', '西', '北'];
  var CALL_NAME = { chi: '吃', pon: '碰', kakan: '加杠', daiminkan: '大明杠', ankan: '暗杠', nuki: '拔北' };
  var RIVER_COLS = 6;          /* 牌河每排张数 */
  var RIVER_ROWS = 4;          /* 牌河预留排数 */

  /* 天凤 log 的役 id（0..54）。未知 id 退化为「役#id」。 */
  var YAKU = {
    0: '門前清自摸和', 1: '立直', 2: '一発', 3: '槍槓', 4: '嶺上開花', 5: '海底摸月',
    6: '河底撈魚', 7: '平和', 8: '断幺九', 9: '一盃口', 10: '自風 東', 11: '自風 南',
    12: '自風 西', 13: '自風 北', 14: '場風 東', 15: '場風 南', 16: '場風 西',
    17: '場風 北', 18: '役牌 白', 19: '役牌 發', 20: '役牌 中', 21: '両立直',
    22: '七対子', 23: '混全帯幺九', 24: '一気通貫', 25: '三色同順', 26: '三色同刻',
    27: '三槓子', 28: '対々和', 29: '三暗刻', 30: '小三元', 31: '混老頭', 32: '二盃口',
    33: '純全帯幺九', 34: '混一色', 35: '清一色', 36: '人和', 37: '天和', 38: '地和',
    39: '大三元', 40: '四暗刻', 41: '四暗刻単騎', 42: '字一色', 43: '緑一色', 44: '清老頭',
    45: '九蓮宝燈', 46: '純正九蓮宝燈', 47: '国士無双', 48: '国士無双十三面',
    49: '大四喜', 50: '小四喜', 51: '四槓子', 52: '宝牌', 53: '里宝牌', 54: '赤宝牌'
  };

  function yakuName(id) { return YAKU[id] || ('役#' + id); }

  /* ------------------------------------------------------------ DOM 小工具 */
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = String(text); }
    return e;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }
  function addCls(e, cls) {
    if (!cls) { return; }
    var parts = String(cls).split(/\s+/);
    for (var i = 0; i < parts.length; i++) { if (parts[i]) { e.classList.add(parts[i]); } }
  }

  /**
   * 单张牌 -> <div class="tile"><img src=…></div>
   * opt: { big:bool, back:bool, cls:'a b', title:'…' }
   */
  function tileEl(id, opt) {
    opt = opt || {};
    var d = el('div', 'tile');
    if (opt.big) { d.classList.add('big'); }
    addCls(d, opt.cls);
    var img = el('img');
    img.draggable = false;
    if (id === null || id === undefined || opt.back) {
      d.classList.add('back');
      img.src = BACK_SRC;
      img.alt = '牌背';
    } else {
      img.src = Tiles.tileSrc(id);
      img.alt = Tiles.tileLabel(id);
      d.title = Tiles.tileLabel(id) + ' (id ' + id + ')';
    }
    d.appendChild(img);
    return d;
  }

  function tilesEl(ids, opt) {
    var box = el('div', 'tiles');
    for (var i = 0; i < ids.length; i++) { box.appendChild(tileEl(ids[i], opt)); }
    return box;
  }

  /* ------------------------------------------------------------ 副露 */
  /* 横放位置：来源 -> 该放第几张（rel = 来源座次 - 自己座次：3=上家 2=対面 1=下家） */
  /*   碰 / 加杠（共 3 张）：上家=第 1 张、対面=第 2 张、下家=第 3 张
   *   大明杠（共 4 张）    ：上家=第 1 张、対面=第 2 张、下家=第 4 张（永不横放第 3 张）
   *                          —— 按用户 m00483 指定的规则，不是 3 张时的位置照搬。
   *                          ⚠ 5 个测试牌谱里大明杠出现 0 次，此分支**未做真实数据验证**，
   *                            只在 test/apptest.js 里单测了下面这张映射表。
   *   吃：只能吃上家的牌，所以被吃的那张恒摆第 1 张（横放），另外两张按点数升序跟在后面。 */
  var MELD_ROT = { 3: 0, 2: 1, 1: 2 };  /* 碰 / 加杠：3 张 */
  var KAN_ROT  = { 3: 0, 2: 1, 1: 3 };  /* 大明杠：4 张（未做测试） */
  function rotIndexOf(m, list, seat) {
    if (m.callType === 'ankan' || m.callType === 'nuki') { return -1; }
    if (m.callType === 'chi') { return 0; }
    var rel = (m.from === null || m.from === undefined) ? 3 : ((m.from - seat + 4) % 4);
    var tbl = (m.callType === 'daiminkan') ? KAN_ROT : MELD_ROT;
    var r = tbl[rel];
    return (r === undefined) ? 0 : r;
  }
  function meldEl(m, seat) {
    var box = el('div', 'meld meld-' + m.callType);
    box.appendChild(el('span', 'meld-tag', CALL_NAME[m.callType] || m.callType));
    var t = el('div', 'tiles'), i, list, rot;
    if (m.callType === 'ankan') {
      /* 暗杠：第一、四张反扣，第二、三张正面朝上，全部竖放 */
      for (i = 0; i < m.tiles.length; i++) {
        t.appendChild(tileEl(m.tiles[i], { back: (i === 0 || i === m.tiles.length - 1) }));
      }
    } else if (m.callType === 'kakan') {
      /* 加杠：[0] 是加进去的那张，横着叠在原先碰出来的那张横牌上 */
      list = m.tiles.slice(1);
      rot = rotIndexOf(m, list, seat);
      for (i = 0; i < list.length; i++) {
        if (i === rot) {
          var stack = el('div', 'tile-stack');
          stack.appendChild(tileEl(list[i], { cls: 'rot' }));
          stack.appendChild(tileEl(m.tiles[0], { cls: 'rot added' }));
          t.appendChild(stack);
        } else {
          t.appendChild(tileEl(list[i]));
        }
      }
    } else {
      if (m.callType === 'chi') {
        /* 吃：被吃的那张横放摆在第 1 张（吃只可能来自上家），另外两张按点数升序跟在后面 */
        var rest = m.tiles.slice().sort(function (a, b) { return a - b; })
          .filter(function (id) { return id !== m.calledId; });
        list = (m.calledId === null || m.calledId === undefined) ? rest : [m.calledId].concat(rest);
      } else {
        list = m.tiles.slice();
      }
      rot = rotIndexOf(m, list, seat);
      for (i = 0; i < list.length; i++) {
        t.appendChild(tileEl(list[i], { cls: (i === rot ? 'rot' : '') }));
      }
    }
    box.appendChild(t);
    return box;
  }

  /* 座位 -> 旋转类。面板按自家视角排版，旋转后手牌自动落在最外侧：
   *   0 下（自家）不旋转 / 3 左（上家）顺时针 90° / 2 上（対面）180° / 1 右（下家）270° */
  var SEAT_ROT = { 0: 'r0', 1: 'r270', 2: 'r180', 3: 'r90' };
  var ROT_NAME = { r0: '下（自家）', r90: '左（上家）', r180: '上（対面）', r270: '右（下家）' };

  /**
   * 牌河：每 RIVER_COLS 张一排。DOM 里第 1 排在前、CSS 用 column 排列，
   * 让第 1 排贴着中央信息框，后续排朝外侧（手牌方向）生长（CSS 预留 RIVER_ROWS 排高度）。
   */
  function riverEl(river) {
    var box = el('div', 'p-river river');
    for (var r = 0; r < river.length; r += RIVER_COLS) {
      var row = el('div', 'river-row');
      var end = Math.min(r + RIVER_COLS, river.length);
      for (var c = r; c < end; c++) {
        var e = river[c], cls = [];
        if (e.tsumogiri) { cls.push('tsumogiri'); }
        if (e.riichi) { cls.push('rot'); }     /* 立直宣言牌：只横放，不加方框也不加文字 */
        if (e.called) { cls.push('called'); }   /* 被鸣走的牌：留在牌河里，用红框标出 */
        if (e.win) { cls.push('win'); }          /* 荣和的铳牌：留在放铳者牌河最后一张，用绿框标出（m00569 ①） */
        row.appendChild(tileEl(e.tile, { cls: cls.join(' ') }));
      }
      box.appendChild(row);
    }
    return box;
  }

  /* ------------------------------------------------------------ 玩家面板 */
  /**
   * renderPlayer(cellEl, state, seat, opts)
   * 依 DOM 顺序（即自家视角「从中心到外侧」）：抬头 -> 牌河 -> 手牌+副露
   */
  function renderPlayer(cellEl, st, seat, opts) {
    clear(cellEl);
    var pl = st.players[seat];
    var self = (seat === opts.selfSeat);
    /* 和了帧 / 流局帧是特例（m00569 ①②、m00635 ①）：只摊开 st.reveal 名单里的手牌，名单外的三家
     * （含自家）一律隐藏，与「隐藏他家手牌」按钮无关；下一局开始自动恢复用户选的显示/隐藏。
     * 流局帧的名单按流局种类算（荒牌流局 = 听牌家、流局満貫 = 満貫者、九種九牌 = 宣告者、
     * 四家立直 = 四家、四風連打 / 四槓散了 = 空即强制全隐藏），见 js/replay.js 的 case 'ryuukyoku'。
     * 这里只作用于手牌：副露任何时候都不隐藏（见下面 p-melds）。 */
    var hidden;
    if (st.phase === 'agari' || st.phase === 'ryuukyoku') {
      var rev = st.reveal || [];
      hidden = (rev.indexOf(seat) < 0);
    } else {
      hidden = opts.hideOthers && !self;
    }

    var rot = el('div', 'p-rot ' + SEAT_ROT[seat]);
    rot.title = (pl.name || '') + ' · ' + ROT_NAME[SEAT_ROT[seat]];

    /* ① 抬头：风位 + 当前点数（整块随面板旋转，所以四家各自的文字朝向自己） */
    var head = el('div', 'p-head');
    head.appendChild(el('span', 'wind', WINDS[(seat - st.oya + 4) % 4]));
    head.appendChild(el('span', 'p-score', st.scores[seat]));
    head.appendChild(el('span', 'p-name', pl.name));
    if (seat === st.oya) { head.appendChild(el('span', 'badge oya', '親')); }
    if (pl.riichi) { head.appendChild(el('span', 'badge riichi', '立直')); }
    else if (pl.riichiPending) { head.appendChild(el('span', 'badge', '立直宣告')); }
    rot.appendChild(head);

    /* ② 牌河（靠近中心一侧） */
    rot.appendChild(riverEl(pl.river));

    /* ③④ 手牌 + 副露（最外侧一行；副露在手牌右侧。摸到的牌单独放在手牌末端） */
    /* 摸到的牌单独摆在手牌末端；和了帧也照上一帧的摆法显示（m00569 ②：不插进手牌） */
    var drawn = (st.drawn && st.drawn.player === seat) ? st.drawn.tile : null;
    var winTile = (st.result && st.result.type === 'agari' && st.result.winner === seat)
      ? st.result.winTile : null;
    var rest = pl.hand.slice(), k;
    if (drawn !== null) { k = rest.indexOf(drawn); if (k >= 0) { rest.splice(k, 1); } }
    rest = Tiles.sortHand(rest);

    var hr = el('div', 'p-hand');
    var hb = el('div', 'tiles');
    for (var j = 0; j < rest.length; j++) {
      hb.appendChild(tileEl(rest[j], {
        big: self, back: hidden,
        cls: (winTile !== null && rest[j] === winTile) ? 'win' : ''
      }));
    }
    hr.appendChild(hb);
    if (drawn !== null) {
      var db = el('div', 'tiles drawn');
      db.appendChild(tileEl(drawn, {
        big: self, back: hidden,
        cls: (winTile !== null && drawn === winTile) ? 'win' : ''
      }));
      hr.appendChild(db);
    }
    /* 副露在手牌右侧：DOM 里倒序排（最后一个是先鸣的 = 最右），后鸣的依次向左延伸 */
    var bottom = el('div', 'p-bottom');
    bottom.appendChild(hr);
    if (pl.melds.length) {
      var mr = el('div', 'p-melds');
      for (var mi = pl.melds.length - 1; mi >= 0; mi--) { mr.appendChild(meldEl(pl.melds[mi], seat)); }
      bottom.appendChild(mr);
    }
    rot.appendChild(bottom);

    cellEl.appendChild(rot);
  }

  /* ------------------------------------------------------------ 中央信息 */
  /** 只放 局数 / 供托 / 剩余牌数 / 宝牌指示牌 / 本局结果 —— 四家信息已移到各家面板 */
  function renderCenter(cellEl, st, opts) {
    clear(cellEl);
    var box = el('div', 'center');
    var lab = MJLOG.roundLabel(st.round);

    box.appendChild(el('div', 'c-round', lab.bakaze + lab.kyoku));
    if (st.honba) { box.appendChild(el('div', 'c-honba', st.honba + ' 本場')); }

    /* m00635 ②：本場 -> 供托 -> 剩余牌数（供托与剩余牌数的位置按用户要求互换） */
    var ky = el('div', 'c-kyotaku');
    ky.appendChild(el('span', 'c-lbl', '供托'));
    for (var i = 0; i < st.kyotaku; i++) { ky.appendChild(el('span', 'stick')); }
    ky.appendChild(el('span', 'c-v', String(st.kyotaku)));
    box.appendChild(ky);

    var left = el('div', 'c-left');
    left.appendChild(el('span', 'c-x', 'x' + st.tilesLeft));
    left.appendChild(el('span', 'c-lbl', '剩余牌数'));
    box.appendChild(left);

    var dora = el('div', 'c-dora');
    dora.appendChild(el('span', 'c-lbl', '宝牌指示牌'));
    dora.appendChild(tilesEl(st.dora));
    box.appendChild(dora);

    if (st.result) { box.appendChild(resultEl(st.result, st)); }

    cellEl.appendChild(box);
  }

  /** 座位号数组 -> 按「東 -> 南 -> 西 -> 北」排好序的「東家 / 南家 …」文本数组（m00635 ① 用） */
  function seatsByWind(seats, st) {
    var oya = (st && st.oya) || 0;
    return seats.slice().sort(function (a, b) {
      return ((a - oya + 4) % 4) - ((b - oya + 4) % 4);
    }).map(function (s) { return WINDS[(s - oya + 4) % 4] + '家'; });
  }

  function resultEl(ev, st) {
    var box = el('div', 'c-result');
    if (ev.type === 'agari') {
      var tsumo = (ev.winner === ev.fromWho);
      var oya = (st && st.oya) || 0;
      var wWin = WINDS[(ev.winner - oya + 4) % 4] + '家';
      var wFrom = WINDS[(ev.fromWho - oya + 4) % 4] + '家';
      box.appendChild(el('div', 'c-result-title',
        tsumo ? (wWin + ' 自摸和了') : (wFrom + ' 放铳 ' + wWin)));
      /* mjlog 的 yaku="id,翻,id,翻,…" -> [[id,翻],…] */
      var names = [], j, y;
      if (ev.yaku && ev.yaku.length) {
        for (j = 0; j < ev.yaku.length; j++) {
          y = ev.yaku[j];
          /* m01212：宝牌(52)/里宝牌(53)/赤宝牌(54) 的番数就是张数，0 张（如没中里宝）时不显示这个条目 */
          if (y && y.length && !y[1] && y[0] >= 52 && y[0] <= 54) { continue; }
          if (y && y.length) { names.push(yakuName(y[0]) + (y[1] ? '(' + y[1] + ')' : '')); }
          else { names.push(yakuName(y)); }
        }
      }
      if (ev.yakuman && ev.yakuman.length) {
        for (j = 0; j < ev.yakuman.length; j++) { names.push(yakuName(ev.yakuman[j]) + '(役満)'); }
      }
      if (names.length) { box.appendChild(el('div', 'c-yaku', names.join(' / '))); }
      var ten = ev.ten || [];
      if (ten.length) { box.appendChild(el('div', 'c-ten', ten[0] + ' 符 / ' + ten[1] + ' 点')); }
      if (ev.dora && ev.dora.length) {
        var d = el('div', 'c-dora-show');
        d.appendChild(el('span', 'c-ten', '宝牌指示牌 '));
        d.appendChild(tilesEl(ev.dora));
        box.appendChild(d);
      }
      if (ev.ura && ev.ura.length) {
        var u = el('div', 'c-dora-show');
        u.appendChild(el('span', 'c-ten', '里宝指示牌 '));
        u.appendChild(tilesEl(ev.ura));
        box.appendChild(u);
      }
    } else if (ev.type === 'ryuukyoku') {
      /* m00635 ① 中央信息：
       *   途中流局 -> 第 1 行「流局」+ 第 2 行流局种类（如「四風連打」）
       *   荒牌流局 -> 第 1 行「荒牌流局」+ 第 2 行「東家 南家 流局听牌」
       *   流局満貫 -> 同上，第 2 行「東家 西家 流局満貫」 */
      var rkName = MJLOG.REASON_NAME ? MJLOG.REASON_NAME[ev.reason || ''] : '';
      if (rkName && ev.reason !== 'nm') {
        box.appendChild(el('div', 'c-result-title', '流局'));
        box.appendChild(el('div', 'c-ten', rkName));
      } else {
        box.appendChild(el('div', 'c-result-title', '荒牌流局'));
        var who = null;
        if (ev.reason === 'nm') {
          if (ev.nagashi && ev.nagashi.length) { who = seatsByWind(ev.nagashi, st).join(' ') + ' 流局満貫'; }
        } else if (ev.tenpai && ev.tenpai.length) {
          who = seatsByWind(ev.tenpai, st).join(' ') + ' 流局听牌';
        }
        if (who) { box.appendChild(el('div', 'c-ten', who)); }
      }
    }
    return box;
  }

  /* ------------------------------------------------------------ 整块牌桌 */
  /**
   * renderBoard(boardEl, state, opts)
   * opts: { selfSeat: 0, hideOthers: bool }
   */
  function renderBoard(boardEl, st, opts) {
    opts = opts || {};
    if (opts.selfSeat === undefined) { opts.selfSeat = 0; }
    clear(boardEl);

    var layout = [
      ['top', 2], ['left', 3], ['center', null], ['right', 1], ['bottom', 0]
    ];
    for (var i = 0; i < layout.length; i++) {
      var area = layout[i][0], seat = layout[i][1];
      var cell = el('div', 'cell cell-' + area);
      if (seat === null) { renderCenter(cell, st, opts); }
      else { renderPlayer(cell, st, seat, opts); }
      boardEl.appendChild(cell);
    }
  }

  /* ------------------------------------------------------------ 事件列表 */
  /** frames: REPLAY.buildFrames 的结果；cur: 当前帧下标 */
  function renderEventList(bodyEl, frames, cur) {
    var keepScroll = bodyEl.scrollTop;
    clear(bodyEl);
    for (var i = 0; i < frames.length; i++) {
      var row = el('div', 'ev-row' + (i === cur ? ' cur' : ''));
      row.setAttribute('data-idx', String(i));
      row.appendChild(el('span', 'ev-idx', i));
      row.appendChild(el('span', 'ev-text', frames[i].state.desc || ''));
      bodyEl.appendChild(row);
    }
    /* 让当前行可见，但不要整页乱跳 */
    var curRow = bodyEl.querySelector('.ev-row.cur');
    if (curRow) {
      var top = curRow.offsetTop - bodyEl.offsetTop;
      var h = bodyEl.clientHeight;
      if (top < bodyEl.scrollTop || top + curRow.offsetHeight > bodyEl.scrollTop + h) {
        bodyEl.scrollTop = Math.max(0, top - h / 2);
      } else {
        bodyEl.scrollTop = keepScroll;
      }
    }
  }

  return {
    el: el, clear: clear, tileEl: tileEl, tilesEl: tilesEl,
    renderBoard: renderBoard, renderCenter: renderCenter, renderPlayer: renderPlayer,
    renderEventList: renderEventList, riverEl: riverEl,
    rotIndexOf: rotIndexOf, MELD_ROT: MELD_ROT, KAN_ROT: KAN_ROT,
    yakuName: yakuName, CALL_NAME: CALL_NAME, YAKU: YAKU,
    SEAT_ROT: SEAT_ROT, RIVER_COLS: RIVER_COLS, RIVER_ROWS: RIVER_ROWS
  };
});
