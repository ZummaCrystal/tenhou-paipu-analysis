; electron-builder NSIS 自定义片段（用户 m00178 决策 4：
;   NSIS 安装包、安装路径用户可选、数据目录固定、卸载时询问是否删除数据）
; 数据目录固定为 %LOCALAPPDATA%\tenhou-paipu-analysis（由 mjscore/paths.py 决定，与安装路径无关）

!macro customUnInstall
  IfFileExists "$LOCALAPPDATA\tenhou-paipu-analysis\*.*" 0 done
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除本地数据（牌谱文件与数据库）？$\r$\n$\r$\n位置：$LOCALAPPDATA\tenhou-paipu-analysis$\r$\n$\r$\n选择「否」将保留这些数据，下次安装后仍可直接使用。" IDNO done
  RMDir /r "$LOCALAPPDATA\tenhou-paipu-analysis"
  done:
!macroend