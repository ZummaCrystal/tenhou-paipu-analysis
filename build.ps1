<#
    build.ps1 —— 天凤牌谱分析：一键打出 Windows 安装包（Electron 外壳 + PyInstaller 后端）

  用法（在项目根目录，用普通（非受限）终端）：
      powershell -ExecutionPolicy Bypass -File .\build.ps1
      powershell -ExecutionPolicy Bypass -File .\build.ps1 -SkipElectron          # 只出后端
      powershell -ExecutionPolicy Bypass -File .\build.ps1 -Smoke -Port 8788      # 顺带冒烟测试
      powershell -ExecutionPolicy Bypass -File .\build.ps1 -Clean -SkipTests      # 重头来过
      powershell -ExecutionPolicy Bypass -File .\build.ps1 -SkipPyi               # 只重打外壳

  六个步骤：环境检查 → 清理（可选）→ 图标 → 回归测试 → 后端 → 冒烟（可选）→ 外壳/安装包

  几个要知道的点：
    * Python 固定用 anaconda 的 py314_null 环境（-PythonExe 可换），需要里面的 PyInstaller；
    * 决策 1：node.exe 内嵌进后端包（-NodeExe 指定，-SkipNodeEmbed 关掉）；
    * 决策 2：后端是 onedir（dist\pyi\tenhou-paipu-analysis-server\）；
    * 决策 3：用户数据固定放 %LOCALAPPDATA%\tenhou-paipu-analysis\data（代码里就是这套路径）；
    * 决策 4：NSIS 安装包，安装路径用户可选；卸载时由 packaging\installer.nsh 询问是否删数据；
    * 图标由 tools\svg2ico.py 从 media\tiles\6m.svg 可复现生成（-SkipIcon 沿用现有 build\icon.ico）；
    * 受限终端（禁止子进程匿名管道）里，PyInstaller 的 hook 发现会报 WinError 5 —— 本脚本会自动
      改用 packaging\pyi_build.py --in-process 兜底；electron-builder 那步则必须换普通终端。
#>
[CmdletBinding()]
param(
    [string]$PythonExe = 'D:\coding\anaconda3\envs\py314_null\python.exe',
    [string]$NodeExe = '',
    [switch]$SkipIcon,
    [switch]$SkipTests,
    [switch]$FullTests,
    [switch]$SkipPyi,
    [switch]$SkipElectron,
    [switch]$SkipNodeEmbed,
    [switch]$ForceInProcessPyi,
    [switch]$Clean,
    [switch]$Smoke,
    [int]$Port = 8770
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Definition }
Set-Location -LiteralPath $Root
$env:PYTHONIOENCODING = 'utf-8'
$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'   # 本机没有代码签名证书，别去自动找

$script:StepNo = 0
function Step($t) { $script:StepNo++; Write-Host ''; Write-Host ('== [{0}] {1}' -f $script:StepNo, $t) -ForegroundColor Cyan }
function Ok($t) { Write-Host ('   OK  ' + $t) -ForegroundColor Green }
function Warn($t) { Write-Host ('   !   ' + $t) -ForegroundColor Yellow }
function Say($t) { Write-Host $t }
function Die($t) { Write-Host ''; Write-Host ('xxx ' + $t) -ForegroundColor Red; exit 1 }
function Must($p, $what) { if (-not (Test-Path -LiteralPath $p)) { Die ('缺少' + $what + '：' + $p) } }
function FSize($p) { if (Test-Path -LiteralPath $p) { '{0:N0} B' -f (Get-Item -LiteralPath $p).Length } else { '缺失' } }

Say '天凤牌谱分析 · 打包'
Say ('项目根：' + $Root)

# ── 1. 环境 ─────────────────────────────────────────────────
Step '检查构建环境'
if (-not (Test-Path -LiteralPath $PythonExe)) { Die ('Python 解释器不存在：' + $PythonExe) }
if (-not $NodeExe) {
    $cands = @()
    if ($env:ProgramFiles) { $cands += (Join-Path $env:ProgramFiles 'nodejs\node.exe') }
    if (${env:ProgramFiles(x86)}) { $cands += (Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe') }
    if ($env:LOCALAPPDATA) { $cands += (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe') }
    $cands += 'D:\Program Files\nodejs\node.exe'
    foreach ($c in $cands) { if (Test-Path -LiteralPath $c) { $NodeExe = $c; break } }
    if (-not $NodeExe) { $g = Get-Command node.exe -ErrorAction SilentlyContinue; if ($g) { $NodeExe = $g.Source } }
}
if (-not $NodeExe -or -not (Test-Path -LiteralPath $NodeExe)) { Die '找不到 node.exe（决策 1 要把 node 内嵌进包），请用 -NodeExe 指定' }
$NodeDir = Split-Path -Parent $NodeExe
$NpmCmd = Join-Path $NodeDir 'npm.cmd'
if (($env:PATH -split ';') -notcontains $NodeDir) { $env:PATH = $NodeDir + ';' + $env:PATH }
Say ('  python : ' + $PythonExe)
& $PythonExe -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { Die ('PyInstaller 不可用。先执行： "' + $PythonExe + '" -m pip install pyinstaller') }
Say ('  node   : ' + $NodeExe + '   (' + (FSize $NodeExe) + ')')
& $NodeExe --version
if ($LASTEXITCODE -ne 0) { Die ('node 跑不起来：' + $NodeExe) }
if (-not (Test-Path -LiteralPath $NpmCmd)) { Warn ('没找到 npm.cmd：' + $NpmCmd + '（只有打 Electron 那步才需要）') }
Ok '环境 OK'

# ── 2. 清理 ─────────────────────────────────────────────────
if ($Clean) {
    Step '清理旧产物'
    foreach ($d in @((Join-Path $Root 'dist\pyi'), (Join-Path $Root 'dist\electron'), (Join-Path $Root 'build\pyi'))) {
        if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Ok ('已删除 ' + $d) }
    }
}

# ── 3. 图标 ─────────────────────────────────────────────────
Step '图标（media\tiles\6m.svg -> build\icon.ico）'
$Icon = Join-Path $Root 'build\icon.ico'
if ($SkipIcon) {
    Must $Icon '图标（-SkipIcon 时要求它已存在）'
    Ok ('沿用现有图标 ' + (FSize $Icon))
} else {
    & $PythonExe (Join-Path $Root 'tools\svg2ico.py') --svg (Join-Path $Root 'media\tiles\6m.svg') --out $Icon --png-dir (Join-Path $Root 'build')
    if ($LASTEXITCODE -ne 0) { Die ('图标生成失败（tools\svg2ico.py 退出码 ' + $LASTEXITCODE + '）') }
    Ok ('build\icon.ico ' + (FSize $Icon) + '（16/32/48/64/128/256）')
}

# ── 4. 回归测试 ─────────────────────────────────────────────
if (-not $SkipTests) {
    Step '回归测试'
    & $NodeExe (Join-Path $Root 'test\apptest.js')
    if ($LASTEXITCODE -ne 0) { Die ('test\apptest.js 未通过（退出码 ' + $LASTEXITCODE + '）') }
    Ok 'test\apptest.js 通过'
    if ($FullTests) {
        & $PythonExe (Join-Path $Root 'test\datamgr_test.py')
        if ($LASTEXITCODE -ne 0) { Die ('test\datamgr_test.py 未通过（退出码 ' + $LASTEXITCODE + '）。它要读 %LOCALAPPDATA%\tenhou-paipu-analysis\data 下的真实数据；本机没有就改用 -SkipTests 或去掉 -FullTests') }
        Ok 'test\datamgr_test.py 通过'
    } else {
        Say '  （跳过需要真实数据目录的 test\datamgr_test.py，加 -FullTests 可跑）'
    }
}

# ── 5. 后端（PyInstaller） ──────────────────────────────────
$BackendDir = Join-Path $Root 'dist\pyi\tenhou-paipu-analysis-server'
$ServerExe = Join-Path $BackendDir 'tenhou-paipu-analysis-server.exe'
if (-not $SkipPyi) {
    Step '打包后端（PyInstaller onedir + 内嵌 node）'
    $pyiBuild = Join-Path $Root 'packaging\pyi_build.py'
    Must $pyiBuild '打包器 packaging\pyi_build.py'
    $common = @($pyiBuild, '--python-exe', $PythonExe)
    if ($SkipNodeEmbed) { $common += '--skip-node' } else { $common += @('--node-exe', $NodeExe) }
    if ($ForceInProcessPyi) {
        & $PythonExe @common --in-process
        if ($LASTEXITCODE -ne 0) { Die ('PyInstaller 失败（退出码 ' + $LASTEXITCODE + '）') }
    } else {
        Say '  第 1 次：正常模式（hook 发现在隔离子进程里跑）'
        & $PythonExe @common
        if ($LASTEXITCODE -ne 0) {
            Warn ('正常模式失败（受限终端常见：PermissionError [WinError 5] / create_pipe）')
            Say '  第 2 次：--in-process 兜底'
            & $PythonExe @common --in-process
            if ($LASTEXITCODE -ne 0) { Die ('PyInstaller 两次都失败（退出码 ' + $LASTEXITCODE + '）') }
            Ok '兜底模式成功'
        }
    }
}
Must $ServerExe '后端 exe（别加 -SkipPyi，或者先跑一次不带 -SkipPyi 的）'
$Internal = Join-Path $BackendDir '_internal'
foreach ($rel in @('web\index.html', 'media\tiles\6m.svg', 'mjscore\node_harness.js')) { Must (Join-Path $Internal $rel) ('后端资源 ' + $rel) }
Ok ('后端 exe ' + (FSize $ServerExe))
if ($SkipNodeEmbed) {
    Warn '没有内嵌 node（后端会退回 PATH / 常见安装路径里的 node.exe）'
} else {
    Must (Join-Path $Internal 'node\node.exe') '内嵌 node（决策 1；不想要就加 -SkipNodeEmbed）'
    Ok ('内嵌 node ' + (FSize (Join-Path $Internal 'node\node.exe')))
}

# ── 6. 冒烟 ─────────────────────────────────────────────────
if ($Smoke) {
    Step ('后端冒烟测试（/api/health，端口 ' + $Port + '）')
    & $PythonExe (Join-Path $Root 'packaging\smoke.py') --exe $ServerExe --port $Port
    if ($LASTEXITCODE -ne 0) { Die ('冒烟测试失败（退出码 ' + $LASTEXITCODE + '）；后端日志见 build\pyi\smoke-backend.log') }
    Ok '健康检查通过'
}

# ── 7. 外壳 + NSIS 安装包 ───────────────────────────────────
if (-not $SkipElectron) {
    Step '打包 Electron 外壳与 NSIS 安装包'
    $cli = Join-Path $Root 'node_modules\electron-builder\out\cli\cli.js'
    Must $cli 'electron-builder（先在项目根执行 npm install）'
    Must (Join-Path $Root 'build\icon.ico') '图标 build\icon.ico'
    # 注意：不要再写成 -c.npmRebuild=false —— 某些 shell 下 yargs 会把它当成「配置文件」路径，
    # 报 ENOENT: open ...\.npmRebuild=false。关掉依赖重建写在 package.json 的 build.npmRebuild 里。
    & $NodeExe $cli --win nsis --publish never
    if ($LASTEXITCODE -ne 0) { Die ('electron-builder 失败（退出码 ' + $LASTEXITCODE + '）。日志里若是 spawn EPERM / EPERM: operation not permitted，说明当前终端禁止子进程匿名管道，请换普通终端重跑。') }
    $setups = @(Get-ChildItem -LiteralPath (Join-Path $Root 'dist\electron') -Filter '*setup.exe' -ErrorAction SilentlyContinue)
    if ($setups.Count -eq 0) { Die 'electron-builder 跑完了但没找到安装包（dist\electron\*setup.exe）' }
    foreach ($s in $setups) {
        Ok ($s.Name + '  ' + ('{0:N0} B' -f $s.Length))
        Say ('      SHA256 ' + (Get-FileHash -LiteralPath $s.FullName -Algorithm SHA256).Hash)
    }
}

Write-Host ''
Write-Host '=== 完成 ===' -ForegroundColor Green
Say ('  后端目录 : ' + $BackendDir)
Say ('  安装包   : ' + (Join-Path $Root 'dist\electron'))
Say '  用户数据 : %LOCALAPPDATA%\tenhou-paipu-analysis\data（卸装时会问要不要一起删）'
exit 0