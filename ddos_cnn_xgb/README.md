# DDoS_CNN_xgb

> **Hackathon contribution (per-packet detector).** The sections further down document
> the original toolkit. This block documents what was added for the NATWORK hackathon:
> a per-packet CNN that meets the KPIs, plus a memory-safe, reproducible pipeline over
> the real `datasets/pcap_big/` captures. For the lab that produces the traffic see
> `../infrastructure/README.md`; for the datasets and label rule see `../datasets/README.md`;
> for the trained model and KPI numbers see [`bigrun/README.md`](bigrun/README.md); for the
> end-to-end walkthrough see [`../REPRODUCE.md`](../REPRODUCE.md).
>
> **New scripts**
> | Script | Role |
> |--------|------|
> | `fast_convert_pcap.py` | streaming, memory-safe pcap→HDF5 (mmap, no scapy); same UE-IP label rule, scales to many GB |
> | `split_windows_stream.py` | streaming windowing + per-window MAC/IP byte randomisation |
> | `build_mixed_windows.py` | pools captured packets by label and composes windows with a **fluctuating** per-window attack fraction averaging ~30 %, address-randomised |
> | `train_model.py` | trains either architecture (`--arch run003|perpacket`, `--loss mse|bce`) |
> | `evaluate_compare.py` | scores several models on one identical held-out split; writes `comparison.csv` |
> | `run_final_pipeline.sh` | compose → train baseline + per-packet → compare, in one command |
>
> **The two architectures** (`train_model.py`) — both take a 100-packet window
> `(100,64,1)` and output one score per packet `(100,)`, so the pipeline is unchanged:
> | Model | Head | Params | NATWORK FP<1 % & FN<1 % |
> |-------|------|-------:|:-----------------------:|
> | `run003` (shipped) | `Flatten → Dense(100)`, 3×3 convs — blends the whole window | 670,820 | ❌ (FP 55.7 %, FN 36.7 %) |
> | **`perpacket` (new)** | all `(1×k)` convs + per-packet `Dense(1)` — never cross the packet axis | **38,417** | ✅ (FP 0.0001 %, FN 0.009 %) |
>
> The per-packet head classifies each packet independently, so interleaved
> benign/attack windows and randomised addresses no longer confuse it — which is why it
> passes where retraining the global-window head does not. Full numbers and confusion
> matrices: [`bigrun/README.md`](bigrun/README.md).

# Repository Structure

```text
.
├── add_labels.py         # Assign benign/DDoS labels to packets
├── convert_pcap.py       # Convert PCAP files into HDF5 datasets
├── load_results_xgb.py   # Load and summarize XGBoost optimization results
├── mask_address.py       # Mask/anonymize IP addresses
├── training.py           # Train the CNN model
├── vis_summary.py        # Generate visualizations of training and optimization results
├── xgb.py                # Train and evaluate the XGBoost classifier
├── param_training.py     # Hyperparameter search for the CNN
├── README.md

```

## File Description

| File                  | Description                                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------------------- |
| `convert_pcap.py`     | Reads raw PCAP files and converts them into HDF5 and adds labels                                            |
| `add_labels.py`       | Labels flows as **Benign** or **Syn** according to the selected dataset.                                    |
| `mask_address.py`     | Masks or anonymizes IP addresses before model training to reduce overfitting to specific network addresses. |
| `training.py`         | Trains the Convolutional Neural Network (CNN) (single run)                                                  |
| `param_training.py`   | Performs CNN hyperparameter optimization by evaluating different network configurations.                    |
| `xgb.py`              | Trains and evaluates an XGBoost classifier using the generated features.                                    |
| `load_results_xgb.py` | Loads and evaluates pre-trained xgboost                                                                     |
| `vis_summary.py`      | Visualizations of hyperparameter searches and model performance.               |

## Typical Workflow

1. Convert PCAP files into HDF5 datasets.
2. Label packets as benign or DDoS.
3. Mask or anonymize IP addresses.
4. Train the CNN model (`training.py`).
5. Perform CNN hyperparameter optimization with `param_training.py`.
6. Generate summary figures using `vis_summary.py`.



# DDoS Packet Classification Dataset and Hyperparameter Search

This repository contains utilities for preparing packet-level datasets from PCAP files, anonymizing network addresses, and performing hyperparameter optimization for a TensorFlow-based packet classification model.

## Workflow

The typical workflow consists of three steps:

1. Convert PCAP files into an HDF5 dataset.
2. Anonymize MAC and IP addresses while preserving consistency within packet windows.
3. Train and evaluate models using hyperparameter search.

```
PCAP files
     │
     ▼
convert_pcap_to_h5.py
     │
     ▼
tf_dataset_pckt.h5
     │
     ▼
split_h5_into_windows.py
     │
     ▼
dataset_masked.h5
     │
     ▼
hyperparam_training.py + param.json
     │
     ▼
Training results
```

---

# 1. PCAP to HDF5

`convert_pcap_to_h5.py` converts one or more PCAP files into an HDF5 dataset suitable for TensorFlow training.

Each packet is converted into a fixed-length array of bytes.

## Features

* Reads every `.pcap` file from a directory.
* Converts packets into fixed-length byte vectors.
* Pads or truncates packets to a specified length.
* Generates packet labels according to the selected labeling strategy.
* Saves the dataset as an HDF5 file containing:

  * `X` – packet byte arrays
  * `y` – packet labels

## Usage

```bash
python convert_pcap_to_h5.py \
    --input data/pcaps \
    --output tf_dataset/tf_dataset_pckt.h5 \
    --packet-length 64 \
    --target-ip 192.168.20.187 \
    --ddos-name wifi-ddos
```

## Output

```
tf_dataset_pckt.h5

X : uint8 [num_packets, packet_length]
y : int32 [num_packets]
```

---

# 2. Dataset Anonymization

`split_h5_into_windows.py ` randomizes Ethernet MAC addresses and IPv4 addresses and splits the dataset into windows of desired size.

The dataset is divided into fixed-size windows. For every window, a random byte permutation is generated.

The permutation is:

* consistent for every packet inside a window,
* different for different windows.

This preserves communication patterns while removing the original addresses.

## Masked fields

The following byte positions are randomized:

* Ethernet source MAC
* Ethernet destination MAC
* IPv4 source address
* IPv4 destination address

## Usage

```bash
python split_h5_into_windows.py  \
    --input tf_dataset/tf_dataset_pckt.h5 \
    --output tf_dataset/dataset_masked.h5 \
    --window 100 \
    --packet-length 64
```

---

# 3. Hyperparameter Search

`hyperparam_training.py` performs a grid search over the hyperparameter space defined in a JSON configuration file.

Each hyperparameter combination is trained independently and stored in its own output directory.

## Usage

```bash
python hyperparam_training.py \
    --input tf_dataset/dataset_masked.h5 \
    --config param.json \
    --output hyperparameter_results
```

---

# 4. Classification with a trained model

`classify_h5.py` loads a trained run (`model.json` + `run.weights.h5`, e.g. from `best_run.zip`)
and scores every packet of a windowed dataset (0 = benign, 1 = DDoS). If the dataset
contains labels, a packet-level classification report is printed as well.

## Usage

```bash
unzip best_run.zip -d best_run

python classify_h5.py \
    --input tf_dataset/dataset_masked.h5 \
    --model-dir best_run/run_003 \
    --output tf_dataset/predictions.h5
```

Note: `split_h5_into_windows.py` drops the last incomplete window, so a PCAP with fewer
than `--window` packets produces no windows at all.

---

# Configuration File

Hyperparameters are stored in a JSON file.

Example:

```json
{
    "window": 100,
    "packet_length": 64,

    "search_space": {
        "filters1": [16, 32],
        "filters2": [32, 64],
        "dense": [64, 128],
        "learning_rate": [0.001],
        "batch_size": [64, 128],
        "epochs": [10, 20],
        "dropout": [0.0, 0.5]
    }
}
```

The Cartesian product of every value in `search_space` defines the experiments that will be executed.

---

# Output Directory

Each experiment produces a directory similar to

```
hyperparameter_results/
├── run_000/
│   ├── model.json
│   ├── run.weights.h5
│   ├── history.json
│   ├── parameters.json
│   ├── classification_report.json
│   └── confusion_matrix.npy
├── run_001/
├── run_002/
└── summary.json
```

The summary file contains the most important metrics for every experiment, including:

* precision
* recall
* F1-score
* best validation accuracy
* best validation loss
* execution time

---

# Requirements

The scripts require Python 3.10 or newer and the following packages:

* numpy
* h5py
* tensorflow
* scapy
* scikit-learn

They can be installed using pip:

```bash
pip install numpy h5py tensorflow scapy scikit-learn
```

---

# Dataset Format

The HDF5 datasets use the following structure:

```
X : uint8
    Shape:
        (packets, packet_length)
    or
        (windows, window_size, packet_length)

y : labels
```

where:

* `packet_length` is typically 64 bytes,
* `window_size` is the number of packets grouped together for training.

---


