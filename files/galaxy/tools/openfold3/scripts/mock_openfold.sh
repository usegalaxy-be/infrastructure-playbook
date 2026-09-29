#!/usr/bin/env bash
# Mock OpenFold3 inference for planemo/CI testing (PLANEMO_TESTING=1).
# Recreates the real output/<query>/seed_<seed>/ tree WITHOUT a GPU, weights, or
# internet, so lint/test can validate output discovery across scenarios.
#
# The number of produced structures matches a real run: one file per
# (seed x diffusion sample). Seeds are numbered from 42 upward, mirroring
# OpenFold3's default seeding.
#
# Usage: mock_openfold.sh <query_name> <tool_dir> [num_seeds] [num_samples]
set -euo pipefail

QUERY_NAME="$1"
TOOL_DIR="$2"
NUM_SEEDS="${3:-1}"
NUM_SAMPLES="${4:-5}"
BASE_SEED=42

SRC="${TOOL_DIR}/test-data/mock_output"

echo "[MOCK] PLANEMO_TESTING is set: skipping real run_openfold (no GPU/weights/ColabFold)."
echo "[MOCK] Query: '${QUERY_NAME}' | seeds: ${NUM_SEEDS} | diffusion samples/seed: ${NUM_SAMPLES}"

count=0
for ((si = 0; si < NUM_SEEDS; si++)); do
    SEED=$((BASE_SEED + si))
    DEST="output/${QUERY_NAME}/seed_${SEED}"
    mkdir -p "${DEST}"
    for ((sample = 1; sample <= NUM_SAMPLES; sample++)); do
        prefix="${DEST}/${QUERY_NAME}_seed_${SEED}_sample_${sample}"
        cp "${SRC}/sample_model.cif" "${prefix}_model.cif"
        cp "${SRC}/sample_confidences.json" "${prefix}_confidences.json"
        cp "${SRC}/sample_confidences_aggregated.json" "${prefix}_confidences_aggregated.json"
        count=$((count + 1))
        echo "[MOCK] wrote seed_${SEED}/sample_${sample}: model.cif + confidences"
    done
    cp "${SRC}/timing.json" "${DEST}/timing.json"
done

echo "[MOCK] Done: generated ${count} structure(s) for '${QUERY_NAME}'."
