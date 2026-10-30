# Reproducing the per-packet DDoS detector & its dataset

This branch contains the **code, the generation/training pipeline, and the trained
per-packet model** for a 5G DDoS detector that meets the NATWORK KPIs
(false-positive rate < 1 %, false-negative rate < 1 %).

The raw captures (~15 GB of pcap) and the composed windowed dataset (~2.7 GB HDF5)
are **not** committed — they are too large for GitHub and are `.gitignore`d. This
guide lets you regenerate an equivalent dataset and reproduce the result end to end.

> You will not get a byte-identical dataset (live traffic is non-deterministic), but
> you will get a statistically equivalent one — real interleaved benign + Mirai DDoS,
> fluctuating per-window attack fraction averaging ~30 %, address-randomized — and a
> model that reaches the same KPIs.

---

## 0. Prerequisites

* Linux host with Docker + Docker Compose, ~20 GB free disk for captures.
* Python 3 virtualenv for the detector (TensorFlow 2.x CPU is fine):

  ```bash
  cd ddos_cnn_xgb
  python3 -m venv .venv
  .venv/bin/pip install tensorflow h5py numpy scikit-learn
  ```

  (The repo was developed against TensorFlow 2.21 CPU-only; a GPU is not required.)

---

## 1. The lab is already patched (nothing to do)

Early captures silently produced **zero attack packets** because the UERANSIM UE
uplink wedged under the flood. This branch ships the fix, baked into the gNB/UE image
build, so you don't have to do anything — `./lab.sh up` in step 2 compiles it in.

The diagnosis and the patch (the bounded-queue uplink fix, the Mirai CNC-before-bot
start order, and the removed Mirai SLA/QoS caps) are documented in
**`infrastructure/README.md` → "This hackathon: Mirai attack + the UERANSIM uplink
patch"**. Read it there if you want to know *why* capture now works.

---

## 2. Bring up the (patched) lab

```bash
cd infrastructure
./lab.sh up          # builds the patched images (first time: several minutes) and starts everything
```

`./lab.sh up` runs `docker compose up -d --build`, so the UERANSIM patch is compiled
in automatically. Wait until the UE has a PDU session and the bot has connected:

```bash
# UE should have uesimtun0 = 10.45.0.2
docker exec ue ip -brief addr show uesimtun0
# bot<->CNC established on :23 (may take up to ~90 s after a fresh 'up')
docker exec custom-client sh -c 'ss -nt | grep ":23 "'
```

> If the UE ever wedges or comes up with the wrong IP, do a **full** reset
> (`./lab.sh down && ./lab.sh up`) — an in-place `docker restart` gives the UE a new
> address and breaks routing.

---

## 3. Generate the dataset (the capture campaign)

Topology and the IP-based label rule (DDoS iff a packet touches the UE `10.45.0.2`)
are documented in **`datasets/README.md`**; the lab topology itself is in
**`infrastructure/README.md`**.

### Run the campaign
From `infrastructure/` with the patched lab up and the bot connected:

```bash
# generate_final.sh <prefix> <target_GB> <chunk_s>
../datasets/generate_final.sh big 15 60
```

This captures on the router in chunks, running the benign app mix (iperf3/UDP, HTTP,
MQTT, video) **together** with the Mirai flood. The per-chunk attack share
**fluctuates** by design — benign-only (~0 %), normal (~30 %), flood-heavy (~55 %) —
following the `PATTERN` array, and **averages ~30 %** overall. Files land in
`datasets/pcap_big/` (captured at snaplen 128). Each chunk prints its size and
measured attack %.

Alternative generators (all in `datasets/`):
* `generate_m.sh <GB> <chunk_s>` — single stable "normal" chunk type, with auto
  lab-reset on a wedge; simplest and most robust.
* `generate_robust.sh`, `generate_fluct.sh`, `generate_big_dataset.sh` — other mixes.
* `capture_attack.sh` / `capture_benign.sh` — capture each class **separately**
  (most reliable; compose the mix afterwards in step 4).
* `generate_dataset.sh` — the original 3-dataset (ds1–ds3) generator.

> **Tip for a clean mix:** solo floods are rock-solid (~55–68k pps). If concurrent
> long chunks still occasionally wedge on your host, capture attack and benign
> separately (`capture_attack.sh` + `capture_benign.sh`) and let `build_mixed_windows.py`
> (step 4) compose any attack fraction you want from the two pools — this is the most
> repeatable path and gives you full control over the 30 % average.

---

## 4. Compose the windowed, address-randomized training set

`build_mixed_windows.py` pools every captured packet by label, then composes
100-packet windows whose per-window attack fraction fluctuates (smoothed random walk
→ logistic) but **averages exactly `--attack-frac`**, and applies a fresh random byte
permutation to the MAC/IP byte positions of each window (the **address randomization**).

You normally don't call it directly — the pipeline script does. To call it alone:

```bash
cd ddos_cnn_xgb
.venv/bin/python -I build_mixed_windows.py \
    -i ../datasets/pcap_big -o bigrun/mixed_masked.h5 \
    -w 100 -p 64 --attack-frac 0.30 --seed 1 --tmp bigrun/pool.h5
```

Output `bigrun/mixed_masked.h5`: `X uint8 [N,100,64]`, `y int32 [N,100]`.
Our run produced **410,766 windows, mean attack 30.0 %** (per-window 2–57 %).

---

## 5. Train + evaluate (one command)

```bash
cd ddos_cnn_xgb
./run_final_pipeline.sh ../datasets/pcap_big bigrun
```

This does everything in step 4 **and**:
1. retrains the shipped global-window arch (`run003`, MSE) as a baseline,
2. trains the **per-packet** model (`perpacket`, BCE),
3. scores all three (shipped / retrained / per-packet) on an identical held-out split
   and writes `bigrun/comparison.csv` with accuracy, benign/DDoS P/R/F1 and the
   NATWORK FP/FN rates.

To train models individually:

```bash
# per-packet model (the one that passes the KPIs)
.venv/bin/python -I train_model.py -i bigrun/mixed_masked.h5 -o bigrun/perpacket \
    --arch perpacket --loss bce --train-cap 150000 --epochs 8 --seed 42

# shipped architecture retrained on the new data (baseline)
.venv/bin/python -I train_model.py -i bigrun/mixed_masked.h5 -o bigrun/run003_retrained \
    --arch run003 --loss mse --train-cap 200000 --epochs 20 --seed 42

# compare any set of models on the same test split
.venv/bin/python -I evaluate_compare.py -i bigrun/mixed_masked.h5 \
    -m shipped_run003 best_run/run_003 \
    -m perpacket bigrun/perpacket \
    --eval-cap 60000 --seed 42 --csv bigrun/comparison.csv
```

---

## 6. Why the per-packet model passes the KPIs

Short version: the shipped `run003` head flattens the whole 100-packet window into one
`Dense` layer, so it smears a single verdict across the window and fails on interleaved
traffic; the new `perpacket` head uses only `(1×k)` convolutions that never cross the
packet axis, so it classifies each packet independently. Same `(100,64,1)→(100,)` I/O,
~17× fewer parameters, and it clears FP<1 %/FN<1 % by orders of magnitude.

The architectures and the full KPI comparison table live in
**`ddos_cnn_xgb/README.md`** (the detector) and **`ddos_cnn_xgb/bigrun/README.md`** (the
trained model + `comparison.csv`). This guide only *produces* those results.

---

## 7. What's committed vs. regenerated

**Committed (code + trained model):**
* `ddos_cnn_xgb/*.py`, `ddos_cnn_xgb/run_*.sh` — converter, windowing, training, evaluation.
* `datasets/*.sh` — all capture/generation scripts.
* `infrastructure/5g/ueransim/patch/`, modified `Dockerfile`s, `entrypoint.sh`, `users.json` — the lab fix.
* `ddos_cnn_xgb/bigrun/perpacket/`, `ddos_cnn_xgb/bigrun/run003_retrained/` — trained models (`model.json` + `run.weights.h5` + params/history/split).
* `ddos_cnn_xgb/bigrun/comparison.csv` — the KPI results.

**Not committed (regenerate with this guide):**
* `datasets/pcap_big/` — raw captures (~15 GB).
* `ddos_cnn_xgb/bigrun/mixed_masked.h5` — composed windowed dataset (~2.7 GB).
* `infrastructure/captures/`, `ddos_cnn_xgb/.venv/`.
