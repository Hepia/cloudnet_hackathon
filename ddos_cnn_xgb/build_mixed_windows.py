#!/usr/bin/env python3
"""
Compose an address-randomized windowed dataset from pools of REAL captured packets,
with a per-window attack fraction that FLUCTUATES 0..100% but averages a target
(default 0.30). DDoS traffic realistically arrives in waves, which the clustered
per-window fractions reproduce.

Inputs are one or more directories of .pcap files. Every packet is converted with the
same fast parser and label rule as fast_convert_pcap.py (DDoS iff a frame's IPv4 src or
dst is the UE 10.45.0.2). Label-1 packets form the attack pool, label-0 the benign pool.

For each of N windows (N chosen to use the attack pool ~once at the target average):
  * draw an attack fraction f for the window (clustered via a random-walk "wave"
    signal passed through a logistic, re-centred so the mean hits --attack-frac),
  * fill round(f*W) slots with attack packets and the rest with benign packets, in a
    random interleaved order within the window,
  * draw a 0..255 byte permutation and apply it to the MAC/IP byte positions
    (address randomization, consistent within the window).

Output: X uint8 [N, W, P], y int32 [N, W]  -- the same format split_windows_stream.py
produces, so train_model.py / evaluate_compare.py consume it unchanged.
"""
import argparse
from pathlib import Path

import os
import sys

import h5py
import numpy as np

# Ensure this script's own directory is importable even under `python -I` (which, via
# -P, drops the script dir from sys.path), so the sibling converter module resolves.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fast_convert_pcap as fc

MASK_INDICES = np.array([0,1,2,3,4,5, 6,7,8,9,10,11, 26,27,28,29, 30,31,32,33])


def pool_packets(dirs, packet_length, target_ip, ddos_name, tmp_h5):
    """Convert all pcaps once; return (attack_rows, benign_rows) as uint8 arrays."""
    with h5py.File(tmp_h5, "w") as h5f:
        h5f.create_dataset("X", shape=(0, packet_length), maxshape=(None, packet_length),
                           dtype=np.uint8, chunks=(1_000_000, packet_length))
        h5f.create_dataset("y", shape=(0,), maxshape=(None,), dtype=np.int32, chunks=(1_000_000,))
        files = []
        for d in dirs:
            files += sorted(Path(d).glob("*.pcap"))
        if not files:
            raise SystemExit("no pcaps found in: " + ", ".join(map(str, dirs)))
        tot = atk = 0
        for f in files:
            t, a = fc.convert_file(f, h5f, packet_length, target_ip, ddos_name, 1_000_000)
            tot += t; atk += a
            print(f"  pooled {f.name}: total={t} attack={a}", flush=True)
    with h5py.File(tmp_h5, "r") as h5f:
        X = h5f["X"][:]
        y = h5f["y"][:]
    attack = X[y == 1]
    benign = X[y == 0]
    print(f"pools: attack={len(attack)} benign={len(benign)} (overall {100*len(attack)/max(len(X),1):.1f}% attack)")
    return attack, benign


def wave_fractions(n, mean_frac, rng, smooth=40):
    """n per-window attack fractions in [0,1], clustered into waves, mean≈mean_frac."""
    # random walk -> smoothed -> logistic -> rescale mean
    steps = rng.standard_normal(n)
    walk = np.cumsum(steps)
    if n >= 3:
        k = max(1, min(smooth, n // 3))
        kern = np.ones(k) / k
        walk = np.convolve(walk, kern, mode="same")
    walk = (walk - walk.mean()) / (walk.std() + 1e-9)
    f = 1.0 / (1.0 + np.exp(-1.6 * walk))        # 0..1, bursty
    # rescale so the realized mean matches the target
    f = f * (mean_frac / max(f.mean(), 1e-6))
    return np.clip(f, 0.0, 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", nargs="+", required=True, help="pcap directories (pooled by label).")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("-w", "--window", type=int, default=100)
    ap.add_argument("-p", "--packet-length", type=int, default=64)
    ap.add_argument("--attack-frac", type=float, default=0.30, help="average attack fraction.")
    ap.add_argument("--target-ip", default="10.45.0.2")
    ap.add_argument("--ddos-name", default="ddos")
    ap.add_argument("--windows", type=int, default=0, help="number of windows (0 = size to the attack pool).")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tmp", default=None, help="temp per-packet h5 (default: <output>.pool.h5).")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    W, P = args.window, args.packet_length
    tmp = args.tmp or (args.output + ".pool.h5")

    attack, benign = pool_packets(args.input, P, args.target_ip, args.ddos_name, tmp)
    Path(tmp).unlink(missing_ok=True)
    if len(attack) == 0 or len(benign) == 0:
        raise SystemExit("need both attack and benign packets in the pools")

    # size the dataset so the attack pool is used ~once at the target average
    if args.windows > 0:
        N = args.windows
    else:
        N = int(len(attack) / (args.attack_frac * W))
    N = max(N, 1)

    fracs = wave_fractions(N, args.attack_frac, rng)
    counts = np.round(fracs * W).astype(int)
    counts = np.clip(counts, 0, W)
    print(f"composing {N} windows x {W} pkts; mean attack/window = {counts.mean()/W*100:.1f}%")

    with h5py.File(args.output, "w") as out:
        Xo = out.create_dataset("X", shape=(N, W, P), dtype=np.uint8, chunks=(min(20000, N), W, P))
        yo = out.create_dataset("y", shape=(N, W), dtype=np.int32, chunks=(min(20000, N), W))
        ai = bi = 0
        na, nb = len(attack), len(benign)
        block, buX, buY = 20000, [], []
        base = 0
        for i in range(N):
            ka = int(counts[i]); kb = W - ka
            # sample packets (wrap around the pools; benign is reused as background)
            aidx = (ai + np.arange(ka)) % na; ai += ka
            bidx = (bi + np.arange(kb)) % nb; bi += kb
            win = np.empty((W, P), dtype=np.uint8)
            lab = np.empty((W,), dtype=np.int32)
            order = rng.permutation(W)
            apos, bpos = order[:ka], order[ka:]
            if ka:
                win[apos] = attack[aidx]; lab[apos] = 1
            if kb:
                win[bpos] = benign[bidx]; lab[bpos] = 0
            perm = rng.permutation(256).astype(np.uint8)
            win[:, MASK_INDICES] = perm[win[:, MASK_INDICES]]
            buX.append(win); buY.append(lab)
            if len(buX) == block or i == N - 1:
                Xb = np.stack(buX); Yb = np.stack(buY)
                Xo[base:base + len(buX)] = Xb; yo[base:base + len(buX)] = Yb
                base += len(buX); buX, buY = [], []
                print(f"  windows {base}/{N}", end="\r", flush=True)
        out.attrs["attack_frac_mean"] = float(counts.mean() / W)
        out.attrs["window"] = W
    print(f"\nwrote {N} windows to {args.output} (mean attack {counts.mean()/W*100:.1f}%)")


if __name__ == "__main__":
    main()
