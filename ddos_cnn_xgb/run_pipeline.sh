#!/bin/bash
# run_pipeline.sh  — end-to-end: big pcap set -> labelled h5 -> address-randomized
# windows -> train models -> compare against the report KPIs and NATWORK FP/FN.
#
# Trains two models on the new in-distribution data:
#   * run003_retrained : the EXACT shipped architecture + repo recipe (MSE), to show
#                        what retraining the current model alone achieves.
#   * perpacket        : the per-packet head (same I/O contract), the model that
#                        meets the NATWORK FP<1% / FN<1% ceilings on concurrent data.
# Then compares shipped run_003 vs both on identical held-out windows.
#
# Usage: run_pipeline.sh <pcap_dir> <work_dir>
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"
PY=.venv/bin/python
F='oneDNN|cpu_feature|InitializeLog|TF_ENABLE|absl|rebuild TensorFlow|To enable|I0000|W0000'

PCAP_DIR=${1:?pcap dir}
WORK=${2:?work dir}
mkdir -p "$WORK"
PKT_H5="$WORK/big_pckt.h5"
MASK_H5="$WORK/big_masked.h5"

echo "######## [1/5] convert pcaps -> labelled per-packet h5 ########"
$PY -I fast_convert_pcap.py -i "$PCAP_DIR" -o "$PKT_H5" \
    --target-ip 10.45.0.2 --ddos-name ddos 2>&1 | grep -vE "$F"

echo "######## [2/5] window + randomize addresses -> masked h5 ########"
$PY -I split_windows_stream.py -i "$PKT_H5" -o "$MASK_H5" -w 100 -p 64 --seed 1 2>&1 | grep -vE "$F" | tail -1
rm -f "$PKT_H5"

echo "######## [3/5] retrain shipped architecture (run003, MSE) on new data ########"
$PY -I train_model.py -i "$MASK_H5" -o "$WORK/run003_retrained" \
    --arch run003 --loss mse --train-cap 200000 --epochs 20 --seed 42 2>&1 \
    | grep -vE "$F" | grep -E 'windows total|Epoch 20|done in'

echo "######## [4/5] train per-packet model on new data ########"
$PY -I train_model.py -i "$MASK_H5" -o "$WORK/perpacket" \
    --arch perpacket --loss bce --train-cap 150000 --epochs 8 --seed 42 2>&1 \
    | grep -vE "$F" | grep -E 'windows total|Total params|Epoch 8|done in'

echo "######## [5/5] compare on identical held-out windows ########"
$PY -I evaluate_compare.py -i "$MASK_H5" \
    -m shipped_run003 best_run/run_003 \
    -m run003_retrained "$WORK/run003_retrained" \
    -m perpacket "$WORK/perpacket" \
    --eval-cap 60000 --seed 42 --csv "$WORK/comparison.csv" 2>&1 | grep -vE "$F"

echo "pipeline done. artifacts in $WORK"
