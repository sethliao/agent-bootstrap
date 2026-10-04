#!/usr/bin/env bash
# drama-tts.sh — 查看/切换 DramaClaw 网关 TTS 后端与声线，快速试听。
#
# 用法:
#   drama-tts.sh status          当前 provider / voice
#   drama-tts.sh list            列出可选声线
#   drama-tts.sh set <voice>     切声线（Edge 男声优先，如 zh-CN-YunxiNeural）
#   drama-tts.sh provider <name> 切后端（edge_tts | volc_tts）
#   drama-tts.sh test ["文本"]   用当前声线生成试听并打开
set -u

INI="$HOME/.hermes/drama-gateway/providers.ini"
GW="http://127.0.0.1:8790"
GW_SCRIPT="$HOME/Code/drama-claw-hermes/agy-shim/drama_gateway.py"
LOG_DIR="$HOME/Code/drama-claw-hermes/logs"

now() { sed -n '/^\[audio\]/,/^\[/p' "$INI" 2>/dev/null | grep -E '^(provider|voice)' | sed 's/^\(provider\|voice\) *= *//'; }

restart_gateway() {
  PID=$(lsof -nP -iTCP:8790 -sTCP:LISTEN -t 2>/dev/null)
  [ -n "$PID" ] && kill "$PID" 2>/dev/null && sleep 1
  mkdir -p "$LOG_DIR"
  nohup /usr/bin/python3 "$GW_SCRIPT" --port 8790 >>"$LOG_DIR/gateway.log" 2>&1 &
  disown
  for _ in $(seq 1 25); do curl -fsS -m 2 "$GW/healthz" >/dev/null 2>&1 && break; sleep 1; done
  echo "gateway 已重启 ($(curl -s "$GW/healthz"))"
}

set_ini() {  # set_ini <key> <value>
  if grep -q "^\[audio\]" "$INI"; then
    if grep -q "^$1 *= *" "$INI"; then
      sed -i '' -E "s|^$1 *= *.*|$1 = $2|" "$INI"
    else
      sed -i '' -E "s|^(\[audio\])|\1\n$1 = $2|" "$INI"
    fi
  else
    printf '\n[audio]\n%s = %s\n' "$1" "$2" >>"$INI"
  fi
}

case "${1:-status}" in
  status)
    echo "当前 TTS: provider=$(now | grep provider | cut -d= -f2)  voice=$(now | grep voice | cut -d= -f2)"
    ;;
  list)
    echo "英文男声（对白默认英文时用）:"
    echo "  en-US-GuyNeural             Guy · 阳光少年（当前默认）"
    echo "  en-US-ChristopherNeural     Christopher · 温暖沉稳"
    echo "  en-US-AndrewNeural          Andrew · 平静友好"
    echo "  en-US-AndrewMultilingualNeural  Andrew 多语言 · 中英混读"
    echo "  en-GB-RyanNeural            Ryan · 英音"
    echo "  en-NZ-MitchellNeural        Mitchell · 纽村口音"
    echo "Edge 中文男声:"
    echo "  zh-CN-YunjianNeural  云健 · 温暖少年"
    echo "  zh-CN-YunxiNeural    云希 · 活泼"
    echo "  zh-CN-YunxiaNeural   云夏 · 少年"
    echo "  zh-CN-YunyangNeural  云扬 · 沉稳/新闻"
    echo "Edge 中文女声:"
    echo "  zh-CN-XiaoxiaoNeural 晓晓 / zh-CN-XiaoyiNeural 晓伊"
    echo "后端: edge_tts（免费）| volc_tts（火山 doubao, 需 ARK_API_KEY）"
    ;;
  set)
    [ $# -lt 2 ] && { echo "用法: drama-tts.sh set <voice>"; exit 1; }
    set_ini voice "$2"
    restart_gateway
    echo "已切换声线 → $2"
    ;;
  provider)
    [ $# -lt 2 ] && { echo "用法: drama-tts.sh provider <edge_tts|volc_tts>"; exit 1; }
    set_ini provider "$2"
    restart_gateway
    echo "已切换后端 → $2"
    ;;
  test)
    TEXT="${2:-你好，我是莫莫，一只住在唐人街的小熊猫。}"
    OUT="/tmp/drama-tts-test.mp3"
    curl -s -X POST "$GW/v1/audio/speech" -H 'Content-Type: application/json' \
      -d "{\"input\":\"$TEXT\"}" -o "$OUT" -w "HTTP %{http_code}, %{size_download}B\n"
    [ -s "$OUT" ] && open "$OUT" && echo "已打开试听: $OUT"
    ;;
  *) echo "用法: drama-tts.sh {status|list|set <voice>|provider <name>|test [文本]}"; exit 1;;
esac
