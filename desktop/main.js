'use strict';
/* 天凤牌谱分析 —— Electron 主进程
 * 职责：挑一个空闲端口 -> 拉起打包好的后端 exe -> 轮询 /api/health
 *      -> BrowserWindow 加载 http://127.0.0.1:<port>/web/index.html -> 退出时杀掉后端。
 * 说明：不能用 file:// 打开 web/index.html（那样 /api/* 与 /media/tiles/ 全部失效）。
 *      后端 stdout/stderr 直接写日志文件（不经过管道，避免缓冲区/权限问题）。
 */
const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

const APP_TITLE = '天凤牌谱分析';
const HOST = '127.0.0.1';
const EXE_NAME = 'tenhou-paipu-analysis-server.exe';

let backend = null;
let win = null;
let quitting = false;

function backendPath() {
  const list = [];
  if (app.isPackaged) list.push(path.join(process.resourcesPath, 'backend', EXE_NAME));
  list.push(path.join(__dirname, '..', 'dist', 'pyi', 'tenhou-paipu-analysis-server', EXE_NAME));
  for (const p of list) { if (fs.existsSync(p)) return p; }
  return null;
}

function logPath() {
  const base = process.env.LOCALAPPDATA || app.getPath('userData');
  const dir = path.join(base, 'tenhou-paipu-analysis', 'logs');
  try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { /* 只读环境则退回 userData */ }
  return path.join(dir, 'backend.log');
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, HOST, () => {
      const p = srv.address().port;
      srv.close(() => resolve(p));
    });
  });
}

function health(port, timeoutMs) {
  return new Promise((resolve) => {
    const req = http.get({ host: HOST, port, path: '/api/health', timeout: timeoutMs }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { body += c; });
      res.on('end', () => { try { resolve(JSON.parse(body)); } catch (e) { resolve(null); } });
    });
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.on('error', () => resolve(null));
  });
}

async function waitHealth(port, limitMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < limitMs) {
    if (backend && backend.exitCode !== null) return null;
    const h = await health(port, 2000);
    if (h && h.ok) return h;
    await new Promise((r) => setTimeout(r, 250));
  }
  return null;
}

function startBackend(port) {
  const exe = backendPath();
  if (!exe) {
    dialog.showErrorBox(APP_TITLE, '找不到后端程序：' + EXE_NAME + '\n请先运行 build.ps1 生成（dist/pyi/...）。');
    return null;
  }
  const log = logPath();
  let fd = null;
  try {
    fd = fs.openSync(log, 'a');
    fs.writeSync(fd, '\n==== ' + new Date().toISOString() + ' 启动 ' + exe + ' --port ' + port + ' ====\n');
  } catch (e) {
    fd = null;   // 日志不可写（只读目录/权限不足）也不能挡住启动
  }
  const child = spawn(exe, ['--port', String(port), '--host', HOST], {
    cwd: path.dirname(exe),
    windowsHide: true,
    stdio: fd === null ? 'ignore' : ['ignore', fd, fd],
  });
  child.on('exit', (code, sig) => {
    if (fd !== null) {
      try { fs.writeSync(fd, '[backend] 退出 code=' + code + ' signal=' + sig + '\n'); } catch (e) { /* ignore */ }
      try { fs.closeSync(fd); } catch (e) { /* ignore */ }
    }
    if (!quitting) {
      dialog.showErrorBox(APP_TITLE, '后端进程意外退出（code=' + code + '）。\n日志：' + log);
      app.quit();
    }
  });
  return child;
}

function stopBackend() {
  const child = backend;
  backend = null;
  if (!child || child.exitCode !== null) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    } else {
      child.kill();
    }
  } catch (e) { /* ignore */ }
}

function createWindow(port) {
  win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1024,
    minHeight: 680,
    title: APP_TITLE,
    backgroundColor: '#1b1f23',
    autoHideMenuBar: true,
    icon: path.join(__dirname, '..', 'build', 'icon.ico'),
    show: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  win.setMenuBarVisibility(false);
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => { win = null; });
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (ev, url) => {
    if (!url.startsWith('http://' + HOST + ':' + port + '/')) { ev.preventDefault(); shell.openExternal(url); }
  });
  win.webContents.on('before-input-event', (ev, input) => {
    if (input.type === 'keyDown' && input.key === 'F12') { win.webContents.toggleDevTools(); ev.preventDefault(); }
  });
  win.loadURL('http://' + HOST + ':' + port + '/web/index.html');
}

async function boot() {
  const port = await freePort();
  backend = startBackend(port);
  if (!backend) { app.quit(); return; }
  const h = await waitHealth(port, 60000);
  if (!h) { dialog.showErrorBox(APP_TITLE, '后端启动超时。\n日志：' + logPath()); app.quit(); return; }
  createWindow(port);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.setAppUserModelId('com.zummacrystal.tenhou-paipu-analysis');
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.on('window-all-closed', () => { app.quit(); });
  app.on('will-quit', () => { quitting = true; stopBackend(); });
  Menu.setApplicationMenu(null);
  app.whenReady().then(boot).catch((e) => {
    dialog.showErrorBox(APP_TITLE, '启动失败：' + (e && e.message ? e.message : e));
    app.quit();
  });
}