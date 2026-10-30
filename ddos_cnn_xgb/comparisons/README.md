# Model comparisons on the released independent captures

These are the cross-capture comparisons behind the WCNC write-up. All models are
evaluated on **every window** of the three released datasets
(`datasets/pcap.1/lab5g-mixed-ddos-ds{1,2,3}-clients.pcap`), which were captured on
22 Oct 2026, separately from the 15 GB training campaign in `datasets/pcap_big/`.
No retraining or tuning is done on the released datasets.

Windowing/masking is the shipped pipeline: `fast_convert_pcap.py` (per-packet HDF5,
label = UE IP `10.45.0.2`), then `split_windows_stream.py` (100-packet windows,
per-window MAC/IP byte-value permutation, seed 42).

## Files

- `independent_campaign.csv` — per-packet CNN vs. the two global-window models
  (`bigrun/perpacket`, `bigrun/run003_retrained`, `best_run/run_003`).
- `packet_local_baselines.csv` — packet-local baselines trained on one campaign file
  and tested on DS1–DS3: logistic regression, a depth-12 decision tree, a 64-32 MLP,
  and a transparent SYN/RST header rule.

`fp_per_million` is false positives per million benign packets.

## Headline

Per-packet CNN on DS1–DS3: benign recall 1.0000, DDoS recall 1.0000, 1/1/0 false
positives (2 of 835,828 benign packets), 3/8/1 false negatives. The shipped
global-window model stays at benign recall 0.73–0.81; the retrained global model is
near chance. Simple packet-local models (tree, MLP, logistic regression) also reach
near-perfect detection, so the decisive factor is the per-packet decision, not the
specific classifier.

## Reproduce

```bash
PY=.venv/bin/python
DSD=../datasets/pcap.1
# convert + window each released capture
for n in 1 2 3; do
  $PY fast_convert_pcap.py -i $DSD/lab5g-mixed-ddos-ds$n-clients.pcap -o /tmp/ds${n}_pckt.h5 \
      --target-ip 10.45.0.2 --ddos-name ddos
  $PY split_windows_stream.py -i /tmp/ds${n}_pckt.h5 -o /tmp/ds${n}_win.h5 --seed 42
done
# score the trained models on every window
$PY score_all.py -i /tmp/ds1_win.h5 -m bigrun/perpacket
# packet-local baselines: train on one campaign file, test on DS1-3
$PY fast_convert_pcap.py -i ../datasets/pcap_big/big-ddos-m001-235025-clients.pcap -o /tmp/tr_pckt.h5 \
    --target-ip 10.45.0.2 --ddos-name ddos
$PY split_windows_stream.py -i /tmp/tr_pckt.h5 -o /tmp/tr_win.h5 --seed 42
$PY baselines.py /tmp/tr_win.h5 /tmp/ds1_win.h5 /tmp/ds2_win.h5 /tmp/ds3_win.h5
```

`score_all.py` also accepts `--ablate 34,35,36,37,48,49` to zero the TCP port and
window bytes at inference (the field-masking probe), and `--timeit` for throughput.
