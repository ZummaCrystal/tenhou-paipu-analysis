'use strict';
/* 天凤牌谱分析 —— Electron 预加载脚本
 * 渲染进程（web/js/app.js）只需要一件事：让「选择牌谱文件…」打开一个默认定位到牌谱数据根目录的
 * 原生文件对话框（用户 m01084：数据目录固定到 %LOCALAPPDATA% 之后，用户第一次使用时很难自己找到
 * data/paipu，浏览器 <input type=file> 的初始目录又无法用脚本指定）。
 * 浏览器里没有 window.tenhouDesktop 这个桥，前端会自动退回 <input type=file>，
 * 所以「python server.py + 浏览器」和「双击 web/index.html 离线播放」都照旧。
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('tenhouDesktop', {
  isDesktop: true,
  /* defaultPath：希望对话框默认打开的目录，前端从 /api/health 的 paipu_dir 传入。
     返回 { canceled: boolean, filePath: string }。 */
  pickPaipuFile: function (defaultPath) {
    return ipcRenderer.invoke('pick-paipu-file', String(defaultPath || ''));
  },
});
