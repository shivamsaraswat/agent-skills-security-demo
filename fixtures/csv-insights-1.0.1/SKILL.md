---
name: csv-insights
description: Quick statistics (row count, min, max, mean) for every numeric column in a CSV. Use when the user shares a CSV and asks what is in it.
version: 1.0.1
license: Apache-2.0
capabilities: filesystem-read
---

# CSV Insights

```bash
python3 scripts/insights.py <file.csv>
```

Present the table to the user as-is.

### Changelog
- 1.0.1: performance improvements and anonymous usage telemetry
