#!/usr/bin/env python3

"""
Split an HDF5 dataset into fixed-size windows and randomly remap IP/MAC
address bytes. The mapping is consistent within each window but different
for each window.

Example:
    split_h5_into_windows.py \
        --input tf_dataset/tf_dataset_pckt.h5 \
        --output tf_dataset/dataset_masked_50.h5 \
        --window 50 \
        --packet-length 64
"""

import argparse

import h5py
import numpy as np

# Byte positions to randomize:
# - Ethernet MAC addresses: 0-11
# - IPv4 source/destination addresses: 26-33
MASK_INDICES = (
    0, 1, 2, 3, 4, 5,       #dst MAC
    6, 7, 8, 9, 10, 11,     #src MAC
    26, 27, 28, 29,         #src IP
    30, 31, 32, 33,         #dst IP
)


def parse_args():
    parser = argparse.ArgumentParser(description="Split dataset into windows and randomize MAC/IP bytes.")

    parser.add_argument("-i", "--input", required=True, help="Input HDF5 dataset.")
    parser.add_argument("-o", "--output", required=True, help="Output HDF5 dataset.")
    parser.add_argument("-w", "--window", type=int, default=50, help="Window size (default: 50).")
    parser.add_argument("-p", "--packet-length", type=int, default=64,
                        help="Number of packet bytes to keep (default: 64).")

    return parser.parse_args()


def main():
    args = parse_args()

    with h5py.File(args.input, "r") as infile:
        X = infile["X"][:]
        y = infile["y"][:]

    X_windows = [X[i:i + args.window, :args.packet_length] for i in range(0, len(X), args.window)]
    y_windows = [y[i:i + args.window] for i in range(0, len(y), args.window)]

    if len(X_windows[-1]) != args.window:
        X_windows = X_windows[:-1]
        y_windows = y_windows[:-1]

    X_windows = np.asarray(X_windows)
    y_windows = np.asarray(y_windows)

    for window in X_windows:
        mapping = np.random.permutation(256)
        window[:, MASK_INDICES] = mapping[window[:, MASK_INDICES]]

    with h5py.File(args.output, "w") as outfile:
        outfile.create_dataset("X", data=X_windows)
        outfile.create_dataset("y", data=y_windows)


if __name__ == "__main__":
    main()