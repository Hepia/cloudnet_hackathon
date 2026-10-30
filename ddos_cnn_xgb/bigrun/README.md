# Trained models & results

Produced by `../run_final_pipeline.sh` on a ~15 GB real capture (benign app mix +
Mirai SYN flood), composed into 410,766 address-randomized 100-packet windows with a
fluctuating per-window attack fraction averaging 30 %.

| Dir / file | What it is |
|------------|------------|
| `perpacket/` | **The per-packet CNN detector that passes the NATWORK KPIs** (`model.json` + `run.weights.h5` + params/history/split). ~38 K params. |
| `run003_retrained/` | The shipped global-window architecture retrained on the same data, kept as a baseline. |
| `comparison.csv` | Accuracy, benign/DDoS P/R/F1, and FP/FN rates for shipped vs. retrained vs. per-packet on an identical 60,000-window held-out split. |

**Not committed** (regenerate — see `../../REPRODUCE.md`): `mixed_masked.h5` (the 2.7 GB
composed windowed dataset) and `*.pool.h5` temporaries.

## KPI result (held-out split)

| Model | FP rate | FN rate | NATWORK FP<1 % & FN<1 % |
|-------|--------:|--------:|:----------------------:|
| shipped `run003` | 55.7 % | 36.7 % | ❌ |
| `run003` retrained | 38.0 % | 62.0 % | ❌ |
| **`perpacket`** | **0.0001 %** | **0.009 %** | ✅ |

## Loading the model

The model is available two ways:

* **unzipped** here in `perpacket/` (loadable directly), and
* **packaged** as `../best_run_perpacket.zip`, mirroring the original `../best_run.zip`
  layout exactly: it unzips to `run_perpacket/` with `model.json`, `run.weights.h5`,
  `parameters.json`, `history.json`, `classification_report.json` and
  `confusion_matrix.npy`.

```bash
# same workflow as the shipped best_run.zip
unzip ../best_run_perpacket.zip -d /tmp/pp
.venv/bin/python ../classify_h5.py -i <windowed.h5> -m /tmp/pp/run_perpacket
```

```python
import tensorflow as tf
m = tf.keras.models.model_from_json(open("perpacket/model.json").read())
m.load_weights("perpacket/run.weights.h5")
# input (N,100,64,1) float32; output (N,100) per-packet DDoS score in [0,1]
```
