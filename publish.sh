#!/usr/bin/env bash
# publish.sh - Git Bash / MSYS / WSL entry point for the maintainer tool.
#
# publish.ps1 is a PowerShell script: a POSIX shell cannot execute it. Running
# "./publish.ps1" from Git Bash fails with an error like:
#     ./publish.ps1: line 1: $'\357\273\277#': command not found
# where \357\273\277 is the UTF-8 BOM. Use this wrapper instead:
#
#     ./publish.sh -Owner <your-github-user> -ValidateOnly
#     ./publish.sh -Owner <your-github-user>
#
# All arguments are forwarded verbatim to publish.ps1.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPT="$DIR/publish.ps1"

if [ ! -f "$SCRIPT" ]; then
  echo "publish.sh: cannot find publish.ps1 next to this script ($DIR)" >&2
  exit 1
fi

# Prefer PowerShell 7 (pwsh) when present, else Windows PowerShell 5.1.
PS=""
for c in pwsh.exe pwsh powershell.exe powershell; do
  if command -v "$c" >/dev/null 2>&1; then PS="$c"; break; fi
done

if [ -z "$PS" ]; then
  cat >&2 <<'EOF'
publish.sh: no PowerShell interpreter found on PATH.

This maintainer tool (publish.ps1) needs Windows PowerShell or PowerShell 7.
On Linux/macOS without PowerShell, do the equivalent steps by hand:
  1. replace ykangli / company-deep-analysis / ykangli/company-deep-analysis / @company-deep-analysis in README.md,
     LICENSE, install.ps1, install.sh, and the two .claude-plugin JSON files
  2. git init && git add -A && git commit -m "release"
  3. git remote add origin https://github.com/<owner>/<repo>.git
  4. git push -u origin main
EOF
  exit 127
fi

# cd into the repo so PowerShell receives a simple relative path; MSYS would
# otherwise hand it a /d/... path that PowerShell cannot resolve.
cd "$DIR"
exec "$PS" -NoProfile -ExecutionPolicy Bypass -File ./publish.ps1 "$@"
