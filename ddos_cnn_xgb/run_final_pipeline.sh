#!/bin/bash
# run_final_pipeline.sh <pcap_dir> <work_dir>
# Pool all captured packets by label from <pcap_dir> and compose a fluctuating-30% (avg)
# address-randomized windowed dataset, then train run003_retrained + perpacket and compare
# against the shipped model (report KPIs + NATWORK FP/FN). Large files under <work_dir> (/home).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE"
PY=.venv/bin/python
F='oneDNN|cpu_feature|InitializeLog|TF_ENABLE|absl|rebuild TensorFlow|To enable|I0000|W0000'
PCAP=${1:?pcap dir}; WORK=${2:?work dir}; mkdir -p "$WORK"
MASK="$WORK/mixed_masked.h5"

echo "######## [1/4] pool packets by label + compose fluctuating ~30% windows ########"
$PY -I build_mixed_windows.py -i "$PCAP" -o "$MASK" -w 100 -p 64 \
    --attack-frac 0.30 --seed 1 --tmp "$WORK/pool.h5" 2>&1 | grep -vE "$F"

echo "######## [2/4] retrain shipped arch (run003, MSE) ########"
$PY -I train_model.py -i "$MASK" -o "$WORK/run003_retrained" --arch run003 --loss mse \
    --train-cap 200000 --epochs 20 --seed 42 2>&1 | grep -vE "$F" | grep -E 'windows total|Epoch 20|done in'

echo "######## [3/4] train per-packet model ########"
$PY -I train_model.py -i "$MASK" -o "$WORK/perpacket" --arch perpacket --loss bce \
    --train-cap 150000 --epochs 8 --seed 42 2>&1 | grep -vE "$F" | grep -E 'windows total|Total params|Epoch 8|done in'

echo "######## [4/4] compare shipped vs retrained vs per-packet ########"
$PY -I evaluate_compare.py -i "$MASK" \
    -m shipped_run003 best_run/run_003 \
    -m run003_retrained "$WORK/run003_retrained" \
    -m perpacket "$WORK/perpacket" \
    --eval-cap 60000 --seed 42 --csv "$WORK/comparison.csv" 2>&1 | grep -vE "$F"
echo "pipeline done. artifacts in $WORK"
