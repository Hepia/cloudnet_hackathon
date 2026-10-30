#!/usr/bin/env python3
"""
Train the packet-level CNN (same architecture as hyperparam_training.py / best_run)
on an address-randomized windowed dataset, and save it in the best_run run layout
(model.json + run.weights.h5 + parameters.json) so classify_h5.py can load it.

The architecture and default hyperparameters match best_run/run_003:
  Conv2D(f1,3x3) - MaxPool - Conv2D(f2,3x3) - MaxPool - Flatten - Dense(d) - Dropout
  - Dense(window, sigmoid);  loss = MSE, optimizer = Adam.
Output is one sigmoid score per packet in the window (0 benign / 1 DDoS).

Train/test split is deterministic (sklearn train_test_split, fixed seed) on window
indices, so evaluate_compare.py can score any model on the exact same held-out test
windows. Training may be capped to a subset of the train split for time on CPU; the
test split is never touched here.
"""
import argparse
import json
import os
import time

import h5py
import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split


def build_run003(window, pckt_len, p):
    """Exact best_run/run_003 architecture: global window features -> Dense(window)."""
    return tf.keras.Sequential([
        tf.keras.layers.Input(shape=(window, pckt_len, 1)),
        tf.keras.layers.Conv2D(p["filters1"], (3, 3), activation="relu"),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Conv2D(p["filters2"], (3, 3), activation="relu"),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(p["dense"], activation="relu"),
        tf.keras.layers.Dropout(p["dropout"]),
        tf.keras.layers.Dense(window, activation="sigmoid"),
    ], name="run003")


def build_perpacket(window, pckt_len, p):
    """Per-packet CNN with the SAME I/O contract (window,pckt_len,1) -> (window,).
    All kernels are (1,k): they span bytes WITHIN a packet and never across the
    100-packet axis, so output j depends only on packet j's bytes. This gives true
    per-packet classification, which the global run003 head cannot do on windows
    where benign and attack packets are interleaved."""
    inp = tf.keras.layers.Input(shape=(window, pckt_len, 1))
    x = tf.keras.layers.Conv2D(p["filters1"], (1, 3), activation="relu", padding="same")(inp)
    x = tf.keras.layers.Conv2D(p["filters1"], (1, 3), activation="relu", padding="same")(x)
    x = tf.keras.layers.MaxPooling2D((1, 2))(x)
    x = tf.keras.layers.Conv2D(p["filters2"], (1, 3), activation="relu", padding="same")(x)
    x = tf.keras.layers.Conv2D(p["filters2"], (1, 3), activation="relu", padding="same")(x)
    x = tf.keras.layers.MaxPooling2D((1, 2))(x)
    # collapse the byte axis into per-packet features, then a per-packet dense head
    x = tf.keras.layers.Reshape((window, -1))(x)
    x = tf.keras.layers.Dense(p["dense"], activation="relu")(x)
    x = tf.keras.layers.Dropout(p["dropout"])(x)
    out = tf.keras.layers.Dense(1, activation="sigmoid")(x)   # (window, 1)
    out = tf.keras.layers.Reshape((window,))(out)
    return tf.keras.Model(inp, out, name="perpacket")


def build_model(window, pckt_len, p, loss="bce", arch="perpacket"):
    model = build_perpacket(window, pckt_len, p) if arch == "perpacket" \
        else build_run003(window, pckt_len, p)
    loss_fn = (tf.keras.losses.BinaryCrossentropy() if loss == "bce"
               else tf.keras.losses.MeanSquaredError())
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=p["learning_rate"]),
                  loss=loss_fn, metrics=["accuracy"])
    return model


def make_ds(X_u8, y, batch, shuffle):
    """uint8 windows -> float32 (W,P,1); labels float32 (W,). Batched tf.data."""
    ds = tf.data.Dataset.from_tensor_slices((X_u8, y.astype(np.float32)))
    if shuffle:
        ds = ds.shuffle(min(len(y), 50000), seed=42, reshuffle_each_iteration=True)
    ds = ds.batch(batch).map(
        lambda x, t: (tf.cast(x, tf.float32)[..., tf.newaxis], t),
        num_parallel_calls=tf.data.AUTOTUNE).prefetch(tf.data.AUTOTUNE)
    return ds


def main():
    ap = argparse.ArgumentParser(description="Train packet-level CNN on masked windows.")
    ap.add_argument("-i", "--input", required=True, help="Masked windowed HDF5 dataset.")
    ap.add_argument("-o", "--output", required=True, help="Output run directory.")
    ap.add_argument("--params", default=None, help="JSON hyperparameters (defaults = run_003).")
    ap.add_argument("--test-size", type=float, default=0.33)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train-cap", type=int, default=0,
                    help="Max training windows (0 = use all of the train split).")
    ap.add_argument("--epochs", type=int, default=None, help="Override epochs.")
    ap.add_argument("--loss", choices=["bce", "mse"], default="bce",
                    help="Training loss (bce default; mse reproduces the repo recipe).")
    ap.add_argument("--arch", choices=["perpacket", "run003"], default="perpacket",
                    help="perpacket = per-packet head (default); run003 = exact shipped architecture.")
    args = ap.parse_args()

    params = {"filters1": 16, "filters2": 32, "dense": 64,
              "learning_rate": 1e-3, "batch_size": 128, "epochs": 20, "dropout": 0.0}
    if args.params:
        params.update(json.load(open(args.params)))
    if args.epochs is not None:
        params["epochs"] = args.epochs

    with h5py.File(args.input, "r") as f:
        n = f["X"].shape[0]
        window = f["X"].shape[1]
        pckt_len = f["X"].shape[2]

        idx = np.arange(n)
        train_idx, test_idx = train_test_split(idx, test_size=args.test_size,
                                               random_state=args.seed)
        train_idx.sort()
        if args.train_cap and len(train_idx) > args.train_cap:
            rng = np.random.default_rng(args.seed)
            train_idx = np.sort(rng.choice(train_idx, args.train_cap, replace=False))

        print(f"windows total={n} train={len(train_idx)} test={len(test_idx)} "
              f"shape=({window},{pckt_len})", flush=True)
        # h5py fancy indexing needs sorted unique indices (train_idx is sorted)
        Xtr = f["X"][train_idx]
        ytr = f["y"][train_idx]

    os.makedirs(args.output, exist_ok=True)
    model = build_model(window, pckt_len, params, loss=args.loss, arch=args.arch)
    model.summary()

    t0 = time.perf_counter()
    val_frac = 0.1
    cut = int(len(Xtr) * (1 - val_frac))
    train_ds = make_ds(Xtr[:cut], ytr[:cut], params["batch_size"], shuffle=True)
    val_ds = make_ds(Xtr[cut:], ytr[cut:], params["batch_size"], shuffle=False)

    history = model.fit(train_ds, validation_data=val_ds, epochs=params["epochs"], verbose=2)
    elapsed = time.perf_counter() - t0

    model.save_weights(os.path.join(args.output, "run.weights.h5"))
    with open(os.path.join(args.output, "model.json"), "w") as fh:
        fh.write(model.to_json())
    with open(os.path.join(args.output, "parameters.json"), "w") as fh:
        json.dump(params, fh, indent=4)
    with open(os.path.join(args.output, "history.json"), "w") as fh:
        json.dump(history.history, fh, indent=4)
    with open(os.path.join(args.output, "split.json"), "w") as fh:
        json.dump({"test_size": args.test_size, "seed": args.seed,
                   "n_windows": int(n), "train_cap": args.train_cap,
                   "train_used": int(len(Xtr))}, fh, indent=4)
    print(f"done in {elapsed:.1f}s -> {args.output}", flush=True)


if __name__ == "__main__":
    main()
