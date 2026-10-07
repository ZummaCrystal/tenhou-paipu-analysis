/* tiles.js — 天凤牌 id(0..135) 与图片素材的映射 / 排序辅助
 * 天凤牌 id 编码：
 *   kind = id >> 2   (0..33)； suit = kind // 9 (0=万m,1=筒p,2=索s,3=字z)
 *   数牌 rank = kind % 9 + 1； 字牌 kind 27..33 -> 1z..7z (东 南 西 北 白 发 中)
 *   赤宝牌：id % 4 === 0 且 kind % 9 === 4 （即 5m / 5p / 5s）
 * 素材命名与 killer_mortal_gui 一致：1m..9m, 0m(赤5m), 1z..7z, back, Front, Blank
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.Tiles = factory(); }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var SUIT_CHAR = ['m', 'p', 's', 'z'];
  var HONOR_LABEL = ['東', '南', '西', '北', '白', '發', '中'];
  /* 素材目录：用 server.py 打开时页面在网站根（/media/tiles/）；
     直接双击 web/index.html（file://）时退回相对上一级（../media/tiles/）。 */
  var TILE_DIR = (typeof location !== 'undefined' && location.protocol === 'file:')
    ? '../media/tiles/' : '/media/tiles/';

  function kindOf(id) { return id >> 2; }
  function suitOf(id) { return Math.floor(kindOf(id) / 9); }
  function rankOf(id) { return (kindOf(id) % 9) + 1; }
  function isHonor(id) { return kindOf(id) >= 27; }
  function isRed(id) { return kindOf(id) < 27 && (id & 3) === 0 && (kindOf(id) % 9) === 4; }

  /** id -> 素材短名，如 '1m' / '0m'(赤5) / '3z'(西) */
  function tileName(id) {
    var k = kindOf(id), s = Math.floor(k / 9);
    if (s === 3) { return (k - 26) + 'z'; }
    var n = (k % 9) + 1;
    if (n === 5 && (id & 3) === 0) { return '0' + SUIT_CHAR[s]; }
    return n + SUIT_CHAR[s];
  }
  function tileSrc(id) { return TILE_DIR + tileName(id) + '.svg'; }

  /** id -> 中文可读名，如 '赤5万' / '5万' / '東' */
  function tileLabel(id) {
    if (isHonor(id)) { return HONOR_LABEL[kindOf(id) - 27]; }
    var num = rankOf(id);
    var suit = ['万', '筒', '索'][suitOf(id)];
    return (isRed(id) ? '赤' : '') + num + suit;
  }

  /** 手牌排序：先按种类，赤5排在普通5之前（id 小者在前） */
  function sortHand(ids) {
    return ids.slice().sort(function (a, b) { return a - b; });
  }

  /** 统计各 kind 的数量，返回 {kind: n} */
  function countsByKind(ids) {
    var m = {};
    for (var i = 0; i < ids.length; i++) { var k = kindOf(ids[i]); m[k] = (m[k] || 0) + 1; }
    return m;
  }

  return {
    SUIT_CHAR: SUIT_CHAR, HONOR_LABEL: HONOR_LABEL,
    kindOf: kindOf, suitOf: suitOf, rankOf: rankOf, isHonor: isHonor, isRed: isRed,
    tileName: tileName, tileSrc: tileSrc, tileLabel: tileLabel,
    sortHand: sortHand, countsByKind: countsByKind
  };
});