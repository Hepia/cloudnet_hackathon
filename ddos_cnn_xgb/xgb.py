"""
Train xgboost
"""
import numpy as np
import pandas as pd
from xgboost import XGBClassifier, plot_tree
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from sklearn.preprocessing import LabelEncoder
import matplotlib.pyplot as plt
from pathlib import Path
import seaborn as sns
from datetime import timedelta

from sklearn.model_selection import train_test_split
import re

plt.rcParams.update({
    "figure.figsize": (8, 5),
    "figure.dpi": 140,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7,
    "legend.title_fontsize": 8,
    "font.size": 20,
#    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.bottom": False,
    "axes.spines.left": False
})

data_dir = Path("/mnt/natwork/nas/data/anna.padee/ddos/cicflowmeter/data/output/csv")
data_dir = Path("/mnt/natwork/nas/data/anna.padee/ddos/data/csv/Bening")

df_agg = None
for data_file in data_dir.glob("*.csv"):
    df = pd.read_csv(data_file)
    if df_agg is None:
        df_agg = df
    else:
        df_agg = pd.concat((df_agg, df), ignore_index=True)

mask = ((df_agg["Label"] == 'Benign'))

df_agg.loc[mask, "Label"] = "0"
df_agg.loc[~mask, "Label"] = "1"


y = df_agg['Label'].to_numpy().astype(int)
df_agg.drop('Label', axis=1, inplace=True)
df_agg.drop('Flow ID', axis=1, inplace=True)
df_agg.drop('Src IP', axis=1, inplace=True)
df_agg.drop('Src Port', axis=1, inplace=True)
df_agg.drop('Dst IP', axis=1, inplace=True)
df_agg.drop('Dst Port', axis=1, inplace=True)
df_agg.drop('Timestamp', axis=1, inplace=True)
df_agg.dropna()
X = df_agg

X = df_agg
X = X.replace([np.inf, -np.inf], np.nan)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.5, random_state=42)

xgb_model = XGBClassifier(n_estimators=100, learning_rate=0.1, random_state=42)

xgb_model.fit(X_train, y_train)
y_pred = xgb_model.predict(X_test)


accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred, average='weighted')
recall = recall_score(y_test, y_pred, average='weighted')
f1 = f1_score(y_test, y_pred, average='weighted')

print(f"Accuracy: {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall: {recall:.4f}")
print(f"F1-score: {f1:.4f}")

cm = confusion_matrix(y_test, y_pred)

sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=["Benign","DDoS"], yticklabels=["Benign","DDoS"])
plt.xlabel('Predicted Labels')
plt.ylabel('True Labels')
plt.title('Confusion Matrix')
plt.savefig("cm.png")
plt.show()

label_encoder = LabelEncoder()
label_encoder.fit(["Bening", "DDoS"])
y_test_labels = label_encoder.inverse_transform(y_test)
y_pred_labels = label_encoder.inverse_transform(y_pred)

ConfusionMatrixDisplay.from_estimator(
    xgb_model, X_test, y_test, display_labels=label_encoder.inverse_transform(np.unique(y_pred)), xticks_rotation="vertical", cmap='Blues'
)
plt.tight_layout()
plt.show()
cm = confusion_matrix(y_test_labels, y_pred_labels)
