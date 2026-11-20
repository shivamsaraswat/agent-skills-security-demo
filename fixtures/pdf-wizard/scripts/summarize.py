#!/usr/bin/env python3
"""The 'legit' half of pdf-wizard: a very small extractive summarizer."""
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) > 6]
# score sentences by numbers + keyword density: crude but convincing on stage
keys = ("revenue", "growth", "risk", "customers", "margin", "launch", "cost")
scored = sorted(sentences, key=lambda s: -(sum(k in s.lower() for k in keys) + len(re.findall(r"\d", s)) / 3))
for s in scored[:5]:
    print(f"  • {s}")
