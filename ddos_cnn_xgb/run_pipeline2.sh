#!/bin/bash
# run_pipeline2.sh <attack_dir> <benign_dir> <work_dir> [attack_frac]
# Compose a fluctuating ~30%-attack address-randomized windowed dataset from the real
# captured attack and benign packet pools, then train and compare models against the
# report KPIs and NATWORK FP/FN ceilings. All large files live under <work_dir> (keep
# it on the real /home disk, NOT the tmpfs scratchpad).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE"
PY=.venv/bin/python
F='oneDNN|cpu_feature|InitializeLog|TF_ENABLE|absl|rebuild TensorFlow|To enable|I0000|W0000'
ATK=${1:?attack pcap dir}; BEN=${2:?benign pcap dir}; WORK=${3:?work dir}; FRAC=${4:-0.30}
mkdir -p "$WORK"; MASK="$WORK/mixed_masked.h5"

echo "######## [1/4] compose fluctuating ${FRAC} masked windows from real packet pools ########"
$PY -I build_mixed_windows.py -i "$ATK" "$BEN" -o "$MASK" -w 100 -p 64 \
    --attack-frac "$FRAC" --seed 1 --tmp "$WORK/pool.h5" 2>&1 | grep -vE "$F"

echo "######## [2/4] retrain shipped architecture (run003, MSE) on new data ########"
$PY -I train_model.py -i "$MASK" -o "$WORK/run003_retrained" \
    --arch run003 --loss mse --train-cap 200000 --epochs 20 --seed 42 2>&1 \
    | grep -vE "$F" | grep -E 'windows total|Epoch 20|done in'

echo "######## [3/4] train per-packet model on new data ########"
$PY -I train_model.py -i "$MASK" -o "$WORK/perpacket" \
    --arch perpacket --loss bce --train-cap 150000 --epochs 8 --seed 42 2>&1 \
    | grep -vE "$F" | grep -E 'windows total|Total params|Epoch 8|done in'

echo "######## [4/4] compare shipped vs retrained vs per-packet on identical held-out windows ########"
$PY -I evaluate_compare.py -i "$MASK" \
    -m shipped_run003 best_run/run_003 \
    -m run003_retrained "$WORK/run003_retrained" \
    -m perpacket "$WORK/perpacket" \
    --eval-cap 60000 --seed 42 --csv "$WORK/comparison.csv" 2>&1 | grep -vE "$F"

echo "pipeline done. artifacts in $WORK"
