"""
Hyperparameter optimization
"""

import os
import json
import itertools
import time
import h5py
import numpy as np
import tensorflow as tf

from sklearn.metrics import multilabel_confusion_matrix, classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split


infile = "tf_dataset/dataset_masked.h5"

window = 100
pckt_len = 64

RESULT_DIR = "hyperparameter_results2"
os.makedirs(RESULT_DIR, exist_ok=True)

with h5py.File(infile, "r") as f:
    X = f["X"][:]
    y = f["y"][:]

X_train, X_test, y_train, y_test = train_test_split(X,y,test_size=0.33,random_state=42)

# Hyperparameter search space

search_space = {
    "filters1": [16, 32],
    "filters2": [32, 64],
    "dense": [64, 128],
    "learning_rate": [1e-3, 1e-3],
    "batch_size": [64, 128],
    "epochs": [10, 20],
    "dropout": [0.0, 0.5]
}

keys = list(search_space.keys())
experiments = list(itertools.product(*(search_space[k] for k in keys)))

summary = []

def build_model(params):

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(window, pckt_len, 1)),
        tf.keras.layers.Conv2D(params["filters1"],(3,3),activation="relu"),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Conv2D(params["filters2"],(3,3),activation="relu"),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(params["dense"],activation="relu"),
        tf.keras.layers.Dropout(params["dropout"]),
        tf.keras.layers.Dense(100,activation="sigmoid")
    ])

    opt = tf.keras.optimizers.Adam(learning_rate=params["learning_rate"])

    model.compile(optimizer=opt,loss=tf.keras.losses.MeanSquaredError(),metrics=["accuracy"])

    return model


for run_id, values in enumerate(experiments):
    start_time = time.perf_counter()
    params = dict(zip(keys, values))

    print("=" * 70)
    print("Experiment", run_id)
    print(params)

    run_dir = os.path.join(RESULT_DIR,f"run_{run_id:03d}")
    os.makedirs(run_dir, exist_ok=True)

    model = build_model(params)

    train_dataset = tf.data.Dataset.from_tensor_slices((X_train, y_train)).batch(params["batch_size"])
    test_dataset = tf.data.Dataset.from_tensor_slices((X_test, y_test)).batch(params["batch_size"])

    history = model.fit(
        train_dataset,
        validation_data=test_dataset,
        epochs=params["epochs"],
        verbose=2
    )

    probs = model.predict(test_dataset)
    preds = (probs > 0.5).astype(int)

    precision = precision_score(y_test,preds,average="macro",zero_division=0)
    recall = recall_score(y_test,preds,average="macro",zero_division=0)
    f1 = f1_score(y_test,preds,average="macro",zero_division=0)

    cm = multilabel_confusion_matrix(y_test, preds)

    report = classification_report(y_test,preds,output_dict=True,zero_division=0)

    model.save_weights(os.path.join(run_dir, "run.weights.h5"))
    end_time = time.perf_counter()
    elapsed = end_time - start_time

    with open(os.path.join(run_dir, "model.json"), "w") as f:
        f.write(model.to_json())

    with open(os.path.join(run_dir, "history.json"), "w") as f:
        json.dump(history.history, f, indent=4)

    np.save(os.path.join(run_dir, "confusion_matrix.npy"),cm)

    with open(os.path.join(run_dir, "classification_report.json"), "w") as f:
        json.dump(report, f, indent=4)

    with open(os.path.join(run_dir, "parameters.json"), "w") as f:
        json.dump(params, f, indent=4)

    result = {
        **params,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "best_val_accuracy": float(max(history.history["val_accuracy"])),
        "best_val_loss": float(min(history.history["val_loss"])),
        "execution_time_seconds": elapsed
    }

    summary.append(result)

with open(
    os.path.join(RESULT_DIR, "summary1.json"),"w") as f:
    json.dump(summary, f, indent=4)

print("Done.")