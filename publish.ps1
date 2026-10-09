# 发布前处理脚本：替换占位符 -> 校验 -> git 初始化 -> 打印推送与安装指令
#
# 用法：
#   .\publish.ps1 -Owner mygithub
#   .\publish.ps1 -Owner mygithub -Repo <repo-name> -Version 1.0.1 -Tag
#   .\publish.ps1 -Owner mygithub -ValidateOnly
#   .\publish.ps1 -Owner mygithub -RunSelfTest      # 会联网跑完整自检

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Owner,

    [string]$Repo = 'company-deep-analysis',
    [string]$Version = '',
    [switch]$ValidateOnly,
    [switch]$RunSelfTest,
    [switch]$Tag,
    [switch]$NoGit
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$skillDir = Join-Path $root 'plugins\company-deep-analysis\skills\company-deep-analysis'
$fail = 0

function Section($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }
function OK($m) { Write-Host "  [OK]   $m" -ForegroundColor Green }
function WARN($m) { Write-Host "  [warn] $m" -ForegroundColor Yellow }
function ERR($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; $script:fail++ }

Section "1. 替换占位符"

# SAFETY: the tokens are assembled at runtime so this script's own source never
# contains them in a form that a previous run could have rewritten. A prior
# version did a plain global replace, which rewrote the script itself into a
# runaway substitution - never template a file against literals it also holds.
$TokOwner  = '@' + '@OWNER' + '@@'
$TokRepo   = '@' + '@REPO' + '@@'
$TokSlug   = '@' + '@SLUG' + '@@'      # owner/repo
$TokAtRepo = '@' + '@ATREPO' + '@@'    # @repo - plugin refs need the @ separator, so
                                       # it must not be part of the plain @@REPO@@ token
$thisName = Split-Path $PSCommandPath -Leaf

$stampFiles = Get-ChildItem $root -Recurse -File |
    Where-Object {
        $_.FullName -notlike '*\.git\*' -and
        ($_.Extension -in @('.md', '.json', '.ps1', '.sh') -or $_.Name -eq 'LICENSE')
    }

$changed = 0
$pending = 0
foreach ($f in $stampFiles) {
    $t = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
    $orig = $t

    # Never stamp this script: it is the stamper, not a template.
    if ($f.Name -ne $thisName) {
        $t = $t.Replace($TokSlug,   "$Owner/$Repo")
        $t = $t.Replace($TokAtRepo, "@$Repo")
        $t = $t.Replace($TokOwner,  $Owner)
        $t = $t.Replace($TokRepo,   $Repo)
    }
    if ($Version -and $f.Name -eq 'plugin.json') {
        $t = $t -replace '("version"\s*:\s*")[^"]+(")', "`${1}$Version`${2}"
    }

    if ($t -ne $orig) {
        $pending++
        if ($ValidateOnly) {
            Write-Host "  [dry-run] 将更新 $($f.FullName.Replace($root, '.'))"
        } else {
            [System.IO.File]::WriteAllText($f.FullName, $t, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "  更新 $($f.FullName.Replace($root, '.'))"
            $changed++
        }
    }
}
if ($pending -eq 0) {
    Write-Host "  （无占位符需要替换，说明已是最终状态）"
} elseif ($ValidateOnly) {
    OK "$pending 个文件待替换（dry-run，未写入）"
} else {
    OK "$changed 个文件已更新"
}

# 残留占位符检查（排除 stamper 自身）
if (-not $ValidateOnly) {
    $residual = @()
    foreach ($f in $stampFiles) {
        if ($f.Name -eq $thisName) { continue }
        $t = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
        if ($t.Contains($TokOwner) -or $t.Contains($TokRepo)) { $residual += $f.Name }
    }
    if ($residual.Count -gt 0) { WARN "以下文件仍含未替换占位符（多为注释示例）: $($residual -join ', ')" }
}

Section "2. SKILL.md frontmatter 校验"
$skillMd = Join-Path $skillDir 'SKILL.md'
if (-not (Test-Path $skillMd)) { ERR "缺少 SKILL.md"; }
else {
    $lines = Get-Content $skillMd -Encoding UTF8
    if ($lines[0] -ne '---') { ERR "SKILL.md 首行必须是 ---" }
    $end = ($lines | Select-Object -Skip 1 | Select-String -Pattern '^---$' | Select-Object -First 1).LineNumber
    if (-not $end) { ERR "frontmatter 未闭合" }
    else {
        $fm = $lines[1..($end - 1)] -join "`n"
        $nameM = [regex]::Match($fm, '(?m)^name:\s*(.+?)\s*$')
        $descM = [regex]::Match($fm, '(?m)^description:\s*(.+?)\s*$')
        if (-not $nameM.Success) { ERR "frontmatter 缺 name" }
        else {
            $n = $nameM.Groups[1].Value.Trim()
            if ($n -ne (Split-Path $skillDir -Leaf)) { ERR "name ($n) 与目录名不一致" }
            else { OK "name: $n" }
        }
        if (-not $descM.Success) { ERR "frontmatter 缺 description" }
        else {
            $d = $descM.Groups[1].Value.Trim()
            if ($d.Length -lt 80) { WARN "description 偏短（$($d.Length) 字符），触发条件可能不足" }
            else { OK "description: $($d.Length) 字符" }
        }
    }
}

Section "3. 必需文件与结构"
$required = @(
    'SKILL.md',
    'README.md',
    'requirements.txt',
    'scripts/bootstrap.py', 'scripts/_deps.py',
    'scripts/preflight.py', 'scripts/fetch_financials.py', 'scripts/fetch_price_dividends.py',
    'scripts/fetch_primary_source.py', 'scripts/compute_metrics.py', 'scripts/verify_report.py',
    'scripts/selftest.py', 'scripts/_common.py',
    'references/00-buy-checklist.md',
    'references/01-report-template.md', 'references/02-checklist-mapping.md',
    'references/03-data-verification.md', 'references/04-market-adapters.md',
    'references/05-holders-insiders-officials.md', 'references/06-valuation-and-margin.md',
    'references/07-evidence-grading.md',
    'assets/example-report-google-20261008.md', 'assets/quality-gate.md'
)
foreach ($r in $required) {
    $p = Join-Path $skillDir ($r -replace '/', '\')
    if (-not (Test-Path $p)) { ERR "缺少 $r" }
}
if ($fail -eq 0) { OK "$($required.Count) 个必需文件齐备" }

# 不该发布的东西
$junk = Get-ChildItem $root -Recurse -Directory -Include '__pycache__', '.pytest_cache' -ErrorAction SilentlyContinue
if ($junk) { WARN "发现缓存目录，建议删除：$($junk.FullName -join ', ')" }
$logs = Get-ChildItem $root -Recurse -File -Include '_*.log', '_*.txt', 'probe_*' -ErrorAction SilentlyContinue
if ($logs) { WARN "发现疑似临时文件：$($logs.Name -join ', ')" }

Section "4. Python 脚本语法编译"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { WARN "未找到 python，跳过语法检查" }
else {
    $scripts = Get-ChildItem (Join-Path $skillDir 'scripts') -Filter '*.py'
    $bad = 0
    foreach ($s in $scripts) {
        $out = & python -m py_compile $s.FullName 2>&1
        if ($LASTEXITCODE -ne 0) { ERR "$($s.Name) 语法错误: $out"; $bad++ }
    }
    if ($bad -eq 0) { OK "$($scripts.Count) 个脚本语法检查通过" }
    Get-ChildItem (Join-Path $skillDir 'scripts') -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Section "5. JSON 清单校验"
foreach ($j in @('.claude-plugin\marketplace.json', 'plugins\company-deep-analysis\.claude-plugin\plugin.json')) {
    $p = Join-Path $root $j
    if (-not (Test-Path $p)) { ERR "缺少 $j"; continue }
    try {
        $obj = Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($j -like '*marketplace*') {
            if (-not $obj.plugins -or $obj.plugins.Count -eq 0) { ERR "marketplace.json 没有 plugins 条目" }
            else {
                $srcPath = Join-Path $root ($obj.plugins[0].source -replace '^\./', '' -replace '/', '\')
                if (-not (Test-Path $srcPath)) { ERR "marketplace 指向的插件路径不存在: $($obj.plugins[0].source)" }
                else { OK "marketplace.json 有效，source -> $($obj.plugins[0].source)" }
            }
        } else {
            if (-not $obj.name) { ERR "plugin.json 缺 name" } else { OK "plugin.json 有效 ($($obj.name) v$($obj.version))" }
        }
    } catch { ERR "$j 不是合法 JSON: $($_.Exception.Message)" }
}

if ($RunSelfTest -and $fail -eq 0) {
    Section "6. 端到端自检（联网）"
    Push-Location (Join-Path $skillDir 'scripts')
    try {
        & python selftest.py --market us --symbol GOOGL --out (Join-Path $env:TEMP 'cda_publish_selftest')
        if ($LASTEXITCODE -ne 0) { ERR "自检未通过" } else { OK "自检全部通过" }
    } finally { Pop-Location }
}

if ($ValidateOnly) {
    Section "结果"
    if ($fail -eq 0) { Write-Host "  校验通过，可以发布。" -ForegroundColor Green; exit 0 }
    Write-Host "  发现 $fail 个错误，请修复后重试。" -ForegroundColor Red; exit 1
}

Section "6. Git 初始化与提交"
$full = "$Owner/$Repo"
if ($NoGit) { WARN "已跳过 git 操作" }
else {
    Push-Location $root
    try {
        if (-not (Test-Path (Join-Path $root '.git'))) {
            git init -q
            git branch -M main 2>$null
            OK "git init"
        } else { OK "已是 git 仓库" }
        git add -A
        $msg = "feat: company-deep-analysis skill v$(if ($Version) { $Version } else { '1.0.0' })"
        git -c user.name="$Owner" -c user.email="$Owner@users.noreply.github.com" commit -q -m $msg 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { OK "已提交: $msg" } else { WARN "无新变更或提交失败（可忽略）" }
        $hasRemote = (git remote 2>$null) -contains 'origin'
        if (-not $hasRemote) { git remote add origin "https://github.com/$full.git"; OK "已添加 remote origin" }
        else { OK "remote origin 已存在" }

        Section "下一步：推送到 GitHub"
        Write-Host "  cd `"$root`""
        Write-Host "  git push -u origin main"
        Write-Host ""
        Write-Host "  若仓库尚未创建，先去 https://github.com/new 建一个空的 public 仓库：$Repo"
        Write-Host "  （不要勾选 README / .gitignore / LICENSE，避免首推冲突）"
        if ($Tag) {
            Write-Host ""
            Write-Host "  git tag -a v$(if ($Version) { $Version } else { '1.0.0' }) -m `"release`""
            Write-Host "  git push origin --tags"
        }
    } finally { Pop-Location }
}

Section "推送后：各 agent 的一键安装指令"
Write-Host ""
Write-Host "  --- Claude Code（插件市场，最省事）---" -ForegroundColor White
Write-Host "    /plugin marketplace add $full"
Write-Host "    /plugin install company-deep-analysis@$Repo"
Write-Host ""
Write-Host "  --- OpenAI Codex ---" -ForegroundColor White
Write-Host "    # 用内置的 skill-installer 技能（推荐）"
Write-Host "    #   在 Codex 里说：安装 $full 的 skills 路径 plugins/company-deep-analysis/skills/company-deep-analysis"
Write-Host "    # 或直接跑它的脚本："
Write-Host "    python `"`$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py`" ``"
Write-Host "        --repo $full --path plugins/company-deep-analysis/skills/company-deep-analysis"
Write-Host ""
Write-Host "    # 或把本仓库加为 Codex git marketplace（写入 ~/.codex/config.toml）"
Write-Host "    # [marketplaces.$Repo]"
Write-Host "    # source_type = `"git`""
Write-Host "    # source = `"https://github.com/$full.git`""
Write-Host ""
Write-Host "  --- DeepSeek Harness / 任意 agent（通用）---" -ForegroundColor White
Write-Host "    Windows:"
Write-Host "      irm https://raw.githubusercontent.com/$full/main/install.ps1 | iex"
Write-Host "    macOS / Linux:"
Write-Host "      curl -fsSL https://raw.githubusercontent.com/$full/main/install.sh | bash"
Write-Host ""
Write-Host "  --- 只装某一个 agent ---" -ForegroundColor White
Write-Host "      ... | iex 之前加参数，或克隆后：.\install.ps1 -Target claude"
Write-Host "      curl -fsSL .../install.sh | bash -s -- --target codex"
Write-Host ""
Write-Host "  --- 手动（任何 agent 都能用）---" -ForegroundColor White
Write-Host "    git clone --depth 1 https://github.com/$full.git"
Write-Host "    # 然后把 plugins/company-deep-analysis/skills/company-deep-analysis"
Write-Host "    # 复制到该 agent 的 skills 目录"
Write-Host ""

Section "结果"
if ($fail -eq 0) { Write-Host "  完成。校验 0 错误。" -ForegroundColor Green; exit 0 }
Write-Host "  发现 $fail 个错误。" -ForegroundColor Red; exit 1
