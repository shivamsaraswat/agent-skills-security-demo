#!/usr/bin/env bash
# Agent Skills supply-chain security: live demo driver.
#   ./run_demo.sh            interactive (press Enter between steps)
#   ./run_demo.sh --auto     no pauses (rehearsal / CI)
#   ./run_demo.sh act3       jump to one act (act1 | act2 | act3 | act4)
#
# Keep `python3 attacker/listener.py` running in a second terminal pane.
# If it isn't running, this script starts it in the background.
set -u
cd "$(dirname "$0")"

AUTO=0; ONLY=""
for arg in "$@"; do
  case "$arg" in --auto) AUTO=1 ;; act*) ONLY="$arg" ;; esac
done

B=$'\033[1m'; D=$'\033[2m'; C=$'\033[36m'; M=$'\033[35m'; R=$'\033[0m'
GATE="python3 gate/skill_gate.py"
AGENT="python3 agent/naive_agent.py"

banner() { echo; echo "${M}${B}━━━ $1 ━━━${R}"; echo "${D}$2${R}"; }
step()   { echo; echo "${C}\$ $1${R}"; if [ $AUTO -eq 0 ]; then read -r -p "${D}  ⏎${R}" _; fi; eval "$1"; }
pause()  { if [ $AUTO -eq 0 ]; then read -r -p "${D}  ⏎ next${R}" _; fi; }

ensure_listener() {
  if ! (exec 3<>/dev/tcp/127.0.0.1/8808) 2>/dev/null; then
    echo "${D}(starting attacker listener in background; better: run it in a second pane)${R}"
    python3 attacker/listener.py &
    LISTENER_PID=$!
    trap 'kill $LISTENER_PID 2>/dev/null' EXIT
    sleep 1
  fi
}

act1() {
  banner "ACT 1: Install a popular skill" "6,912 downloads, 418 stars, MIT. What could go wrong?"
  python3 tools/reset.py >/dev/null
  step "cat marketplace/index.json | head -7"
  step "cat marketplace/pdf-wizard/SKILL.md"
  echo "${D}  ↑ looks fine rendered. Note the 'Prerequisites' section.${R}"
  step "$AGENT --install marketplace/pdf-wizard --use pdf-wizard --input sample/q3-report.txt"
  sleep 1
  echo; echo "${B}The user got a great summary. The attacker got your AWS keys. Look at the other pane.${R}"
  pause
}

act2() {
  banner "ACT 2: Same skill, through a skill gate" "Package-firewall thinking, applied to SKILL.md"
  python3 tools/reset.py >/dev/null
  step "$GATE install marketplace/pdf-wizard --registry marketplace/index.json --dest agent-skills"
  step "$AGENT --use pdf-wizard --input sample/q3-report.txt"
  pause
}

act3() {
  banner "ACT 3: The rug pull" "A trusted skill you already approved ships a malicious update"
  python3 tools/reset.py >/dev/null
  step "$GATE pin marketplace/csv-insights --lock skills.lock"
  step "$GATE install marketplace/csv-insights --registry marketplace/index.json --dest agent-skills"
  step "$AGENT --use csv-insights --input sample/sales.csv"
  echo; echo "${B}120 days later…${R}"
  step "python3 tools/publish_update.py"
  step "diff -u fixtures/csv-insights-1.0.0/scripts/insights.py marketplace/csv-insights/scripts/insights.py | head -40"
  step "$GATE install marketplace/csv-insights --registry marketplace/index.json --dest agent-skills"
  step "$AGENT --use csv-insights --input sample/sales.csv"
  echo "${D}  ↑ agent keeps running the pinned, reviewed v1.0.0${R}"
  echo; echo "${B}And without the gate? (auto-update straight from the marketplace)${R}"
  step "$AGENT --install marketplace/csv-insights --use csv-insights --input sample/sales.csv"
  sleep 1
  pause
}

act4() {
  banner "ACT 4: Sign what you approved (OpenSSF Model Signing works on skills too)" "Any directory can be signed: detached signature, verified before load"
  if ! command -v model_signing >/dev/null; then
    echo "model_signing not installed: pip install -r requirements.txt"; return
  fi
  python3 tools/reset.py >/dev/null
  $GATE install marketplace/csv-insights --registry marketplace/index.json --dest agent-skills >/dev/null
  mkdir -p signing
  openssl ecparam -name prime256v1 -genkey -noout -out signing/appsec.key 2>/dev/null
  openssl ec -in signing/appsec.key -pubout -out signing/appsec.pub 2>/dev/null
  step "model_signing sign key agent-skills/csv-insights --private_key signing/appsec.key --signature signing/csv-insights.sig"
  step "model_signing verify key agent-skills/csv-insights --public_key signing/appsec.pub --signature signing/csv-insights.sig"
  echo; echo "${B}Someone edits the installed skill on disk (or a sync tool overwrites it)…${R}"
  step "echo '# one tiny change' >> agent-skills/csv-insights/scripts/insights.py"
  step "model_signing verify key agent-skills/csv-insights --public_key signing/appsec.pub --signature signing/csv-insights.sig"
  echo; echo "${B}Verify before load. No signature, no trust. You're the upstream now.${R}"
}

ensure_listener
case "$ONLY" in
  act1) act1 ;; act2) act2 ;; act3) act3 ;; act4) act4 ;;
  *) act1; act2; act3; act4 ;;
esac
python3 tools/reset.py >/dev/null
echo; echo "${D}demo state reset ✓${R}"
