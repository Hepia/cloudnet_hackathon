"""
Plot hyperparameter training results
"""


import json
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path

OUTPUT_DIR = Path("figures")
OUTPUT_DIR.mkdir(exist_ok=True)

sns.set_theme(
    style="ticks",
    context="paper",
    palette="viridis"
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

json_file = "hyperparameter_results2/summary1.json"

with open(json_file, "r") as f:
    data = json.load(f)

if isinstance(data, dict):
    data = [data]
df = pd.DataFrame(data)
print(df.describe())

corr = df.corr(numeric_only=True)

plt.figure(figsize=(10,8))

sns.heatmap(
    corr,
    cmap="RdBu_r",
    center=0,
    annot=True,
    fmt=".2f",
    annot_kws={"size":7},
    linewidths=.4,
    cbar_kws={"shrink":0.8}
)

plt.title("Correlation Matrix", fontsize=11)
plt.xticks(rotation=45, ha="right")
plt.yticks(rotation=0)
plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "correlation_heatmap.png",
    dpi=300,
    bbox_inches="tight",
)
plt.close()

hyperparams = [
    "filters1",
    "filters2",
    "dense",
    "learning_rate",
    "batch_size",
    "epochs",
    "dropout",
    "execution_time_seconds"
]

metric = "f1"

fig, axes = plt.subplots(3, 3, figsize=(18, 12))
axes = axes.flatten()

for ax, hp in zip(axes, hyperparams):
    sns.scatterplot(
        data=df,
        x=hp,
        y=metric,
        hue="best_val_loss",
        palette="viridis",
        s=120,
        ax=ax
    )

    sns.regplot(
        data=df,
        x=hp,
        y=metric,
        scatter=False,
        color="red",
        ax=ax
    )

    ax.set_title(f"{metric} vs {hp}")

for ax in axes[len(hyperparams):]:
    fig.delaxes(ax)

plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "scatter.png",
    dpi=600,
    bbox_inches="tight",
)
plt.close()

metrics = [
    "precision",
    "recall",
    "f1",
    "best_val_accuracy",
    "best_val_loss"
]

sns.pairplot(
    df[metrics],
    corner=True,
    diag_kind="kde",
    plot_kws=dict(s=60)
)

plt.savefig(
    OUTPUT_DIR / "pairplot.png",
    dpi=600,
    bbox_inches="tight",
)
plt.close()

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

sns.boxplot(y=df["precision"], ax=axes[0, 0])
axes[0, 0].set_title("Precision")

sns.boxplot(y=df["recall"], ax=axes[0, 1])
axes[0, 1].set_title("Recall")

sns.boxplot(y=df["f1"], ax=axes[1, 0])
axes[1, 0].set_title("F1 Score")

sns.boxplot(y=df["best_val_loss"], ax=axes[1, 1])
axes[1, 1].set_title("Validation Loss")

plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "f1_distr.png",
    dpi=600,
    bbox_inches="tight",
)
plt.close()

# ----------------------------------------------------
# Best Configuration
# ----------------------------------------------------
best = df.loc[df["best_val_accuracy"].idxmax()]

print("\nBest Hyperparameter Configuration")
print(best)


top = df.sort_values("best_val_accuracy", ascending=False).head(25)

plt.figure(figsize=(9,4))

sns.barplot(
    data=top,
    x=top.index.astype(str),
    y="best_val_accuracy",
    palette="viridis"
)

plt.xticks(rotation=60, fontsize=7)
plt.ylabel("Validation Accuracy")
plt.xlabel("Trial")
plt.title("Top 15 Models")

plt.tight_layout()
plt.savefig(
    OUTPUT_DIR / "top15.png",
    dpi=600,
    bbox_inches="tight",
)
plt.close()

best = df.loc[df["best_val_accuracy"].idxmax()]

plt.figure(figsize=(6,5))
plt.axis("off")

text = "\n".join(
    [f"{k:18s}: {v}" for k, v in best.items()]
)
