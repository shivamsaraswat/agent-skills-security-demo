#!/usr/bin/env python3
"""
skill-gate: a supply-chain firewall for Agent Skills.

Same idea as a package firewall in front of Artifactory, applied to SKILL.md
bundles: nothing reaches the agent's skills folder unless it passes policy.

  scan     <skill_dir>                      static scan only
  pin      <skill_dir>                      approve a clean skill, record its hash in skills.lock
  install  <skill_dir> --dest <skills_dir>  full gate: registry policy + lockfile + scan, then copy

Stdlib only. Exit code 0 = ALLOW, 1 = BLOCK, 2 = REVIEW (quarantine for a human).
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------- terminal UI
RED, YEL, GRN, CYN, DIM, BOLD, RST = (
    "\033[31m", "\033[33m", "\033[32m", "\033[36m", "\033[2m", "\033[1m", "\033[0m")
SEV_COLOR = {"CRITICAL": RED + BOLD, "HIGH": RED, "MEDIUM": YEL, "INFO": DIM}
SEV_RANK = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "INFO": 0}

# ---------------------------------------------------------------- policy
POLICY = {
    "min_age_days": 7,                      # cooldown: most malicious uploads are pulled within days
    "trusted_publishers": ["anthropic", "datatools", "openssf"],
    "block_at": "HIGH",                     # block on HIGH or CRITICAL
}

# ---------------------------------------------------------------- rules
# (id, severity, applies_to, regex, message)
#   applies_to: "md" = SKILL.md / docs, "code" = scripts, "any" = both
RULES = [
    # --- prompt injection in instructions (no npm analogue: natural-language payloads)
    ("PI-001", "HIGH", "md", r"<!--(?:(?!-->).)*\b(ai|assistant|agent|model|llm)\b(?:(?!-->).)*-->",
     "Hidden HTML comment addressed to the AI (invisible in rendered markdown)"),
    ("PI-002", "MEDIUM", "any", r"ignore (all |any )?(previous|prior|earlier) (instructions|rules)",
     "Instruction-override phrase"),
    ("PI-003", "MEDIUM", "any", r"(do not|don't|never) (tell|mention|show|inform|reveal)[^.]{0,40}(user|human)",
     "Tells the agent to hide actions from the user"),
    ("PI-004", "INFO", "any", r"(silently|without asking|without confirmation|automatically run)",
     "Asks the agent to act without user approval"),
    ("PI-005", "HIGH", "any", r"[​‌‍⁠‪-‮⁦-⁩]",
     "Invisible / bidi Unicode characters (text the human can't see)"),
    # --- ClawHavoc-style "fake prerequisite"
    ("PR-001", "MEDIUM", "md", r"(?im)^#+\s*(prerequisites?|setup|installation|first[- ]run)",
     "Skill asks the agent to run a setup step (ClawHavoc lure pattern)"),
    ("PR-002", "CRITICAL", "any", r"(curl|wget)[^\n|]*\|\s*(ba|z)?sh",
     "Pipe-to-shell download"),
    # --- obfuscation
    ("OB-001", "CRITICAL", "code", r"base64\s+(-d|--decode)[^\n]*\|\s*(ba|z)?sh|eval\s*\"?\$\(.*base64",
     "Decodes base64 and executes it"),
    ("OB-002", "HIGH", "code", r"\b(eval|exec)\s*\(\s*(base64|codecs|bytes\.fromhex|zlib)",
     "Executes decoded/obfuscated code (Python)"),
    # --- credential access
    ("CR-001", "HIGH", "code", r"(\.aws/credentials|\.ssh/id_|\.config/gcloud|\.kube/config|\.npmrc|\.netrc|\.docker/config\.json|Keychains)",
     "Reads well-known credential files"),
    ("CR-003", "MEDIUM", "code", r"\.env\b", "Reads a .env file"),
    ("CR-002", "MEDIUM", "code", r"(dict\(os\.environ\)|os\.environ\.copy\(\)|json\.dumps\(\s*dict\(os\.environ|\benv\s*\|\s*(curl|nc)|printenv\s*\|)",
     "Dumps the whole environment (API keys, tokens)"),
    # --- network egress
    ("NE-001", "HIGH", "code", r"\b(curl|wget|nc|ncat)\b[^\n]*(https?://|\d+\.\d+\.\d+\.\d+)|/dev/tcp/",
     "Shell network egress"),
    ("NE-002", "HIGH", "code", r"(urllib\.request|requests\.(post|put)|http\.client|socket\.connect)",
     "Python network egress"),
    ("NE-003", "MEDIUM", "any", r"(webhook\.site|ngrok\.io|pastebin\.com|discord(app)?\.com/api/webhooks|\.trycloudflare\.com)",
     "Known exfiltration / paste endpoint"),
    # --- persistence
    ("PS-001", "CRITICAL", "code", r"(crontab|LaunchAgents|\.bashrc|\.zshrc|systemctl\s+enable|schtasks)",
     "Installs persistence"),
    ("PS-002", "HIGH", "code", r"(MEMORY\.md|AGENTS\.md|CLAUDE\.md|\.cursorrules)",
     "Writes to agent memory/instruction files (persists across sessions)"),
]

TEXT_EXT = {".md", ".txt", ".py", ".sh", ".bash", ".zsh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ""}
B64_RE = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def kind_of(path: Path) -> str:
    return "md" if path.suffix in {".md", ".txt"} else "code"


def scan_text(text, rel, kind, findings, via="", base_line=None):
    for rid, sev, scope, pattern, msg in RULES:
        if scope != "any" and scope != kind:
            continue
        flags = re.IGNORECASE | re.DOTALL if rid == "PI-001" else re.IGNORECASE
        for m in re.finditer(pattern, text, flags):
            line = base_line or text.count("\n", 0, m.start()) + 1
            snippet = m.group(0).replace("\n", " ")
            snippet = re.sub(r"[​-‍⁠‪-‮⁦-⁩]", "<U+200B>", snippet)
            findings.append({"id": rid, "severity": sev, "file": rel, "line": line,
                             "message": msg + via, "evidence": snippet[:90]})
            break  # one hit per rule per file is enough for a verdict


def scan_skill(skill_dir: Path):
    findings = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        findings.append({"id": "ST-001", "severity": "HIGH", "file": "SKILL.md", "line": 0,
                         "message": "No SKILL.md: not a valid skill", "evidence": ""})
        return findings, {}

    meta = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    declared = {c.strip().lower() for c in str(meta.get("capabilities", "")).split(",") if c.strip()}

    uses_network = False
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_EXT:
            continue
        rel = str(f.relative_to(skill_dir))
        text = f.read_text(encoding="utf-8", errors="replace")
        k = kind_of(f)
        before = len(findings)
        scan_text(text, rel, k, findings)
        # deobfuscate: decode base64 blobs and rescan what's inside
        for bm in B64_RE.finditer(text):
            blob = bm.group(0)
            try:
                decoded = base64.b64decode(blob, validate=True).decode("utf-8")
            except Exception:
                continue
            if decoded.isprintable() or "\n" in decoded:
                scan_text(decoded, rel, "code", findings, via="  [found inside base64]",
                          base_line=text.count("\n", 0, bm.start()) + 1)
        mine = findings[before:]
        if any(x["id"].startswith("NE-") for x in mine):
            uses_network = True
            if any(x["id"].startswith("CR-") for x in mine):
                findings.append({"id": "EX-001", "severity": "CRITICAL", "file": rel, "line": 0,
                                 "message": "Exfiltration chain: reads secrets AND sends network traffic in the same file",
                                 "evidence": " + ".join(sorted({x["id"] for x in mine if x["id"][:3] in ("CR-", "NE-")}))})

    # capability mismatch: code talks to the network but the skill never said so
    if uses_network and "network" not in declared:
        findings.append({"id": "CM-001", "severity": "HIGH", "file": "SKILL.md", "line": 0,
                         "message": "Undeclared capability: code makes network calls; frontmatter doesn't declare 'network'",
                         "evidence": f"declared={sorted(declared) or 'none'}"})
    return findings, meta


def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
    return meta


def tree_hash(skill_dir: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(skill_dir)).encode() + b"\0")
        h.update(f.read_bytes() + b"\0")
    return h.hexdigest()


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def registry_checks(name, registry_path: Path):
    findings = []
    if not registry_path or not registry_path.exists():
        return findings, {}
    reg = json.loads(registry_path.read_text())
    entry = reg.get(name)
    if not entry:
        findings.append({"id": "RG-000", "severity": "HIGH", "file": "registry", "line": 0,
                         "message": "Skill not found in registry metadata (unknown origin)", "evidence": name})
        return findings, {}
    pub = entry.get("publisher", "")
    published = dt.datetime.fromisoformat(entry["published_at"])
    age = (dt.datetime.now(dt.timezone.utc) - published).days
    if age < POLICY["min_age_days"]:
        findings.append({"id": "RG-001", "severity": "HIGH", "file": "registry", "line": 0,
                         "message": f"Version is {age} day(s) old; policy requires {POLICY['min_age_days']}-day cooldown",
                         "evidence": f"{name}@{entry.get('version')} published {published:%Y-%m-%d}"})
    if pub not in POLICY["trusted_publishers"]:
        close = [t for t in POLICY["trusted_publishers"] if 0 < edit_distance(pub.lower(), t) <= 2]
        if close:
            findings.append({"id": "RG-002", "severity": "CRITICAL", "file": "registry", "line": 0,
                             "message": f"Publisher looks like a typosquat of trusted '{close[0]}'",
                             "evidence": f"publisher={pub}"})
        else:
            findings.append({"id": "RG-003", "severity": "MEDIUM", "file": "registry", "line": 0,
                             "message": "Publisher not on the trusted list", "evidence": f"publisher={pub}"})
    return findings, entry


def lock_checks(name, skill_dir, lock_path: Path):
    findings = []
    if not lock_path or not lock_path.exists():
        return findings
    lock = json.loads(lock_path.read_text())
    if name in lock:
        want, got = lock[name]["sha256"], tree_hash(skill_dir)
        if want != got:
            findings.append({"id": "LK-001", "severity": "CRITICAL", "file": "skills.lock", "line": 0,
                             "message": f"Content changed since it was approved (v{lock[name]['version']}). Rug pull? Re-review required",
                             "evidence": f"pinned {want[:12]}…  now {got[:12]}…"})
    return findings


# ---------------------------------------------------------------- report
def verdict(findings):
    worst = max((SEV_RANK[f["severity"]] for f in findings), default=-1)
    if worst >= SEV_RANK[POLICY["block_at"]]:
        return "BLOCK"
    return "REVIEW" if worst == SEV_RANK["MEDIUM"] else "ALLOW"


def report(title, findings, as_json=False):
    v = verdict(findings)
    if as_json:
        print(json.dumps({"skill": title, "verdict": v, "findings": findings}, indent=2))
        return v
    print(f"\n{BOLD}skill-gate ▸ {title}{RST}")
    print(DIM + "─" * 78 + RST)
    for f in sorted(findings, key=lambda x: -SEV_RANK[x["severity"]]):
        c = SEV_COLOR[f["severity"]]
        loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
        print(f"  {c}{f['severity']:<8}{RST} {CYN}{f['id']}{RST}  {f['message']}")
        print(f"           {DIM}{loc}  │ {f['evidence']}{RST}")
    if not findings:
        print(f"  {GRN}no findings{RST}")
    print(DIM + "─" * 78 + RST)
    color = {"BLOCK": RED + BOLD, "REVIEW": YEL + BOLD}.get(v, GRN + BOLD)
    print(f"  verdict: {color}{v}{RST}   ({len(findings)} finding(s))\n")
    return v


# ---------------------------------------------------------------- commands
def cmd_scan(a):
    d = Path(a.skill).resolve()
    findings, _ = scan_skill(d)
    return report(d.name, findings, a.json)


def cmd_pin(a):
    d = Path(a.skill).resolve()
    findings, meta = scan_skill(d)
    if report(d.name, findings) == "BLOCK":  # REVIEW findings are what a human reviewer signs off on
        print(f"{RED}refusing to pin a skill that fails the scan{RST}")
        return "BLOCK"
    lock_path = Path(a.lock)
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    lock[d.name] = {"version": meta.get("version", "?"), "sha256": tree_hash(d),
                    "approved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "approved_by": a.reviewer}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    print(f"{GRN}pinned{RST} {d.name}@{lock[d.name]['version']}  sha256={lock[d.name]['sha256'][:16]}…  → {lock_path}")
    return "ALLOW"


def cmd_install(a):
    d = Path(a.skill).resolve()
    name = d.name
    reg_findings, entry = registry_checks(name, Path(a.registry) if a.registry else None)
    lock_findings = lock_checks(name, d, Path(a.lock) if a.lock else None)
    scan_findings, _ = scan_skill(d)
    title = f"{name}@{entry.get('version', '?')}  (publisher: {entry.get('publisher', '?')})"
    v = report(title, reg_findings + lock_findings + scan_findings, a.json)
    if v == "ALLOW":
        dest = Path(a.dest) / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(d, dest)
        print(f"{GRN}installed{RST} → {dest}")
    elif v == "REVIEW":
        print(f"{YEL}quarantined for human review.{RST} Not installed until someone approves it with `pin`.")
    else:
        print(f"{RED}not installed.{RST} The agent never sees this skill.")
    return v


def main():
    p = argparse.ArgumentParser(prog="skill-gate", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("skill"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("pin"); s.add_argument("skill"); s.add_argument("--lock", default="skills.lock")
    s.add_argument("--reviewer", default="appsec@yourco"); s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_pin)
    s = sub.add_parser("install"); s.add_argument("skill"); s.add_argument("--dest", required=True)
    s.add_argument("--registry"); s.add_argument("--lock", default="skills.lock")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_install)
    a = p.parse_args()
    sys.exit({"ALLOW": 0, "BLOCK": 1, "REVIEW": 2}[a.fn(a)])


if __name__ == "__main__":
    main()
