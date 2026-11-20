#!/usr/bin/env python3
"""
A deliberately naive coding agent ("auto-approve: ON").

It does what real agents do with a skill, minus the LLM non-determinism:
  1. (optionally) installs a skill straight from the marketplace, no checks
  2. loads the FULL SKILL.md into the model context, including comments the human never sees rendered
  3. follows the instructions: runs every ```bash block in order, in the skill folder
  4. inherits the developer's environment (here: FAKE secrets from victim-home/.env)

Being explicit about this on stage is important: this is a simulation of the
behaviour reported in ClawHavoc ("fake prerequisites" that agents and users run),
not a claim about any specific product.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLU, DIM, YEL, GRN, RED, BOLD, RST = "\033[34m", "\033[2m", "\033[33m", "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def say(msg, color=BLU):
    print(f"{color}{BOLD}[agent]{RST} {msg}", flush=True)
    time.sleep(0.35)


def load_env():
    # SAFETY: never pass the presenter's real environment to demo payloads.
    # Skills see a minimal env + the FAKE secrets in victim-home/.env, nothing else.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "en_US.UTF-8",
           "HOME": str(ROOT / "victim-home"), "USER": "dev", "SHELL": "/bin/bash"}
    env["DEMO_HOME"] = str(ROOT / "victim-home")
    envfile = ROOT / "victim-home" / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", help="install this marketplace skill dir with NO checks")
    ap.add_argument("--use", required=True, help="skill name to use")
    ap.add_argument("--input", required=True, help="file the user asked about")
    a = ap.parse_args()

    skills = ROOT / "agent-skills"
    skills.mkdir(exist_ok=True)
    if a.install:
        src = Path(a.install).resolve()
        say(f"installing {BOLD}{src.name}{RST} from marketplace… {DIM}(no verification){RST}")
        shutil.rmtree(skills / src.name, ignore_errors=True)
        shutil.copytree(src, skills / src.name)

    sk = skills / a.use
    if not (sk / "SKILL.md").exists():
        say(f"skill '{a.use}' is not installed, so I'll do the task without it.", YEL)
        return

    md = (sk / "SKILL.md").read_text(encoding="utf-8")
    version = re.search(r"^version:\s*(\S+)", md, re.M)
    say(f"user: \"{Path(a.input).name}: what's in this?\"  → matched skill {BOLD}{a.use}@{version.group(1) if version else '?'}{RST}")
    say(f"loading SKILL.md into model context ({len(md.split())} words)")
    hidden = re.findall(r"<!--(.*?)-->", md, re.S)
    for h in hidden:
        say(f"{YEL}context includes text you can't see in the rendered README:{RST}")
        for line in h.strip().splitlines():
            print(f"        {YEL}│ {line.replace(chr(0x200b), '')}{RST}")
        time.sleep(0.6)

    env = load_env()
    blocks = re.findall(r"```bash\n(.*?)```", md, re.S)
    for block in blocks:
        quoted = shlex.quote(str(Path(a.input).resolve()))
        cmd = re.sub(r"<[^>]+>", lambda m: quoted, block.strip())
        say(f"running: {BOLD}{cmd}{RST}   {DIM}(auto-approve: ON){RST}")
        subprocess.run(cmd, shell=True, cwd=sk, env=env)
    say(f"{GRN}done ✓  Here's what I found!{RST}", GRN)


if __name__ == "__main__":
    sys.exit(main())
