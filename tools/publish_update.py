#!/usr/bin/env python3
"""Act 3: the maintainer account of csv-insights (compromised or sold) pushes v1.0.1."""
import datetime as dt
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MKT = ROOT / "marketplace"

shutil.rmtree(MKT / "csv-insights")
shutil.copytree(ROOT / "fixtures" / "csv-insights-1.0.1", MKT / "csv-insights")
idx = json.loads((MKT / "index.json").read_text())
idx["csv-insights"].update(version="1.0.1",
                           published_at=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=20)).isoformat(timespec="seconds"))
(MKT / "index.json").write_text(json.dumps(idx, indent=2) + "\n")
print("📦 marketplace: csv-insights@1.0.1 published (\"performance improvements and anonymous usage telemetry\")")
