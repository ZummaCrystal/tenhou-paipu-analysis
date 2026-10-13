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
  var RIVER_TILE_ROWS = 3;     /* 牌最多占几排：第 13 张起全在第 3 排向右延伸（用户 m08576） */
  var RIVER_ROWS = 4;          /* 牌河预留排数（第 4 排只留白：布局固定，手牌位置不跳） */

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
  /* nextIds = 本帧主视角「准备杠（暗杠 / 加杠）」的牌 id 列表（用户 m08178）：落在副露区的
   * 那几张也要框细红框（加杠 = 手里 1 张 + 副露区那 3 张）。打牌那一张不在这里，由手牌循环处理。 */
  function meldEl(m, seat, nextIds) {
    var box = el('div', 'meld meld-' + m.callType);
    /* 副露区不再写「吃 / 碰 / 杠」文字（用户 m04160 ②）：牌型本身 + 牌河里的红框已足够，
     * 文字标签只会占宽度。副露种类仍在 DOM 的 class（meld-chi / meld-pon / …）与事件列表里。 */
    var t = el('div', 'tiles'), i, list, rot;
    var nx = nextIds || [];
    function ncls(id) { return (nx.indexOf(id) >= 0) ? ' next' : ''; }
    if (m.callType === 'ankan') {
      /* 暗杠：第一、四张反扣，第二、三张正面朝上，全部竖放 */
      for (i = 0; i < m.tiles.length; i++) {
        t.appendChild(tileEl(m.tiles[i], {
          back: (i === 0 || i === m.tiles.length - 1), cls: ncls(m.tiles[i]) }));
      }
    } else if (m.callType === 'kakan') {
      /* 加杠：[0] 是加进去的那张，横着叠在原先碰出来的那张横牌上 */
      list = m.tiles.slice(1);
      rot = rotIndexOf(m, list, seat);
      for (i = 0; i < list.length; i++) {
        if (i === rot) {
          var stack = el('div', 'tile-stack');
          stack.appendChild(tileEl(list[i], { cls: 'rot' + ncls(list[i]) }));
          stack.appendChild(tileEl(m.tiles[0], { cls: 'rot added' + ncls(m.tiles[0]) }));
          t.appendChild(stack);
        } else {
          t.appendChild(tileEl(list[i], { cls: ncls(list[i]) }));
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
        t.appendChild(tileEl(list[i], { cls: (i === rot ? 'rot' : '') + ncls(list[i]) }));
      }
    }
    box.appendChild(t);
    return box;
  }

  /* 座位 -> 旋转类。面板按自家视角排版，旋转后手牌自动落在最外侧：
   *   0 下（自家）不旋转 / 3 左（上家）顺时针 90° / 2 上（対面）180° / 1 右（下家）270° */
  var SEAT_ROT = { 0: 'r0', 1: 'r270', 2: 'r180', 3: 'r90' };
  var ROT_NAME = { r0: '下（自家）', r90: '左（上家）', r180: '上（対面）', r270: '右（下家）' };

  /* 大字（vocalization）的「展示位置 → 桌面百分比坐标」（用户 m03978 ②）。
   * 官方 viewer 的 vocalization_pos = [[350,500],[560,320],[350,160],[140,320]]、桌面 700×650、
   * 字号 60 ÷ 牌高 40 = 1.5 倍牌高（见 build/_scratch/naga_samples/_viewer_index.js 的 renderBa）。
   * 下标 = 展示位置：0 下（主视角）/ 1 右 / 2 上 / 3 左 —— 与 .board 的 grid 区域一一对应。 */
  var VOCAL_POS = [[50, 76.92], [80, 49.23], [50, 24.62], [20, 49.23]];

  /**
   * 牌河：每排最多 RIVER_COLS 张、最多 RIVER_TILE_ROWS 排（用户 m08576）。
   * 前 6 张进第 1 排、再 6 张进第 2 排，**第 13 张起全部放在第 3 排、向右延伸**（不再放入第 4 排）；
   * CSS 仍按 RIVER_ROWS 排预留高度 ⇒ 牌河变长时手牌位置不跳（m01386）。
   * DOM 里第 1 排在前、CSS 用 column 排列，让第 1 排贴着中央信息框、后续排朝外侧（手牌方向）生长。
   * markLast = true 时把这一家的最后一张牌加黄框（牌谱检索 / 全部浏览的「鸣牌响应局面」，
   * 用户 m07820 补充 2：主视角正在等着回应吃 / 碰 / 杠的那张被打出的牌）。
   */
  function riverEl(river, markLast) {
    var box = el('div', 'p-river river');
    var start = 0, rowNo = 0;
    while (start < river.length) {
      var row = el('div', 'river-row');
      /* 最后一排（第 RIVER_TILE_ROWS 排）把剩下的牌全部装下、不再折行（用户 m08576） */
      var end = (rowNo >= RIVER_TILE_ROWS - 1)
        ? river.length
        : Math.min(start + RIVER_COLS, river.length);
      for (var c = start; c < end; c++) {
        var e = river[c], cls = [];
        if (e.tsumogiri) { cls.push('tsumogiri'); }
        if (e.riichi) { cls.push('rot'); }     /* 立直宣言牌：只横放，不加方框也不加文字 */
        if (e.called) { cls.push('called'); }   /* 被鸣走的牌：留在牌河里，用红框标出 */
        if (e.win) { cls.push('win'); }          /* 荣和的铳牌：留在放铳者牌河最后一张，用绿框标出（m00569 ①） */
        if (markLast && c === river.length - 1) { cls.push('mark'); }   /* 黄框（用户 m07820 补充 2） */
        row.appendChild(tileEl(e.tile, { cls: cls.join(' ') }));
      }
      box.appendChild(row);
      start = end;
      rowNo += 1;
    }
    return box;
  }

  /* ------------------------------------------------------------ 玩家面板 */
  /**
   * renderPlayer(cellEl, state, seat, opts)
   * 依 DOM 顺序（即自家视角「从中心到外侧」）：抬头 -> 牌河 -> 手牌+副露
   */
    // ---- NAGA 决策条（用户 m00198 ③）------------------------------------------
    // 牌上方 = 打牌预测柱（官方 renderDahaiGraph：柱高 = 牌高 × 概率，最大项再叠高亮框）；
    // 牌下方 = 三条危险条（官方 renderTehai：上家 K 蓝 / 対面 T 黄 / 下家 S 绿，每条宽 30.7% 牌宽）。
    // 两条都只画在「当前决策者」手上（用户 m02007 ② / m03710 ①），别家一律不画。
    // 第 43 轮一度把危险条挪成「手牌左侧的竖条」，用户 m03799 ① 要求回滚：危险条回到手牌下方
    // （本函数），那套「竖条 + 基色边框 + 红色自下而上」的形态改用到听牌率条上（见 .p-tenpai）。
    function nagaPctText(p) {                      // 万分比 → 统一一位小数（用户 m02227 ①）
      var v = (Number(p) || 0) / 100;
      return v.toFixed(1) + '%';
    }

    /* 决策条：牌上方 = 打牌预测柱，牌下方 = 三条危险条（用户 m00198 ③ / m03710 ①②）。
     * 两条都只画在「当前决策者」手上（轮到谁决策就显示谁的，用户 m02007 ②），同种牌只在最靠左
     * 那张画（用户 m00198 ③）。危险条的取值 = danger_*[手牌主人][kind]，0 不画（与官方一致）。
     * 尺寸一律用百分比：绝对定位子元素的包含块 = 祖先的 padding edge，而 .tile 没有边框
     * ⇒ padding box 就是整张牌的外框，百分比按牌宽 / 牌高算（用户 m03799 ②：不要给牌加定位层）。 */
    function addNagaBars(node, id, nf, seen, mode, obs) {
      if (!nf) { return; }
      var kind = Tiles.kindOf(id);
      if (seen[kind]) { return; }
      seen[kind] = true;
      if (mode === 'down') {
        /* 危险条：三条并排画在牌下方（官方：每条宽 30.7% 牌宽，左偏移 3.4% / 34.1% / 64.8%） */
        var oc = (typeof obs === 'number' && obs >= 0) ? obs : 0;
        var combos = [['k', nf.danger_k, '上家'], ['t', nf.danger_t, '対面'], ['s', nf.danger_s, '下家']];
        for (var i = 0; i < combos.length; i++) {
          var arr = combos[i][1];
          var row = (arr && arr.length) ? (arr[oc] || arr[0]) : null;
          var val = (row && row.length) ? (row[kind] || 0) : 0;
          if (!(val > 0)) { continue; }
          var dn = el('span', 'tbar down ' + combos[i][0]);
          dn.style.height = (val / 100).toFixed(2) + '%';
          dn.title = Tiles.tileLabel(id) + ' ' + combos[i][2] + '危险度 ' + nagaPctText(val);
          node.appendChild(dn);
          node.classList.add('bars');
        }
        return;
      }
      /* 新版 NAGA（NAGA-避四 / NAGA-争一）：报告给的是「是否立直 × 打哪张牌」的联合分布
         （用户 m09803），所以一张牌上可能出现两根半宽的条 —— 左半紫 = 默听（不立直）打此牌的
         概率（默听支）、右半红 = 立直打此牌的概率（立直支），两根高度各自忠实表示自己的值。
         只出现在默听支的牌仍是一根整宽紫条（与 NAGA-平衡相同）；只出现在立直支的牌是整宽红条。
         旧模型没有 dahai_split ⇒ 走原来的单根紫条分支（展示一字不变）。 */
      var sp = nf.dahai_split;
      if (sp && sp.dama && sp.riichi) {
        var dv = sp.dama[kind] || 0, rv = sp.riichi[kind] || 0;
        if (!(dv > 0) && !(rv > 0)) { return; }
        var lb = Tiles.tileLabel(id);
        if (dv > 0 && rv > 0) {                    /* 默听 / 立直都能打这张牌 ⇒ 左右分色 */
          var bl = el('span', 'tbar up dama');
          bl.style.height = (dv / 100).toFixed(2) + '%';
          bl.title = '打 ' + lb + '（默听） ' + nagaPctText(dv);
          node.appendChild(bl);
          var br = el('span', 'tbar up riichi');
          br.style.height = (rv / 100).toFixed(2) + '%';
          br.title = '打 ' + lb + '（立直） ' + nagaPctText(rv);
          node.appendChild(br);
        } else if (dv > 0) {                       /* 只能默听打：整宽紫条 */
          var bu = el('span', 'tbar up');
          bu.style.height = (dv / 100).toFixed(2) + '%';
          bu.title = '打 ' + lb + ' 预测 ' + nagaPctText(dv);
          node.appendChild(bu);
        } else {                                   /* 只能立直打：整宽红条 */
          var bs = el('span', 'tbar up riichi solo');
          bs.style.height = (rv / 100).toFixed(2) + '%';
          bs.title = '打 ' + lb + '（立直） ' + nagaPctText(rv);
          node.appendChild(bs);
        }
        node.classList.add('bars');
        return;
      }
      var dp = nf.dahai_pred;
      var p = (dp && dp.length) ? (dp[kind] || 0) : 0;
      if (!(p > 0)) { return; }
      /* 概率条统一配色（用户 m10014）：默听条一律同一紫色、立直条一律同一红色，
         不再给「概率最高的那张牌」单独加亮紫高亮（原来的 .max 已删除）。 */
      var up = el('span', 'tbar up');
      up.style.height = (p / 100).toFixed(2) + '%';
      up.title = '打 ' + Tiles.tileLabel(id) + ' 预测 ' + nagaPctText(p);
      node.appendChild(up);
      node.classList.add('bars');
    }

  /* pos = 展示位置（0 下 / 1 右 / 2 上 / 3 左）：整块面板按「位置」旋转，与绝对座位无关 ——
     换主视角只需改 app.js 的 viewRot 旋转向量，四家的相对方位自动保持（用户 m03343 ②）。 */
  function renderPlayer(cellEl, st, seat, opts, pos) {
    clear(cellEl);
    var pl = st.players[seat];
    if (pos === undefined || pos === null) { pos = seat; }   /* 兼容旧调用：按绝对座位摆 */
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

    var rot = el('div', 'p-rot ' + SEAT_ROT[pos]);
    rot.title = (pl.name || '') + ' · ' + ROT_NAME[SEAT_ROT[pos]];

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
    /* 黄框只画在「等待鸣牌响应」的那张牌上（opts.mark.seat = 打出这张牌的人，用户 m07820 补充 2） */
    rot.appendChild(riverEl(pl.river, !!(opts.mark && opts.mark.seat === seat)));

    /* ③④ 手牌 + 副露（最外侧一行；副露在手牌右侧。摸到的牌单独放在手牌末端） */
    /* 摸到的牌单独摆在手牌末端；和了帧也照上一帧的摆法显示（m00569 ②：不插进手牌） */
    var drawn = (st.drawn && st.drawn.player === seat) ? st.drawn.tile : null;
    var winTile = (st.result && st.result.type === 'agari' && st.result.winner === seat)
      ? st.result.winTile : null;
    var rest = pl.hand.slice(), k;
    if (drawn !== null) { k = rest.indexOf(drawn); if (k >= 0) { rest.splice(k, 1); } }
    rest = Tiles.sortHand(rest);

    /* 决策条（用户 m02007 ② / m03710 ①②）：打牌预测柱与铳率条都只画在「当前决策者」手上 ——
     * 轮到谁决策就显示谁的，别家一律不画（用户在截图里指出：显示他家手牌时别家手牌下方也跟着
     * 出现条文，混淆了「谁在决策」）。同种牌只画最靠左那张（用户 m00198 ③）；5m / 5p / 5s 例外 ——
     * 优先画在普通 5 上、避开赤 5（用户 m04498，见下面的 barOwner）。
     * 第 43 轮把铳率条挪成「手牌左侧的竖条」，用户 m03799 ① 要求回滚到手牌下方。 */
    var nagaFrame = (opts.naga && opts.naga.frame) ? opts.naga.frame : null;
    var decider = (opts.naga && typeof opts.naga.seat === 'number') ? opts.naga.seat : null;
    /* 决策者是别家、他的牌又被隐藏时就不画（用户 m03343 ①） */
    var hideDecider = !!(opts.naga && opts.naga.hideOthers) && decider !== null && decider !== opts.selfSeat;
    var upNf = (nagaFrame && decider !== null && seat === decider && !hideDecider) ? nagaFrame : null;
    var upBars = upNf ? {} : null;
    /* 铳率条同一个条件（只画决策者）；另外手牌盖着时也不画（盖着的牌不泄露身份） */
    var dnBars = (upNf && !hidden) ? {} : null;
    /* 听牌率条（用户 m03479 ②）：只画在非主视角的三家手上；报告里 tenpai_* 的第一维 = 观察者，
     * 我们用「主视角那一行」+ 展示槽位取项（与官方 viewer 的 tw 行一致）。 */
    var tenpai = null;
    if (pos > 0 && nagaFrame && typeof opts.selfSeat === 'number') {
      var tpRow = (pos === 1) ? nagaFrame.tenpai_s : ((pos === 2) ? nagaFrame.tenpai_t : nagaFrame.tenpai_k);
      /* 报告里没有 tenpai_* 数据时整条不画（Mortal 报告就没有，用户 m05937 ③） */
      if (tpRow && tpRow.length > opts.selfSeat) { tenpai = tpRow[opts.selfSeat] || 0; }
    }
    /* 「同种牌只画最靠左那张」到底是哪一张：kind → 该画条的那张牌 id（用户 m00198 ③ / m04498）。
     * 赤 5 的 id 是同一 kind 里最小的（赤 5 = kind * 4 + 0），升序排列后反而排在最左 ⇒
     * 5m / 5p / 5s 特殊处理：优先普通 5，手里只有赤 5 时才画在赤 5 上。
     * 摸到的牌排在最后 ⇒ 同 kind 时手牌优先（与原「最靠左」的行为一致）。 */
    var barOwner = {};
    var barSeq = rest.slice();
    if (drawn !== null) { barSeq.push(drawn); }
    for (var bq = 0; bq < barSeq.length; bq++) {
      var bk = Tiles.kindOf(barSeq[bq]);
      if (barOwner[bk] === undefined) { barOwner[bk] = barSeq[bq]; continue; }
      if (!Tiles.isRed(barSeq[bq]) && Tiles.isRed(barOwner[bk])) { barOwner[bk] = barSeq[bq]; }
    }
    /* 细红框（用户 m08125 ② / m08178 / m08319 ①）：本帧决策者接下来要做的事 ——
     *   打牌 = 即将打出的那一张（只给 kind，下面按紫色条那套筛选逻辑挑一张：同 kind 只框一张、
     *     优先普通 5 避开赤 5）；立直宣言算打出的宣言牌；
     *   暗杠 / 加杠 = 准备杠的 4 张（app.js 给准确 id：手里几张 + 副露区那 3 张）。
     * opts.next = { seat: 被框的那一家（= 本帧决策者，用户 m08319 ① 起不一定是主视角）,
     *   kind: n, tids: [手里准确的 id…], melds: [副露区准确的 id…] }。 */
    var nextIds = [];
    var nextMeldIds = (opts.next && opts.next.melds) ? opts.next.melds : [];
    if (opts.next && seat === opts.next.seat) {
      var nseq = rest.slice();
      if (drawn !== null) { nseq.push(drawn); }
      var given = (opts.next.tids && opts.next.tids.length) ? opts.next.tids : null;
      if (given) {
        nextIds = given;                       /* 暗杠 / 加杠：牌谱（状态）已经确定是哪几张 */
      } else {
        /* 打牌：同 kind 可能有好几张，只框其中一张 —— 与 barOwner 同一套规则：
           先出现的那张优先，遇到普通 5 就把赤 5 换掉 */
        var pick = null;
        for (var nq = 0; nq < nseq.length; nq++) {
          if (Tiles.kindOf(nseq[nq]) !== opts.next.kind) { continue; }
          if (pick === null) { pick = nseq[nq]; continue; }
          if (!Tiles.isRed(nseq[nq]) && Tiles.isRed(pick)) { pick = nseq[nq]; }
        }
        if (pick !== null) { nextIds = [pick]; }
      }
    }
    var hr = el('div', 'p-hand');
    var hb = el('div', 'tiles');
    for (var j = 0; j < rest.length; j++) {
      var tn = tileEl(rest[j], {
        back: hidden,
        cls: ((winTile !== null && rest[j] === winTile) ? 'win' : '')
          + ((nextIds.indexOf(rest[j]) >= 0) ? ' next' : '')
      });
      if (upBars && barOwner[Tiles.kindOf(rest[j])] === rest[j]) {
        addNagaBars(tn, rest[j], upNf, upBars, 'up', opts.selfSeat);
      }
      if (dnBars && barOwner[Tiles.kindOf(rest[j])] === rest[j]) {
        addNagaBars(tn, rest[j], upNf, dnBars, 'down', seat);
      }
      hb.appendChild(tn);
    }
    hr.appendChild(hb);
    /* 摸牌槽位永远占位：没摸到时加 .empty（CSS 里 visibility: hidden），
     * 这样「摸牌前 / 摸牌后」手牌行宽度一致，播放时不会左右摆（用户 m01386）。 */
    var db = el('div', 'tiles drawn' + (self ? ' self' : '') + (drawn === null ? ' empty' : ''));
    if (drawn !== null) {
      var dn = tileEl(drawn, {
        back: hidden,
        cls: ((winTile !== null && drawn === winTile) ? 'win' : '')
          + ((drawn !== null && nextIds.indexOf(drawn) >= 0) ? ' next' : '')
      });
      if (upBars && barOwner[Tiles.kindOf(drawn)] === drawn) {
        addNagaBars(dn, drawn, upNf, upBars, 'up', opts.selfSeat);
      }
      if (dnBars && barOwner[Tiles.kindOf(drawn)] === drawn) {
        addNagaBars(dn, drawn, upNf, dnBars, 'down', seat);
      }
      db.appendChild(dn);
    }
    hr.appendChild(db);
    /* 副露在手牌右侧：DOM 里倒序排（最后一个是先鸣的 = 最右），后鸣的依次向左延伸 */
    var bottom = el('div', 'p-bottom');
    bottom.appendChild(hr);
    if (pl.melds.length) {
      var mr = el('div', 'p-melds');
      for (var mi = pl.melds.length - 1; mi >= 0; mi--) {
        mr.appendChild(meldEl(pl.melds[mi], seat, nextMeldIds));
      }
      bottom.appendChild(mr);
    }
    rot.appendChild(bottom);

    /* 听牌率条（用户 m03479 ② / m03799 ①）：竖着贴在「这一家」手牌的左端外侧、与手牌垂直 ——
     * 长度 1.5 牌高（手牌带上下各伸出 .25 牌高）、宽度 = 一条铳率条的宽度；基色 = 与主视角的相对
     * 关系（位置 1 下家绿 / 位置 2 対面黄 / 位置 3 上家蓝），边框保持基色（用户 m03627）；
     * 红色从「该家自己的下方」（= 远离牌桌中心的一侧）往上生长，高度 = 听牌率。
     * 放进手牌容器（.p-hand .tiles 是 position: relative）⇒ 随面板一起旋转。 */
    if (tenpai !== null) {
      var tp = el('div', 'p-tenpai tp-' + (pos === 1 ? 's' : (pos === 2 ? 't' : 'k')));
      var tpRed = el('span', 'tp-red');
      tpRed.style.height = Math.max(0, Math.min(100, (Number(tenpai) || 0) / 100)).toFixed(1) + '%';
      tp.appendChild(tpRed);
      tp.title = (pl.name || '') + ' 听牌率 ' + nagaPctText(tenpai);
      hb.appendChild(tp);
    }

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
   * opts: { selfSeat: 0, viewRot: [0,1,2,3], hideOthers: bool, naga: { frame, seat, hideOthers } }
   * viewRot = 「展示位置 → 绝对座位」的旋转向量：下标 0 下（主视角）/ 1 右（下家）/ 2 上（対面）/ 3 左（上家）；
   * 初始 [0,1,2,3]，换主视角时整体旋转即可（用户 m03343 ②）。
   */
  function renderBoard(boardEl, st, opts) {
    opts = opts || {};
    if (opts.selfSeat === undefined) { opts.selfSeat = 0; }
    clear(boardEl);

    var layout = [
      ['top', 2], ['left', 3], ['center', null], ['right', 1], ['bottom', 0]
    ];
    var vr = (opts.viewRot && opts.viewRot.length === 4) ? opts.viewRot : [0, 1, 2, 3];
    for (var i = 0; i < layout.length; i++) {
      var area = layout[i][0], pos = layout[i][1];
      var cell = el('div', 'cell cell-' + area);
      if (pos === null) { renderCenter(cell, st, opts); }
      else { renderPlayer(cell, st, vr[pos], opts, pos); }
      boardEl.appendChild(cell);
    }

    /* 大字（vocalization，用户 m03978 ②）：官方 renderBa 把它画在所有牌之上、结算框之下，
     * 文字永远水平（不随座位旋转、不随面板旋转）⇒ 绝对定位盖在牌桌上，位置取展示位置的百分比。
     * 由 app.js 的 vocalForFrame() 给出 { pos, text }（天凤牌谱的 call / agari 事件同样适用）；
     * 位置直接用官方 vocalization_pos 的百分比、不做任何平移（第 48 轮的左移已按用户 m04456 回滚）。 */
    var vc = opts.vocal;
    if (vc && vc.text) {
      var vp = VOCAL_POS[vc.pos & 3] || VOCAL_POS[0];
      var vo = el('div', 'vocal', vc.text);
      vo.style.left = vp[0] + '%';
      vo.style.top = vp[1] + '%';
      boardEl.appendChild(vo);
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
    SEAT_ROT: SEAT_ROT, RIVER_COLS: RIVER_COLS, RIVER_TILE_ROWS: RIVER_TILE_ROWS, RIVER_ROWS: RIVER_ROWS,
    VOCAL_POS: VOCAL_POS
  };
});
