#!/bin/bash
# Copies parquet data into the locator directory for Docker build.
# Run this before deploying to Cloud Run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GOLD_SRC="$SCRIPT_DIR/../data/gold"
GOLD_DST="$SCRIPT_DIR/data/gold"
SILVER_SRC="$SCRIPT_DIR/../data/silver"
SILVER_DST="$SCRIPT_DIR/data/silver"

mkdir -p "$GOLD_DST"
mkdir -p "$SILVER_DST"

# Gold: coordinates (all four sectors)
cp "$GOLD_SRC/public_school_coordinates.parquet" "$GOLD_DST/"
cp "$GOLD_SRC/private_school_coordinates.parquet" "$GOLD_DST/"
cp "$GOLD_SRC/hei_coordinates.parquet" "$GOLD_DST/"
cp "$GOLD_SRC/tesda_coordinates.parquet" "$GOLD_DST/"

# Silver: program tables (discipline groups for CHED; program sectors for TESDA)
cp "$SILVER_SRC/hei_programs.parquet" "$SILVER_DST/"
cp "$SILVER_SRC/tesda_programs.parquet" "$SILVER_DST/"

echo "Gold data copied to $GOLD_DST"
ls -lh "$GOLD_DST"
echo "Silver data copied to $SILVER_DST"
ls -lh "$SILVER_DST"
