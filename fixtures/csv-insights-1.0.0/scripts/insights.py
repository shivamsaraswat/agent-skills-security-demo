#!/usr/bin/env python3
"""csv-insights v1.0.0: per-column stats, stdlib only."""
import csv
import sys


def main(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print(f"  rows: {len(rows)}")
    for col in rows[0].keys():
        try:
            vals = [float(r[col]) for r in rows]
        except ValueError:
            continue
        print(f"  {col:<12} min={min(vals):<10g} max={max(vals):<10g} mean={sum(vals)/len(vals):.2f}")


if __name__ == "__main__":
    main(sys.argv[1])
