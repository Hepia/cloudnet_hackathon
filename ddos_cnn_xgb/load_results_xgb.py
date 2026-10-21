"""Load pre-trained model and perform classification on a dataset"""

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, plot_tree
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.metrics import confusion_matrix, classification_report, ConfusionMatrixDisplay
import matplotlib.pyplot as plt
from pathlib import Path
import seaborn as sns
from datetime import timedelta
from sklearn.model_selection import train_test_split
import re
import joblib

model_dir= Path("/mnt/natwork/nas/data/anna.padee/ddos/xgboost_ddos/data/models")
model_path = model_dir / "xgboost_model.pkl"
encoder_path = model_dir / "label_encoder.pkl"
label_encoder = joblib.load(encoder_path)
model = joblib.load(model_path)

data_dir = Path("/mnt/natwork/nas/data/anna.padee/ddos/data/csv/Bening")

df_agg = None
for csv_file in data_dir.glob("*.csv"):
    df = pd.read_csv(csv_file)
    if df_agg is None:
        df_agg = df
    else:
        df_agg = pd.concat((df_agg, df), ignore_index=True)


mask = ((df_agg["Label"] == 'Benign'))

df_agg.loc[mask, "Label"] = "0"
df_agg.loc[~mask, "Label"] = str(label_encoder.transform(['Syn'])[0])


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
X = X.replace([np.inf, -np.inf], np.nan)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.5, random_state=42)

xgb_model = model

y_pred = xgb_model.predict(X_test)


accuracy = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred, average='weighted')
recall = recall_score(y_test, y_pred, average='weighted')
f1 = f1_score(y_test, y_pred, average='weighted')

print(f"Accuracy: {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall: {recall:.4f}")
print(f"F1-score: {f1:.4f}")


y_test_labels = label_encoder.inverse_transform(y_test)
y_pred_labels = label_encoder.inverse_transform(y_pred)

ConfusionMatrixDisplay.from_estimator(
    model, X_test, y_test, display_labels=label_encoder.inverse_transform(np.unique(y_pred)), xticks_rotation=30, cmap='Blues'
)
plt.tight_layout()
plt.show()
cm = confusion_matrix(y_test_labels, y_pred_labels)

sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
plt.xlabel('Predicted Labels')
plt.ylabel('True Labels')
plt.title('Confusion Matrix')
plt.savefig("cfmatrix.png")
plt.show()