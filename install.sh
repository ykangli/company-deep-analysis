#!/usr/bin/env bash
# 通用一键安装脚本（macOS / Linux）
#
# 用法一（从克隆的仓库运行）：
#   git clone --depth 1 https://github.com/ykangli/company-deep-analysis.git
#   cd company-deep-analysis && ./install.sh
#   ./install.sh --target claude
#   ./install.sh --target all
#
# 用法二（不克隆，一行）：
#   curl -fsSL https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --target all
#
# 用法三（本地目录，开发调试）：
#   ./install.sh --source ./plugins/company-deep-analysis/skills/company-deep-analysis

set -euo pipefail

SKILL_NAME="company-deep-analysis"
TARGET="auto"
REPO=""
SOURCE=""
REF="main"
DEST=""
FORCE=0
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --repo)   REPO="$2";   shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --ref)    REF="$2";    shift 2 ;;
    --dest)   DEST="$2";   shift 2 ;;
    --force)  FORCE=1;     shift ;;
    --quiet)  QUIET=1;     shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

c_ok()   { printf '  \033[32m[OK]\033[0m   %s\n' "$1"; }
c_skip() { printf '  \033[90m[skip]\033[0m %s\n' "$1"; }
c_warn() { printf '  \033[33m[warn]\033[0m %s\n' "$1"; }
c_fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$1"; }
say()    { [ "$QUIET" = "1" ] || printf '%s\n' "$1"; }
head()   { [ "$QUIET" = "1" ] || { printf '\n==============================================================\n %s\n==============================================================\n' "$1"; }; }

head "$SKILL_NAME 安装器"

# ---------------------------------------------------------------- 源目录
resolve_source() {
  if [ -n "$SOURCE" ]; then
    [ -f "$SOURCE/SKILL.md" ] || { echo "-source 目录缺少 SKILL.md: $SOURCE" >&2; exit 1; }
    (cd "$SOURCE" && pwd); return
  fi
  # 脚本所在仓库内的 skill
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  local cand="$script_dir/plugins/$SKILL_NAME/skills/$SKILL_NAME"
  if [ -f "$cand/SKILL.md" ]; then (cd "$cand" && pwd); return; fi

  [ -n "$REPO" ] || { echo "无法定位 skill。请用 --source 指定，或用 --repo owner/name 远程拉取。" >&2; exit 1; }

  local tmp
  tmp="$(mktemp -d)"
  say "克隆 https://github.com/$REPO.git ($REF) -> $tmp"
  git clone --depth 1 --branch "$REF" "https://github.com/$REPO.git" "$tmp" >/dev/null 2>&1 \
    || { echo "git clone 失败（检查仓库名/网络/git）" >&2; exit 1; }
  cand="$tmp/plugins/$SKILL_NAME/skills/$SKILL_NAME"
  [ -f "$cand/SKILL.md" ] || { echo "克隆成功但未找到 $cand" >&2; exit 1; }
  (cd "$cand" && pwd)
}

SRC="$(resolve_source)"
say "源目录: $SRC"

for f in SKILL.md scripts/verify_report.py references/01-report-template.md assets/quality-gate.md; do
  [ -e "$SRC/$f" ] || { c_fail "源目录缺少必需文件: $f"; exit 1; }
done
c_ok "源目录校验通过（SKILL.md / scripts / references / assets 齐备）"

# ---------------------------------------------------------------- 目标
HOME_DIR="${HOME:-$USERPROFILE}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME_DIR/.codex}"
DSH_HOME_DIR="${DSH_HOME:-$HOME_DIR/.dsh}"

all_targets() {
  echo "claude|$HOME_DIR/.claude/skills|$HOME_DIR/.claude"
  echo "codex|$CODEX_HOME_DIR/skills|$CODEX_HOME_DIR"
  echo "dsh|$DSH_HOME_DIR/skills|$DSH_HOME_DIR"
  echo "agents|$HOME_DIR/.agents/skills|$HOME_DIR/.agents"
  echo "project|$PWD/.agents/skills|$PWD"
}

select_targets() {
  case "$TARGET" in
    all) all_targets ;;
    auto)
      local hits
      hits="$(all_targets | while IFS='|' read -r n p r; do
                if [ -d "$r" ] || [ -d "$p" ]; then echo "$n|$p|$r"; fi
              done)"
      if [ -z "$hits" ]; then
        c_warn "未检测到任何已知 agent 目录，默认安装到 claude / codex / dsh"
        all_targets | grep -E '^(claude|codex|dsh)\|'
      else
        echo "$hits"
      fi ;;
    claude|codex|dsh|agents|project) all_targets | grep "^$TARGET|" ;;
    *) echo "未知 --target: $TARGET" >&2; exit 2 ;;
  esac
}

say ""
say "安装目标:"

installed=""
count=0
if [ -n "$DEST" ]; then
  set -- "custom|$DEST|$DEST"
else
  # shellcheck disable=SC2046
  set -- $(select_targets)
fi

for entry in "$@"; do
  name="${entry%%|*}"
  rest="${entry#*|}"
  root="${rest%%|*}"
  dest="$root/$SKILL_NAME"
  if [ -d "$dest" ]; then
    if [ "$FORCE" = "1" ]; then
      [ "$(basename "$dest")" = "$SKILL_NAME" ] || { c_fail "拒绝删除非目标目录: $dest"; continue; }
      rm -rf "$dest"
    else
      c_skip "$name: 已存在（加 --force 覆盖）-> $dest"
      continue
    fi
  fi
  mkdir -p "$root"
  cp -R "$SRC" "$dest"
  find "$dest" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
  n="$(find "$dest" -type f | wc -l | tr -d ' ')"
  c_ok "$name: $n 个文件 -> $dest"
  installed="$installed $dest"
  count=$((count + 1))
done

say ""
head "结果"
if [ "$count" -gt 0 ]; then
  printf ' 安装完成，共 %s 处：\n' "$count"
  for i in $installed; do printf '   %s\n' "$i"; done
  printf '\n 验证安装：\n'
  first="$(echo "$installed" | awk '{print $1}')"
  printf '   python "%s/scripts/preflight.py" --market us --symbol GOOGL\n' "$first"
  printf '\n 使用方式（对 agent 说）：\n'
  printf '   用 company-deep-analysis 分析一下 <公司名>(<代码>)\n'
else
  c_warn "没有任何位置被安装（可能全部已存在）。加 --force 覆盖。"
fi
printf '\n 提示：本工具仅生成研究报告，不构成投资建议。\n'
