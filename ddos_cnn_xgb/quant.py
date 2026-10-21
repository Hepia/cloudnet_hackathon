import os
import json
import h5py
import numpy as np
import tensorflow as tf

from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score


# ============================================================
# Configuration
# ============================================================

RESULT_DIR = "/mnt/natwork/nas/data/anna.padee/ddos/models/ddos/hyperparameter_results"
OUTPUT_JSON = "quantization_results1.json"

infile = "tf_dataset/dataset_masked.h5"

window = 100
pckt_len = 64

# ============================================================
# Load dataset
# ============================================================

with h5py.File(infile, "r") as f:
    X = f["X"][:]
    y = f["y"][:]
X = X[..., np.newaxis]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.33,
    random_state=42
)

# ============================================================
# Representative dataset for INT8 calibration
# ============================================================

def representative_dataset():

    for sample in X_train[:100]:
        sample = np.expand_dims(sample.astype(np.float32), axis=0)
        yield [sample]

# ============================================================
# Evaluate TFLite model
# ============================================================

def evaluate_tflite(tflite_model, X, y):


    interpreter = tf.lite.Interpreter(model_content=tflite_model)
    interpreter.allocate_tensors()
    #print(interpreter.get_input_details())
    #print(interpreter.get_output_details())

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
#    print("Interpreter expects:", input_details[0]["shape"])
#    print("X_test shape:", X.shape)

    input_dtype = input_details[0]["dtype"]
    output_dtype = output_details[0]["dtype"]

    input_scale, input_zero = input_details[0]["quantization"]
    output_scale, output_zero = output_details[0]["quantization"]

    predictions = []

    for sample in X:

        sample = np.expand_dims(sample, axis=0)

        if input_dtype == np.int8:
            sample = sample / input_scale + input_zero
            sample = np.round(sample).astype(np.int8)
        else:
            sample = sample.astype(input_dtype)

        interpreter.set_tensor(input_details[0]["index"], sample)
        interpreter.invoke()

        output = interpreter.get_tensor(output_details[0]["index"])

        if output_dtype == np.int8:
            output = (output.astype(np.float32) - output_zero) * output_scale

        predictions.append(output[0])

    predictions = np.array(predictions)

    preds = (predictions > 0.5).astype(int)

    precision = precision_score(
        y,
        preds,
        average="macro",
        zero_division=0
    )

    recall = recall_score(
        y,
        preds,
        average="macro",
        zero_division=0
    )

    f1 = f1_score(
        y,
        preds,
        average="macro",
        zero_division=0
    )

    return precision, recall, f1

# ============================================================
# Main loop
# ============================================================

results = []

run_dirs = sorted(
    d for d in os.listdir(RESULT_DIR)
    if d.startswith("run_")
)

for run in run_dirs:

    print(f"Processing {run}")

    run_path = os.path.join(RESULT_DIR, run)

    with open(os.path.join(run_path, "model.json")) as f:
        model = tf.keras.models.model_from_json(f.read())

    model.load_weights(os.path.join(run_path, "run.weights.h5"))

    with open(os.path.join(run_path, "parameters.json")) as f:
        params = json.load(f)

    for quantization in ["none", "float16", "int8"]:

        converter = tf.lite.TFLiteConverter.from_keras_model(model)

        if quantization == "float16":

            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            converter.target_spec.supported_types = [tf.float16]

        elif quantization == "int8":

            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            converter.representative_dataset = representative_dataset

            converter.target_spec.supported_ops = [
                tf.lite.OpsSet.TFLITE_BUILTINS_INT8
            ]

            converter.inference_input_type = tf.int8
            converter.inference_output_type = tf.int8

        tflite_model = converter.convert()

        model_size = len(tflite_model)

        precision, recall, f1 = evaluate_tflite(
            tflite_model,
            X_test,
            y_test
        )

        result = {
            "run": run,
            "quantization": quantization,
            "model_size_bytes": model_size,
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            **params
        }

        results.append(result)

# ============================================================
# Save results
# ============================================================

with open(OUTPUT_JSON, "w") as f:
    json.dump(results, f, indent=4)

print(f"\nSaved results to {OUTPUT_JSON}")