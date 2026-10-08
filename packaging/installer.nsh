; electron-builder NSIS 自定义片段（用户 m00178 决策 4：
;   NSIS 安装包、安装路径用户可选、数据目录固定、卸载时询问是否删除数据）
; 数据目录 = %LOCALAPPDATA%\tenhou-paipu-analysis（由 mjscore/paths.py 决定，与安装路径无关）
;
; 用户 m01220 反馈的缺陷：从控制面板卸载时没有出现「是否删除数据」的询问。
; 根因（用 electron-builder 自带的 makensis 3.04 实测）：按「所有用户」安装（build.nsis.perMachine
; = true）时，卸载器里的 shell 变量上下文是 all，此时 $LOCALAPPDATA 会解析成 C:\ProgramData
; （$APPDATA 同样），于是 IfFileExists "$LOCALAPPDATA\tenhou-paipu-analysis\*.*" 恒为假，整段被
; 跳过。修法：先 SetShellVarContext current 切到「执行卸载的那个用户」，查完、删完再切回 all
; —— electron-builder 自己在 templates/nsis/uninstaller.nsh 里删 $APPDATA 时也是这么做的。
; 另外：询问框的默认按钮设为「否」（MB_DEFBUTTON2），也就是默认不删除数据；静默卸载（/S）
; 一律保留数据。这里只用 NSIS 原生指令（StrCmp / IfFileExists / IfSilent），不依赖 LogicLib。

!macro customUnInstall
  StrCmp $installMode "all" 0 tenhou_shell_current
    SetShellVarContext current
  tenhou_shell_current:

  IfFileExists "$LOCALAPPDATA\tenhou-paipu-analysis\*.*" 0 tenhou_keep_data
  IfSilent tenhou_keep_data
  MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "是否同时删除本地数据（牌谱文件与数据库）？$\r$\n$\r$\n位置：$LOCALAPPDATA\tenhou-paipu-analysis$\r$\n$\r$\n默认选择「否」：保留这些数据，下次安装后仍可直接使用。" IDNO tenhou_keep_data
  RMDir /r "$LOCALAPPDATA\tenhou-paipu-analysis"
  RMDir /r "$APPDATA\tenhou-paipu-analysis"

  tenhou_keep_data:

  StrCmp $installMode "all" 0 tenhou_shell_done
    SetShellVarContext all
  tenhou_shell_done:
!macroend
