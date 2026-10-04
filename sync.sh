#!/bin/bash
# agent-bootstrap · sync.sh —— 真源 <-> 本仓 双向同步
# 用法: bash sync.sh push|pull
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
WB="$HOME/.workbuddy/skills"
MODE="${1:-}"
[ -z "$MODE" ] && { echo "用法: bash sync.sh push|pull"; exit 1; }

sync_one() {
  local name="$1" from="$2" to="$3"
  if [ ! -d "$from/$name" ]; then echo "    ⚠️ 源不存在: $name"; return; fi
  rm -rf "$to/$name"
  cp -R "$from/$name" "$to/$name"
  echo "    ok $name"
}

for d in "$SRC"/skills/*/; do
  name=$(basename "$d")
  if [ "$MODE" = "push" ]; then sync_one "$name" "$SRC/skills" "$WB"; else sync_one "$name" "$WB" "$SRC/skills"; fi
done
echo "==> sync $MODE 完成（记得 git add -A && git commit）"
