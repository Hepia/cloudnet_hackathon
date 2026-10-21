"""
Add labels to a csv files in the catalogue. Labels are added based on source or destination IP
"""
import pandas as pd
from pathlib import Path

input_dir = Path("/mnt/natwork/nas/data/anna.padee/ddos/data/csv/Bening")

target_ip = "192.168.20.187"

new_label = ("Syn")

for csv_file in input_dir.glob("*.csv"):
    df = pd.read_csv(csv_file)
    df["Label"] = "Benign"
    mask = (
        (df["Src IP"] == target_ip) |
        (df["Dst IP"] == target_ip)
    )

    df.loc[mask, "Label"] = new_label

    df.to_csv(csv_file, index=False)

    print(f"Processed {csv_file.name}: {mask.sum()} rows updated.")