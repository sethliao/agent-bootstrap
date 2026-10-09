#!/bin/bash
# agent-bootstrap · install.sh —— 新机器恢复运行前配置
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
WB="$HOME/.workbuddy"

echo "==> 1/3 拷贝 skills -> $WB/skills/（已存在的跳过）"
mkdir -p "$WB/skills"
for d in "$SRC"/skills/*/; do
  name=$(basename "$d")
  if [ -e "$WB/skills/$name" ]; then
    echo "    skip $name（已存在）"
  else
    cp -R "$d" "$WB/skills/$name"
    echo "    ok   $name"
  fi
done

echo "==> 1.5/3 拷贝 chains -> $WB/chains/（链注册表，agent 运行时读这里）"
mkdir -p "$WB/chains"
cp "$SRC"/chains/REGISTRY.md "$WB/chains/REGISTRY.md"
echo "    ok chains/REGISTRY.md"

echo "==> 2/3 拷贝 mcp.json -> $WB/mcp.json"
if [ -f "$WB/mcp.json" ]; then
  cp "$WB/mcp.json" "$WB/mcp.json.bak-$(date +%Y%m%d-%H%M%S)"
  echo "    已备份旧 mcp.json，新文件合并请手动核对（不直接覆盖）"
  echo "    模板在 $SRC/mcp/mcp.json"
else
  cp "$SRC/mcp/mcp.json" "$WB/mcp.json"
  echo "    ok"
fi

echo "==> 3/3 提醒（需手动）"
cat <<'EOF'
- keychain 写入 API key：security add-generic-password -a seth -s <svc> -w '<key>'
  （svc 清单和 key 值见 vault System/AI-API-清单.md）
- CLI 安装：见仓库 CLI-清单.md
- WorkBuddy 连接器页 → 自定义连接器 → 对新 MCP server 点「信任」
- vault 本体不在本仓：从 iCloud / 备份 zip 恢复 $VAULT_PATH
EOF
echo "==> 完成"
