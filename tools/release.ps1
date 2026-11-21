# 星剪 StarSnip 发版脚本
#
#   .\tools\release.ps1                      # 用当前版本号打包，不推送
#   .\tools\release.ps1 -Version 1.2.0       # 先同步版本号再打包
#   .\tools\release.ps1 -Version 1.2.0 -Push # 打包 + 提交 + tag + 推送 + Release
#
# 做的事：同步版本 → PyInstaller 打包 → 写 SHA256 → 回填 version.json 的
# 下载地址/哈希 → （可选）提交、打 tag、推送、用 gh 建 Release。
param(
    [string]$Version = "",
    [switch]$Push,
    [switch]$Force      # 同一个版本号要重发时用：会重建、覆盖 Release、强制移动 tag
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($Version) {
    & $py tools\set_version.py $Version
    if ($LASTEXITCODE -ne 0) { throw "版本同步失败" }
}

$initText = Get-Content "src\starsnip\__init__.py" -Raw
if ($initText -notmatch '__version__\s*=\s*"([\d.]+)"') { throw "读不到版本号" }
$ver = $Matches[1]
$tag = "v$ver"
if (-not $Force -and (git tag --list $tag)) {
    throw "tag $tag 已存在：发新版本请先 tools\set_version.py 升版本号；确实要重发这一版请加 -Force"
}
Write-Host "== 版本 $ver ($tag) ==" -ForegroundColor Cyan

Write-Host "== 打包 ==" -ForegroundColor Cyan
cmd /c "tools\build_exe.bat" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "打包失败" }
$exe = "dist\StarSnip.exe"
if (-not (Test-Path $exe)) { throw "没有生成 $exe" }

$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$size = [math]::Round((Get-Item $exe).Length / 1MB, 2)
"$hash  StarSnip.exe" | Set-Content -Encoding ascii "dist\SHA256SUMS.txt"
Write-Host ("   {0}  {1} MB  sha256={2}" -f $exe, $size, $hash)

$url = "https://github.com/NANYAN-01/StarSnip/releases/download/$tag/StarSnip.exe"
$vj = Get-Content "version.json" -Raw -Encoding utf8 | ConvertFrom-Json
$vj.version = $ver
$vj.url = "https://github.com/NANYAN-01/StarSnip/releases/tag/$tag"
$vj.assets.exe = $url
$vj.assets.sha256 = $hash
# 写 UTF-8 无 BOM（Windows PowerShell 的 -Encoding utf8 会带 BOM，
# 那样 update.check 解析清单会失败），写完立刻回读校验
$json = ($vj | ConvertTo-Json -Depth 5) + "`n"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $root "version.json"), $json, $utf8)
$check = Get-Content "version.json" -Raw -Encoding utf8 | ConvertFrom-Json
if ($check.version -ne $ver -or -not $check.assets.exe) { throw "version.json 写入异常" }
Write-Host "   已回填 version.json（下载地址 + sha256，UTF-8 无 BOM）"

if (-not $Push) {
    Write-Host ""
    Write-Host "下一步（确认无误后）：" -ForegroundColor Yellow
    Write-Host "  git add -A; git commit -m 'release: $tag'"
    Write-Host "  git tag $tag; git push; git push --tags"
    Write-Host "  gh release create $tag dist\StarSnip.exe -t '星剪 $ver' --generate-notes"
    return
}

git add version.json StarSnip.version src/starsnip/__init__.py README.md
if (git diff --cached --quiet) {
    Write-Host "   版本文件无变化，跳过提交"
} else {
    git commit -m "release: $tag" | Out-Null
}
git tag -f -a $tag -m "星剪 $ver"
git push
if ($Force) {
    git push --force origin "refs/tags/$tag"
} else {
    git push origin "refs/tags/$tag"
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "未安装 gh：tag 已推，请手动把 dist\StarSnip.exe 上传到 Release $tag" -ForegroundColor Yellow
    return
}
# 只上传 exe 和校验文件：dist\config.local.json 含本机内网信息，绝不上传
# 注意：PowerShell 5.1 会把原生命令的 stderr 当错误，脚本开头设了 Stop 会直接中断，
# 所以这里临时放宽，并用 $LASTEXITCODE 判断成败。
$ErrorActionPreference = "Continue"
cmd /c "gh release view $tag >nul 2>&1"
if ($LASTEXITCODE -eq 0) {
    Write-Host "   该 tag 已有 Release，覆盖上传资产"
    gh release upload $tag "dist\StarSnip.exe" "dist\SHA256SUMS.txt" --clobber
} else {
    gh release create $tag "dist\StarSnip.exe" "dist\SHA256SUMS.txt" --title "星剪 $ver" --generate-notes
}
if ($LASTEXITCODE -ne 0) { throw "gh 创建/上传 Release 失败（exit $LASTEXITCODE）" }
# 不要用 --jq：PowerShell 5.1 会把含空格的表达式拆成多个参数（gh 报「received N arg(s)」）
$rel = gh release view $tag --json url,assets | ConvertFrom-Json
Write-Host ("   Release: " + $rel.url)
foreach ($asset in $rel.assets) {
    Write-Host ("   资产: " + $asset.name + "  " + $asset.size + " B")
}
Write-Host "   发布完成（tag $tag + Release 资产）" -ForegroundColor Green
