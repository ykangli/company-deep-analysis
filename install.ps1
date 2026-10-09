# company-deep-analysis - universal installer for Windows / PowerShell
#
# NOTE: this bootstrap script is intentionally ASCII-only. Windows PowerShell 5.1
# reads .ps1 files using the system ANSI code page unless the file has a UTF-8
# BOM, which turns non-ASCII comments and strings into parse errors. The skill
# payload itself (SKILL.md, references, generated reports) is Chinese; only this
# installer speaks English so it can never fail on an unknown locale.
#
# Usage A - from a clone (recommended):
#   git clone --depth 1 https://github.com/ykangli/company-deep-analysis.git
#   cd company-deep-analysis
#   .\install.ps1                  # auto-detect installed agents
#   .\install.ps1 -Target claude   # one agent only
#   .\install.ps1 -Target all      # every known location
#
# Usage B - no clone, one line (bypasses execution policy because nothing is
# loaded from disk, so no signature check applies):
#   irm https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.ps1 | iex
#
# Usage C - local development:
#   .\install.ps1 -Source .\plugins\company-deep-analysis\skills\company-deep-analysis -Target project

[CmdletBinding()]
param(
    [ValidateSet('auto', 'all', 'claude', 'codex', 'dsh', 'agents', 'project')]
    [string]$Target = 'auto',

    # GitHub repo (owner/name) for remote install. Leave empty when running from a clone.
    [string]$Repo = '',

    # Explicit skill directory (overrides auto-detection).
    [string]$Source = '',

    [string]$Ref = 'main',

    # Explicit single destination root.
    [string]$Dest = '',

    [switch]$Force,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$SkillName = 'company-deep-analysis'

function Say($msg) { if (-not $Quiet) { Write-Host $msg } }
function Ok($msg)   { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Skip($msg) { Write-Host "  [skip] $msg" -ForegroundColor DarkGray }
function Warn($msg) { Write-Host "  [warn] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

function Resolve-Source {
    param([string]$Explicit, [string]$RepoSpec, [string]$ScriptPath)

    if ($Explicit) {
        if (-not (Test-Path (Join-Path $Explicit 'SKILL.md'))) {
            throw "-Source directory has no SKILL.md: $Explicit"
        }
        return (Resolve-Path $Explicit).Path
    }

    # Prefer the skill inside the repo this script lives in.
    if ($ScriptPath) {
        $cand = Join-Path (Split-Path $ScriptPath -Parent) "plugins\$SkillName\skills\$SkillName"
        if (Test-Path (Join-Path $cand 'SKILL.md')) { return (Resolve-Path $cand).Path }
    }

    if (-not $RepoSpec) {
        throw "Cannot locate the skill. Pass -Source <dir>, or -Repo owner/name to fetch it."
    }

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("cda_" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    Say "Cloning https://github.com/$RepoSpec.git ($Ref) -> $tmp"
    git clone --depth 1 --branch $Ref "https://github.com/$RepoSpec.git" $tmp 2>&1 | ForEach-Object { Say "    $_" }
    if ($LASTEXITCODE -ne 0) { throw "git clone failed (check repo name, network, and that git is installed)" }
    $cand = Join-Path $tmp "plugins\$SkillName\skills\$SkillName"
    if (-not (Test-Path (Join-Path $cand 'SKILL.md'))) { throw "Clone succeeded but $cand is missing" }
    return $cand
}

function Get-Targets {
    param([string]$Which, [string]$ExplicitDest)

    if ($ExplicitDest) {
        return @([pscustomobject]@{ Name = 'custom'; Path = $ExplicitDest; Root = $ExplicitDest })
    }

    $userHome = $env:USERPROFILE
    if (-not $userHome) { $userHome = $HOME }

    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $userHome '.codex' }
    $dshHome   = if ($env:DSH_HOME)   { $env:DSH_HOME }   else { Join-Path $userHome '.dsh' }
    $cwd       = (Get-Location).Path

    $all = @(
        [pscustomobject]@{ Name = 'claude';  Path = (Join-Path $userHome '.claude\skills'); Root = (Join-Path $userHome '.claude') },
        [pscustomobject]@{ Name = 'codex';   Path = (Join-Path $codexHome 'skills');       Root = $codexHome },
        [pscustomobject]@{ Name = 'dsh';     Path = (Join-Path $dshHome 'skills');         Root = $dshHome },
        [pscustomobject]@{ Name = 'agents';  Path = (Join-Path $userHome '.agents\skills'); Root = (Join-Path $userHome '.agents') },
        [pscustomobject]@{ Name = 'project'; Path = (Join-Path $cwd '.agents\skills');     Root = $cwd }
    )

    if ($Which -eq 'all') { return $all }
    if ($Which -eq 'auto') {
        $hits = @($all | Where-Object { (Test-Path $_.Root) -or (Test-Path $_.Path) })
        if ($hits.Count -eq 0) {
            Warn "No known agent directory detected; installing to claude / codex / dsh"
            return @($all | Where-Object { $_.Name -in @('claude', 'codex', 'dsh') })
        }
        return $hits
    }
    return @($all | Where-Object { $_.Name -eq $Which })
}

Say ""
Say "=============================================================="
Say " company-deep-analysis installer"
Say "=============================================================="

$scriptPath = $PSCommandPath
if (-not $scriptPath) { $scriptPath = $MyInvocation.MyCommand.Path }

$src = Resolve-Source -Explicit $Source -RepoSpec $Repo -ScriptPath $scriptPath
Say "Source: $src"

$required = @('SKILL.md', 'scripts\verify_report.py', 'references\01-report-template.md', 'assets\quality-gate.md')
$missing = @($required | Where-Object { -not (Test-Path (Join-Path $src $_)) })
if ($missing.Count -gt 0) { throw "Source is missing required files: $($missing -join ', ')" }
Ok "Source verified (SKILL.md / scripts / references / assets all present)"

$targets = @(Get-Targets -Which $Target -ExplicitDest $Dest)
Say ""
Say "Targets:"

$installed = @()
foreach ($t in $targets) {
    $destRoot = $t.Path
    $dest = Join-Path $destRoot $SkillName
    try {
        if (-not (Test-Path $destRoot)) {
            New-Item -ItemType Directory -Force -Path $destRoot | Out-Null
            Say "  created $destRoot"
        }
        if (Test-Path $dest) {
            if ($Force) {
                if ((Split-Path $dest -Leaf) -ne $SkillName) { throw "Refusing to delete non-target directory: $dest" }
                Remove-Item $dest -Recurse -Force
            } else {
                Skip "$($t.Name): already installed (use -Force to overwrite) -> $dest"
                continue
            }
        }
        Copy-Item $src $dest -Recurse -Force
        Get-ChildItem $dest -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        $n = @(Get-ChildItem $dest -Recurse -File).Count
        Ok "$($t.Name): $n files -> $dest"
        $installed += $dest
    } catch {
        Fail "$($t.Name): $($_.Exception.Message)"
    }
}

Say ""
Say "=============================================================="
if ($installed.Count -gt 0) {
    Say " Installed to $($installed.Count) location(s):"
    $installed | ForEach-Object { Say "   $_" }
    Say ""
    Say " Verify the install:"
    Say "   python `"$($installed[0])\scripts\preflight.py`" --market us --symbol GOOGL"
    Say ""
    Say " Then ask your agent:"
    Say "   Use company-deep-analysis to analyse <company> (<ticker>)"
} else {
    Say " Nothing installed (everything already present). Use -Force to overwrite."
}
Say "=============================================================="
Say ""
Say "Research aid only. Not investment advice."
