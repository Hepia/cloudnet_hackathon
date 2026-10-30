#!/usr/bin/env python3
"""
Streaming windowing + per-window address randomization (memory-safe replacement
for split_h5_into_windows.py).

Reads a per-packet HDF5 dataset (X: [packets, pckt_len], y: [packets]) and writes
a windowed dataset (X: [windows, window, pckt_len], y: [windows, window]).

For every window a fresh random permutation of 0..255 is drawn and applied to the
MAC/IP address byte positions (same MASK_INDICES as split_h5_into_windows.py),
consistent within the window and different across windows. This is the
"address randomization" / anonymization step. The final incomplete window is
dropped, matching the shipped script.
"""
import argparse

import h5py
import numpy as np

MASK_INDICES = (
    0, 1, 2, 3, 4, 5,       # dst MAC
    6, 7, 8, 9, 10, 11,     # src MAC
    26, 27, 28, 29,         # src IP
    30, 31, 32, 33,         # dst IP
)


def main():
    ap = argparse.ArgumentParser(description="Stream windows + randomize MAC/IP bytes.")
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("-w", "--window", type=int, default=100)
    ap.add_argument("-p", "--packet-length", type=int, default=64)
    ap.add_argument("--block-windows", type=int, default=20000,
                    help="Windows processed per I/O block.")
    ap.add_argument("--seed", type=int, default=None, help="Optional RNG seed.")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    w = args.window
    p = args.packet_length
    mask = np.asarray(MASK_INDICES)

    with h5py.File(args.input, "r") as fin, h5py.File(args.output, "w") as fout:
        X = fin["X"]
        y = fin["y"]
        n_pkts = X.shape[0]
        n_windows = n_pkts // w

        Xo = fout.create_dataset("X", shape=(0, w, p), maxshape=(None, w, p),
                                 dtype=np.uint8, chunks=(min(args.block_windows, max(n_windows, 1)), w, p))
        yo = fout.create_dataset("y", shape=(0, w), maxshape=(None, w), dtype=np.int32,
                                 chunks=(min(args.block_windows, max(n_windows, 1)), w))

        done = 0
        while done < n_windows:
            nb = min(args.block_windows, n_windows - done)
            r0 = done * w
            r1 = r0 + nb * w
            Xb = X[r0:r1, :p].reshape(nb, w, p).copy()
            yb = y[r0:r1].reshape(nb, w)

            # per-window permutation applied to the address byte positions
            for i in range(nb):
                perm = rng.permutation(256).astype(np.uint8)
                Xb[i][:, mask] = perm[Xb[i][:, mask]]

            base = Xo.shape[0]
            Xo.resize(base + nb, axis=0)
            yo.resize(base + nb, axis=0)
            Xo[base:base + nb] = Xb
            yo[base:base + nb] = yb
            done += nb
            print(f"windows {done}/{n_windows}", end="\r", flush=True)

        fout.attrs["window"] = w
        fout.attrs["packet_length"] = p
        print(f"\nwrote {done} windows of {w} packets to {args.output}")


if __name__ == "__main__":
    main()
