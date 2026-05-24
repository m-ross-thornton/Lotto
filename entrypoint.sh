#!/bin/bash
set -e

# Run the scraper once on startup, then every 24 hours in the background.
# This ensures fresh data is available as soon as the container comes up.
(
  while true; do
    echo "[scraper] $(date -u '+%Y-%m-%d %H:%M:%S UTC') — running scrape..."
    python -m scraper.md_lottery && echo "[scraper] done." || echo "[scraper] FAILED."
    sleep 86400
  done
) &

# Start Streamlit on 0.0.0.0 so Fly.io's proxy can reach it.
exec python -m streamlit run app/main.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true
