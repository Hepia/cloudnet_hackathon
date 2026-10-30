#!/usr/bin/env python3
"""
Score one or more trained CNN runs on the SAME held-out test windows of a masked
dataset, and report the KPIs used in the hackathon report plus the NATWORK
FP/FN ceilings.

Per model it prints, at the packet level:
  accuracy, benign precision/recall/f1, DDoS precision/recall/f1,
  FP rate (= 1 - benign recall, NATWORK KPI 3.2 target < 1%),
  FN rate (= 1 - DDoS recall,   NATWORK KPI 3.3 target < 1%),
and the window-level accuracy (majority vote), matching report Table 5.

The test split is reconstructed with the same train_test_split(seed) as
train_model.py, so every model is judged on identical, never-trained windows.
"""
import argparse
import json

import h5py
import numpy as np
import tensorflow as tf
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix
from sklearn.model_selection import train_test_split


def load_model(run_dir):
    with open(f"{run_dir}/model.json") as f:
        model = tf.keras.models.model_from_json(f.read())
    model.load_weights(f"{run_dir}/run.weights.h5")
    return model


def eval_model(model, X, y, threshold, batch):
    """X: uint8 [n,w,p]; y: int [n,w]. Returns metrics dict."""
    probs = model.predict(X[..., np.newaxis].astype(np.float32), batch_size=batch, verbose=0)
    preds = (probs > threshold).astype(np.int32)
    yt = y.ravel()
    yp = preds.ravel()

    acc = float((yt == yp).mean())
    (p0, p1), (r0, r1), (f0, f1), _ = precision_recall_fscore_support(
        yt, yp, labels=[0, 1], zero_division=0)
    cm = confusion_matrix(yt, yp, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    # window-level majority vote (report Table 5)
    yw = (y.mean(axis=1) > 0.5).astype(int)
    pw = (preds.mean(axis=1) > 0.5).astype(int)
    win_acc = float((yw == pw).mean())

    return {
        "accuracy": acc,
        "benign_prec": float(p0), "benign_rec": float(r0), "benign_f1": float(f0),
        "ddos_prec": float(p1), "ddos_rec": float(r1), "ddos_f1": float(f1),
        "fp_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "fn_rate": float(fn / (fn + tp)) if (fn + tp) else 0.0,
        "window_acc": win_acc,
        "cm": [int(tn), int(fp), int(fn), int(tp)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True, help="Masked windowed HDF5 dataset.")
    ap.add_argument("-m", "--model", action="append", nargs=2, metavar=("NAME", "DIR"),
                    required=True, help="Model name and run dir; repeatable.")
    ap.add_argument("--test-size", type=float, default=0.33)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval-cap", type=int, default=0, help="Max test windows (0 = all).")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--csv", default=None, help="Optional CSV output path.")
    args = ap.parse_args()

    with h5py.File(args.input, "r") as f:
        n = f["X"].shape[0]
        idx = np.arange(n)
        _, test_idx = train_test_split(idx, test_size=args.test_size, random_state=args.seed)
        test_idx.sort()
        if args.eval_cap and len(test_idx) > args.eval_cap:
            rng = np.random.default_rng(args.seed)
            test_idx = np.sort(rng.choice(test_idx, args.eval_cap, replace=False))
        X = f["X"][test_idx]
        y = f["y"][test_idx]

    print(f"test windows: {len(test_idx)} of {n}  (packets: {y.size})\n")

    rows = []
    for name, run_dir in args.model:
        model = load_model(run_dir)
        m = eval_model(model, X, y, args.threshold, args.batch)
        m["model"] = name
        rows.append(m)

    cols = ["accuracy", "benign_prec", "benign_rec", "benign_f1",
            "ddos_prec", "ddos_rec", "ddos_f1", "fp_rate", "fn_rate", "window_acc"]
    header = f"{'model':<14}" + "".join(f"{c:>12}" for c in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['model']:<14}" + "".join(f"{r[c]:>12.4f}" for c in cols))
    print()
    print("NATWORK targets: fp_rate < 0.01 (KPI 3.2), fn_rate < 0.01 (KPI 3.3), "
          "ddos_rec > 0.80 (KPI 4.4), fp_rate < 0.05 (KPI 4.5)")
    for r in rows:
        ok = "PASS" if (r["fp_rate"] < 0.01 and r["fn_rate"] < 0.01) else "FAIL"
        print(f"  {r['model']:<14} FP={r['fp_rate']*100:6.3f}%  FN={r['fn_rate']*100:6.3f}%  "
              f"-> KPI 3.2/3.3 {ok}")

    if args.csv:
        import csv
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["model"] + cols + ["cm_tn", "cm_fp", "cm_fn", "cm_tp"])
            for r in rows:
                w.writerow([r["model"]] + [f"{r[c]:.6f}" for c in cols] + r["cm"])
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
