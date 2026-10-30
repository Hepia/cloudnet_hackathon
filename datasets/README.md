# 6G-DALI / NATWORK hackathon — mixed benign + Mirai DDoS datasets

This directory holds the **label rule** and the **generation scripts** that turn lab5g
traffic into labelled datasets. There are two generations, both produced by the lab in
`../infrastructure/` (which owns the testbed and the Mirai attack; see its README):

* the **original ds1–ds3** small captures, documented immediately below;
* the **15 GB fluctuating-~30 % single-pass campaign** used for the per-packet model,
  documented under *"The per-packet campaign"* at the end.

The detector that consumes these datasets is in `../ddos_cnn_xgb/`; the full end-to-end
walkthrough is in `../REPRODUCE.md`.

---

## Original ds1–ds3

Three packet captures generated in the `infrastructure/` lab5g environment, each mixing
normal application traffic with a Mirai SYN-flood DDoS attack. They are meant to be fed to
the `ddos_cnn_xgb/` detector (and any other participant model) as labelled train/test data.

All traffic was produced inside the self-contained lab (no route to the outside). Benign
traffic comes from the client containers on `10.10.2.0/24`; the attack is a Mirai SYN flood
launched from the UE (`10.45.0.2`) through the 5G user plane. Both were captured together on
the router, headers only (tcpdump snaplen 128).

## Files

`pcap/lab5g-mixed-ddos-ds{1,2,3}-clients.pcap` — the router clients-side interface, which
sees both the client network and the UE, so each file contains the complete benign + attack
mix. (The router servers-side capture is a byte-for-byte redundant view and is not shipped.)

## Label rule

A packet is **DDoS (1)** iff its source or destination IP is the UE `10.45.0.2`, otherwise
**benign (0)**. This is exact because benign traffic is only ever generated from the client
containers (`10.10.2.x`) and the attack only ever from the UE. For `ddos_cnn_xgb`:

```
python convert_pcap_to_h5.py -i datasets/pcap -o tf_dataset/mixed_pckt.h5 \
    -p 64 --target-ip 10.45.0.2 --ddos-name ddos
python split_h5_into_windows.py -i tf_dataset/mixed_pckt.h5 \
    -o tf_dataset/mixed_masked.h5 -w 100 -p 64
python classify_h5.py -i tf_dataset/mixed_masked.h5 -m best_run/run_003
```

The filenames contain `ddos`, which the converter uses together with `--target-ip` to apply
the label above.

## Composition (packets, clients-side capture)

| Dataset | Total | Attack (10.45.0.2) | Benign | Size | Attack % |
| --- | --- | --- | --- | --- | --- |
| ds1 | 499,373 | 207,220 | 292,153 | 54.9 MB | 41% |
| ds2 | 657,875 | 342,007 | 315,868 | 68.5 MB | 52% |
| ds3 | 411,267 | 183,245 | 228,022 | 44.3 MB | 45% |

Benign protocol mix per file (approximate packet counts):

| | HTTP (80) | MQTT (1883) | iperf3 UDP (5201) | RTP video (from .30) |
| --- | --- | --- | --- | --- |
| ds1 | 13,057 | 14,018 | 252,097 | 12,694 |
| ds2 | 13,884 | 14,020 | 275,014 | 12,667 |
| ds3 | 13,521 | 13,930 | 187,512 | 12,772 |

The bulk iperf3 UDP stream provides benign volume (so the dataset is not dominated by the
flood); HTTP, MQTT and RTP video provide protocol diversity. The attack portion is the Mirai
SYN flood (TCP SYN, win 0, randomized ports to `10.10.1.50`) plus the RST/SYN-ACK responses
it draws back toward the UE.

## Verification

Labelling was checked by converting ds1 and comparing against an independent `tcpdump`
count: the converter reported 292,153 benign / 207,220 DDoS, matching exactly. Running the
shipped CNN (`best_run/run_003`) over the windowed, masked ds1 gives a meaningful score on
balanced data (a pure-attack capture would trivially read 100%):

| Metric | benign | DDoS |
| --- | --- | --- |
| precision | 0.997 | 0.785 |
| recall | 0.807 | 0.996 |
| f1 | 0.892 | 0.878 |

Overall accuracy 0.885. The model catches almost every attack packet (recall 0.996) and
mislabels ~19% of benign as attack, so these datasets are useful for improving precision.

## Regeneration

With the lab up (`cd infrastructure && ./lab.sh up`), from `datasets/`:

```
./generate_dataset.sh ds1 2 110M 22     # ~55 MB, 41% attack
./generate_dataset.sh ds2 3 120M 22     # ~68 MB, 52% attack
./generate_dataset.sh ds3 2  90M 20     # ~44 MB, 45% attack
```

Arguments: `<label> <flood_seconds> <iperf_mbit> <window_seconds>`. The flood runs at the
bot's full rate (~60k SYN/s as seen at the router), so flood seconds is the main attack-volume
knob; iperf bitrate and window are the benign-volume knobs.

---

## The per-packet campaign (15 GB, fluctuating ~30 % attack)

The per-packet detector is trained on a larger, more realistic generation: benign and
the Mirai flood run **concurrently** and are captured in a single pass, with the attack
share **fluctuating** across chunks (benign-only ≈ 0 %, normal ≈ 30 %, flood-heavy
≈ 55 %) but **averaging ~30 %**. The same label rule above applies unchanged (DDoS iff
the packet touches the UE `10.45.0.2`). Output lands in `datasets/pcap_big/` (snaplen
128); it is **not committed** (~15 GB) and is regenerated with these scripts.

Run from `infrastructure/` with the lab up and the Mirai bot connected (see
`../infrastructure/README.md`):

| Script | What it captures |
| --- | --- |
| `generate_final.sh <prefix> <GB> <chunk_s>` | single-pass concurrent capture; attack share follows a built-in fluctuation pattern, averaging ~30 % |
| `generate_m.sh <GB> <chunk_s>` | the stable "normal" chunk only, with automatic lab reset on a wedge — simplest and most robust |
| `generate_robust.sh`, `generate_fluct.sh`, `generate_big_dataset.sh` | other benign/attack mixes |
| `capture_attack.sh` / `capture_benign.sh` | capture each class **separately** (most reliable); compose any attack fraction afterwards with `ddos_cnn_xgb/build_mixed_windows.py` |
| `generate_dataset.sh` | the original ds1–ds3 generator (above) |

```bash
cd infrastructure
../datasets/generate_final.sh big 15 60     # ~15 GB into datasets/pcap_big/
```

Composing the captured packets into the windowed, address-randomised training set
(`mixed_masked.h5`) and training/evaluating the models is driven by
`../ddos_cnn_xgb/run_final_pipeline.sh` — see `../REPRODUCE.md`.
