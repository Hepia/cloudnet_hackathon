import json
import os

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# ---------------------------------------------------
# Configuration
# ---------------------------------------------------

RESULTS_FILE = "/home/yoda/PycharmProjects/ddos/hyperparameter_results/quantization_results.json"
OUTPUT_DIR = "figures_Q"

os.makedirs(OUTPUT_DIR, exist_ok=True)

sns.set_theme(
    style="ticks",
    context="paper",
    palette="viridis",
)

plt.rcParams.update({
    "figure.figsize": (8, 5),
    "figure.dpi": 140,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7,
    "legend.title_fontsize": 8,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
})
with open(RESULTS_FILE) as f:
    data = json.load(f)

df = pd.DataFrame(data)

# Convert bytes to MB
df["model_size_mb"] = df["model_size_bytes"] / (1024 * 1024)

# ---------------------------------------------------
# 1. Model size by quantization
# ---------------------------------------------------

plt.figure(figsize=(8,6))

sns.boxplot(
    data=df,
    x="quantization",
    y="model_size_mb",
    palette="Blues"
)

sns.stripplot(
    data=df,
    x="quantization",
    y="model_size_mb",
    color="black",
    alpha=0.6
)

plt.xlabel("Quantization")
plt.ylabel("Model Size (MB)")
plt.title("Model Size After Quantization")

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/model_size.png", dpi=300)
plt.close()

# ---------------------------------------------------
# 2. F1 score by quantization
# ---------------------------------------------------

plt.figure(figsize=(8,6))

sns.boxplot(
    data=df,
    x="quantization",
    y="f1",
    palette="Blues"
)

sns.stripplot(
    data=df,
    x="quantization",
    y="f1",
    color="black",
    alpha=0.5
)

plt.ylabel("Macro F1")
plt.xlabel("Quantization")
plt.title("Classification Performance")

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/f1.png", dpi=300)
plt.close()

# ---------------------------------------------------
# 3. Precision vs Recall
# ---------------------------------------------------

plt.figure(figsize=(7,7))

sns.scatterplot(
    data=df,
    x="precision",
    y="recall",
    hue="quantization",
    style="quantization",
    s=120
)

plt.title("Precision vs Recall")

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/precision_recall.png", dpi=300)
plt.close()

# ---------------------------------------------------
# 4. Model size vs F1
# ---------------------------------------------------

plt.figure(figsize=(8,6))

sns.scatterplot(
    data=df,
    x="model_size_mb",
    y="f1",
    hue="quantization",
    style="quantization",
    s=120
)

plt.xlabel("Model Size (MB)")
plt.ylabel("Macro F1")
plt.title("Accuracy vs Model Size")

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/size_vs_f1.png", dpi=300)
plt.close()

# ---------------------------------------------------
# 5. Architecture heatmap
# ---------------------------------------------------

pivot = df.pivot_table(
    values="f1",
    index=["filters1", "filters2"],
    columns="quantization",
    aggfunc="mean"
)

plt.figure(figsize=(7,5))

sns.heatmap(
    pivot,
    annot=True,
    fmt=".3f",
    cmap="viridis"
)

plt.title("Average F1 by CNN Architecture")

plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/architecture_heatmap.png", dpi=300)
plt.close()

# ---------------------------------------------------
# 6. Hyperparameter influence
# ---------------------------------------------------

g = sns.catplot(
    data=df,
    x="dense",
    y="f1",
    hue="quantization",
    col="batch_size",
    row="epochs",
    kind="box",
    height=4
)

g.fig.subplots_adjust(top=0.9)
g.fig.suptitle("Effect of Dense Layer Size")

g.savefig(f"{OUTPUT_DIR}/hyperparameters.png", dpi=300)

print("Plots saved to:", OUTPUT_DIR)