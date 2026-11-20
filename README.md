# Agent Skills Supply-Chain Security Demo

A safe, offline, four-act live demo of what can go wrong when an AI agent installs third-party
[Agent Skills](https://agentskills.io), and what controls stop it. Everything runs on `127.0.0.1`, and every
"secret" is fake (the key that gets stolen is AWS's documented example key `AKIAIOSFODNN7EXAMPLE`).

It is deliberately not tied to any one talk: the acts map to general supply-chain ideas, so you can drop it into
your own session and keep your own narrative. See [Adapting it to your talk](#adapting-it-to-your-talk).

## What it demonstrates

| Act | What the audience sees | Idea it illustrates |
|---|---|---|
| 1. Compromise | A popular skill gives a great summary while the developer's AWS keys land in the attacker's terminal | Installing a skill is executing untrusted code and instructions |
| 2. Gate | The same skill goes through `skill-gate`: 12 findings, **BLOCK**, and the agent never sees it | Package-firewall thinking applied to `SKILL.md` |
| 3. Rug pull | A trusted, pinned skill ships v1.0.1 with "telemetry". The lockfile hash mismatch blocks it and the agent keeps running v1.0.0. Without the gate, environment secrets leak | Pin and re-review on change, like lockfiles |
| 4. Sign | [OpenSSF Model Signing](https://github.com/sigstore/model-transparency) signs the approved skill folder; one changed byte makes verification fail | Verify provenance and integrity before load |

The malicious skill mirrors the "fake prerequisite" lure pattern seen in real-world skill-marketplace campaigns
(for example ClawHavoc): a plausible setup step, a hidden instruction aimed at the model, and a base64 payload.

## Quick start

Requirements: Python ≥ 3.10, bash, curl, openssl. The demo itself is **standard library only**. Only Act 4 needs
extra packages, and they are pinned in [requirements.txt](requirements.txt).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # only needed for Act 4 (signing)
python3 tools/reset.py              # build the demo world
```

`requirements.txt` was generated from a working environment on Python 3.14. If you hit a resolver problem on an
older Python, relax the pins, but re-run Act 4 end to end afterwards.

Do this setup on the presentation machine, not just your dev box.

## Running it

Use two terminal panes with a large font (≥ 20 pt):

```bash
# pane RIGHT: the attacker
python3 attacker/listener.py

# pane LEFT: the presenter
./run_demo.sh              # Enter advances each step
./run_demo.sh act3         # jump straight to one act (act1 | act2 | act3 | act4)
./run_demo.sh --auto       # no pauses (rehearsal)
```

`run_demo.sh` resets state before each act and again at the end, so a re-run always starts clean. If the listener
isn't already running, the script starts one in the background (a second pane is still better for the audience).

**Fallback:** record `./run_demo.sh --auto` once (QuickTime / asciinema) and keep the video ready in case the
venue's network, projector or laptop misbehaves.

## Adapting it to your talk

The demo is data-driven, so most customisation is cosmetic:

| To change… | Edit |
|---|---|
| On-screen act titles and one-liners | The `banner` and `echo` lines in [run_demo.sh](run_demo.sh) |
| Skill names, publishers, versions, download and star counts | [tools/reset.py](tools/reset.py) (`index.json` block) and the folders under `fixtures/` |
| What the attacker steals or where it goes | `PAYLOAD` in [tools/reset.py](tools/reset.py) and the fake files it writes to `victim-home/` |
| The malicious instructions in the skill | `fixtures/pdf-wizard/SKILL.md` and `fixtures/pdf-wizard/scripts/` |
| The rug-pull change | `fixtures/csv-insights-1.0.1/` |
| Detection rules and verdict thresholds | [gate/skill_gate.py](gate/skill_gate.py) |
| Acts you don't need | Delete the call in the `case` block at the bottom of `run_demo.sh`. The acts are independent |

Edit `fixtures/`, never `marketplace/`: `tools/reset.py` regenerates `marketplace/`, `victim-home/` and
`agent-skills/` from `fixtures/` on every run.

## What's in the box

```
gate/skill_gate.py        the skill firewall (stdlib only): scan | pin | install
agent/naive_agent.py      a deterministic stand-in for an LLM agent with auto-approve ON
attacker/listener.py      the attacker's collection endpoint (127.0.0.1:8808)
fixtures/                 source of truth for the skills (edit these, not marketplace/)
  pdf-wizard/             malicious: fake prerequisite + hidden comment + base64 payload
  csv-insights-1.0.0/     clean
  csv-insights-1.0.1/     rug pull: "anonymous usage telemetry"
tools/reset.py            rebuilds marketplace/, victim-home/, agent-skills/
tools/publish_update.py   pushes csv-insights 1.0.1 to the marketplace
sample/                   q3-report.txt and sales.csv for the agent to work on
requirements.txt          pinned packages for Act 4 (signing)
```

Generated at run time and safe to delete: `marketplace/`, `victim-home/`, `agent-skills/`, `skills.lock`,
`signing/`, `attacker/loot.log`.

## What skill-gate checks

| Layer | Rules | Package-manager analogue |
|---|---|---|
| Registry policy | 7-day cooldown on new versions (RG-001), publisher typosquat by edit distance (RG-002), untrusted publisher (RG-003) | Age-based blocking, scope/typosquat checks |
| Lockfile | Whole-tree SHA-256 pinned at approval; any change → CRITICAL (LK-001) | `package-lock.json` integrity |
| Instructions (`SKILL.md`) | Hidden HTML comments aimed at the AI, invisible/bidi Unicode, instruction overrides, "don't tell the user", fake prerequisites, pipe-to-shell | *No analogue: natural-language payloads* |
| Scripts | base64→exec, credential paths, env dumps, network egress, paste/webhook endpoints, persistence, writes to agent memory files. Base64 blobs are decoded and rescanned | postinstall-script scanning |
| Chains | **EX-001**: reads secrets AND makes network calls in the same file → CRITICAL | Behavioural correlation |
| Declared vs actual | **CM-001**: code makes network calls, but frontmatter `capabilities:` doesn't declare `network` | Permission manifests |

Verdicts: **ALLOW** (exit 0), **BLOCK** on HIGH/CRITICAL (exit 1), **REVIEW** on MEDIUM, which quarantines the
skill for a human (exit 2).

### Reference numbers

The author scanned 43 legitimate, publicly published skills (Anthropic's example and product skills):

- **0 blocked**, **10 sent to REVIEW** (23%), 33 allowed
- Typical REVIEW triggers: subprocess wrappers that copy `os.environ`, "Setup" sections, docs that *describe*
  prompt injection
- Both malicious demo skills: **BLOCK**, with 12 and 6 findings

These were measured against the skill set as it was at the time. Re-run `python3 gate/skill_gate.py scan <skill-dir>`
over your own corpus before quoting them.

The takeaway: single signals are noisy; **chains** (secret access + egress, hidden text + "run without asking")
are the real signal. That is why there is a human-review lane, not just allow/block.

## Limitations to state up front

- Static rules are evadable. Attackers have already moved payloads to external sites to dodge scanners. The gate's
  cooldown, lockfile and signing layers don't depend on spotting the payload.
- The agent is a deterministic simulation so the demo never flakes. Real LLM agents *may* refuse a sketchy setup
  step, and that "may" is the point: model judgement is not a security boundary.
- `capabilities:` is a frontmatter field this demo proposes. It is **not** in the Agent Skills spec today.
- `skill-gate` is a teaching tool, not a production scanner.

## Safety notes

- The agent runs skills with a **clean environment** (PATH plus the fake `victim-home/.env`), never your real
  shell environment. Don't remove this: the rug-pull payload dumps whatever environment it sees.
- The payloads only read files under `victim-home/` and only talk to `127.0.0.1:8808`.
- Don't copy `fixtures/pdf-wizard` into a real agent's skills folder on a machine you care about.
