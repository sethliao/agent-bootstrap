#!/bin/bash
# drama-mcp-launcher.sh — 在 drama-claw repo 里启动 dramaclaw MCP server
# Hermes 的 mcp_servers 配置:
#   command: ~/Code/drama-claw-hermes/bin/drama-mcp-launcher.sh
#   env: DRAMACLAW_API_URL=http://127.0.0.1:8780, DRAMACLAW_CE_OWNER=1
cd ~/Code/drama-claw || exit 1
exec uv run python -m novelvideo.chat.dramaclaw_mcp
