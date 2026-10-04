#!/usr/bin/env bash
# GOSIM 巡天智能体 · 跑一张练习卡并打印分数细项
#
# 用法:
#   run_card.sh              # 默认跑 L4（最难）
#   run_card.sh L1           # 跑指定卡
#   run_card.sh L1 --real-llm  # 用 examples/python/.env 里的真实 key 跑（LLM 环节真生效）
#   run_card.sh --all        # 四张卡全跑，汇总对照
#
# 环境变量可覆盖: GOSIM_REPO / GOSIM_PY
set -euo pipefail

REPO="${GOSIM_REPO:-/Users/seth/Code/gosim-survey26}"
PY="${GOSIM_PY:-/Users/seth/.workbuddy/binaries/python/versions/3.13.12/bin/python3}"

if [ ! -d "$REPO" ]; then
  echo "官方仓不在 $REPO" >&2
  echo "先跑: git clone https://github.com/gosimfoundation/hackathon-survey26.git $REPO" >&2
  exit 1
fi

run_one() {
  local card="$1"; shift
  local real_llm=0
  for a in "$@"; do [ "$a" = "--real-llm" ] && real_llm=1; done

  if [ "$real_llm" = "1" ]; then
    echo "[$(date +%H:%M:%S)] $card —— 用真实 key（读 examples/python/.env）"
    "$PY" examples/_local/runner/run_local.py \
        --card "examples/_local/cards/$card" \
        --agent "$PY agent.py" --agent-cwd examples/python \
        --out "run_output/$card" --quiet
  else
    echo "[$(date +%H:%M:%S)] $card —— 占位 key（确定性基线，LLM 调用会被跳过）"
    OPENAI_API_KEY=local-debug-no-llm OPENAI_BASE_URL=http://127.0.0.1:9/v1 \
    "$PY" examples/_local/runner/run_local.py --inherit-env \
        --card "examples/_local/cards/$card" \
        --agent "$PY agent.py" --agent-cwd examples/python \
        --out "run_output/$card" --quiet
  fi
}

cd "$REPO"

if [ "${1:-}" = "--all" ]; then
  for c in L1 L2 L3 L4; do run_one "$c"; done
  echo
  echo "================= 汇总 ================="
  "$PY" - <<'EOF'
import json, pathlib
cards = [c for c in ["L1", "L2", "L3", "L4"] if (pathlib.Path("run_output") / c / "score_report.json").is_file()]
rows = {c: json.loads((pathlib.Path("run_output") / c / "score_report.json").read_text()) for c in cards}
comp = ["sum_best_scores", "required_penalty", "uniformity_penalty", "report_settlement", "observation_request_reward"]
cnt = ["required_missing", "observation_requests_completed", "observation_requests_issued", "invalidated_observations"]
print(f"{'项':<32}" + "".join(f"{c:>12}" for c in cards))
print(f"{'total':<32}" + "".join(f"{rows[c]['total']:>12,.1f}" for c in cards))
for k in comp:
    print(f"{k:<32}" + "".join(f"{rows[c]['components'].get(k, 0):>12,.1f}" for c in cards))
for k in cnt:
    print(f"{k:<32}" + "".join(f"{rows[c]['counts'].get(k, 0):>12}" for c in cards))
for c in cards:
    print(f"  {c}: termination={rows[c]['termination']['reason']}")
EOF
else
  CARD="${1:-L4}"
  run_one "$CARD" "$@"
  echo
  echo "================= 分数细项 ================="
  "$PY" - "$CARD" <<'EOF'
import json, pathlib, sys
card = sys.argv[1]
d = json.loads((pathlib.Path("run_output") / card / "score_report.json").read_text())
print(f"total = {d['total']:,.3f}   termination = {d['termination']['reason']}")
for k, v in d["components"].items():
    print(f"  {k:<30} {v:>12,.3f}")
print("  --- counts ---")
for k, v in d["counts"].items():
    print(f"  {k:<30} {v:>12}")
EOF
  echo "产物: $REPO/run_output/$CARD/"
fi
