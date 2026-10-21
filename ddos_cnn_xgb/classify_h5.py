#!/usr/bin/env python3

"""
Classify packets in a windowed HDF5 dataset with a trained CNN run
(model.json + run.weights.h5, as produced by hyperparam_training.py).

The model outputs one sigmoid score per packet in each window
(0 = benign, 1 = DDoS). If the dataset contains labels (y), a
classification report against them is printed as well.

Example:
    python classify_h5.py \
        --input tf_dataset/dataset_masked.h5 \
        --model-dir best_run/run_003 \
        --output predictions.h5
"""

import argparse
import json
from pathlib import Path

import h5py
import numpy as np
import tensorflow as tf


def parse_args():
    parser = argparse.ArgumentParser(description="Classify windowed packets with a trained CNN.")
    parser.add_argument("-i", "--input", type=Path, required=True, help="Windowed HDF5 dataset (X: windows x packets x bytes).")
    parser.add_argument("-m", "--model-dir", type=Path, required=True,
                        help="Directory containing model.json and run.weights.h5.")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Optional HDF5 file to store per-packet scores.")
    parser.add_argument("-t", "--threshold", type=float, default=0.5, help="Decision threshold (default: 0.5).")
    parser.add_argument("-b", "--batch-size", type=int, default=128, help="Prediction batch size (default: 128).")
    parser.add_argument("--window-threshold", type=float, default=0.5,
                        help="Fraction of DDoS packets above which a window is reported as attack (default: 0.5).")
    return parser.parse_args()


def load_model(model_dir):
    with open(model_dir / "model.json") as f:
        model = tf.keras.models.model_from_json(f.read())
    model.load_weights(model_dir / "run.weights.h5")
    return model


def main():
    args = parse_args()

    with h5py.File(args.input, "r") as f:
        X = f["X"][:]
        y = f["y"][:] if "y" in f else None

    model = load_model(args.model_dir)
    expected = model.input_shape[1:3]
    if tuple(X.shape[1:3]) != tuple(expected):
        raise SystemExit(f"Dataset windows are {X.shape[1:3]}, but the model expects {expected}.")

    probs = model.predict(X[..., np.newaxis].astype(np.float32), batch_size=args.batch_size, verbose=0)
    preds = (probs > args.threshold).astype(np.int32)

    n_windows, window = preds.shape
    per_window = preds.mean(axis=1)
    attack_windows = int((per_window > args.window_threshold).sum())

    print(f"Windows                : {n_windows} (x {window} packets)")
    print(f"Packets flagged DDoS   : {int(preds.sum())} / {preds.size} ({100 * preds.mean():.2f}%)")
    print(f"Windows flagged attack : {attack_windows} / {n_windows} ({100 * attack_windows / n_windows:.2f}%)")
    print(f"Mean score             : {probs.mean():.4f}")

    if y is not None and y.any():
        from sklearn.metrics import classification_report, confusion_matrix

        yt = y.ravel()
        yp = preds.ravel()
        print("\nGround truth available - packet-level evaluation:")
        print(confusion_matrix(yt, yp, labels=[0, 1]))
        print(classification_report(yt, yp, labels=[0, 1], target_names=["benign", "ddos"], zero_division=0, digits=4))

    if args.output:
        with h5py.File(args.output, "w") as f:
            f.create_dataset("probs", data=probs.astype(np.float32))
            f.create_dataset("preds", data=preds)
            if y is not None:
                f.create_dataset("y", data=y)
        print(f"Scores saved to {args.output}")


if __name__ == "__main__":
    main()
