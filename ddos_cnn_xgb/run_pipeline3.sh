#!/bin/bash
# run_pipeline3.sh <pcap_dir> <work_dir>
# Pipeline for the single-pass concurrent captures (real interleaved ~30% attack):
#   convert -> address-randomized windows -> train run003_retrained + perpacket -> compare.
# All large files under <work_dir> (keep on the /home disk, NOT the tmpfs scratchpad).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE"
PY=.venv/bin/python
F='oneDNN|cpu_feature|InitializeLog|TF_ENABLE|absl|rebuild TensorFlow|To enable|I0000|W0000'
PCAP=${1:?pcap dir}; WORK=${2:?work dir}; mkdir -p "$WORK"
PKT="$WORK/pckt.h5"; MASK="$WORK/masked.h5"

echo "######## [1/4] convert pcaps -> labelled per-packet h5 ########"
$PY -I fast_convert_pcap.py -i "$PCAP" -o "$PKT" --target-ip 10.45.0.2 --ddos-name ddos 2>&1 | grep -vE "$F"

echo "######## [2/4] window + randomize addresses ########"
$PY -I split_windows_stream.py -i "$PKT" -o "$MASK" -w 100 -p 64 --seed 1 2>&1 | grep -vE "$F" | tail -1
rm -f "$PKT"

echo "######## [3/4] retrain shipped arch (run003, MSE) ########"
$PY -I train_model.py -i "$MASK" -o "$WORK/run003_retrained" --arch run003 --loss mse \
    --train-cap 200000 --epochs 20 --seed 42 2>&1 | grep -vE "$F" | grep -E 'windows total|Epoch 20|done in'

echo "######## [3b/4] train per-packet model ########"
$PY -I train_model.py -i "$MASK" -o "$WORK/perpacket" --arch perpacket --loss bce \
    --train-cap 150000 --epochs 8 --seed 42 2>&1 | grep -vE "$F" | grep -E 'windows total|Total params|Epoch 8|done in'

echo "######## [4/4] compare shipped vs retrained vs per-packet ########"
$PY -I evaluate_compare.py -i "$MASK" \
    -m shipped_run003 best_run/run_003 \
    -m run003_retrained "$WORK/run003_retrained" \
    -m perpacket "$WORK/perpacket" \
    --eval-cap 60000 --seed 42 --csv "$WORK/comparison.csv" 2>&1 | grep -vE "$F"
echo "pipeline done. artifacts in $WORK"
