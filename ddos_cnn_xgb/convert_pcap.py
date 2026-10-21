"""Convert PCAP into h5 file with labeled packets. PCAP files should be in two catalogues Benign / DDoS"""

import os
from pathlib import Path
import h5py
import numpy as np
from scapy.all import rdpcap
from scapy.layers.inet import IP

PCAP_DIR = "/mnt/natwork/nas/data/anna.padee/ddos/data/pcap"
OUTPUT_DIR = "tf_dataset"

WIN_LENGTH = 64
target_ip = '192.168.20.187'
print(repr(target_ip))

def process_pcap(pcap_path):
    packets = rdpcap(str(pcap_path))
    packet_array = []
    labels = []

    for pkt in packets:
        found = False
        if "wifi-ddos" in str(pcap_path):
            for ip in pkt.getlayer(IP, nb=0), pkt.getlayer(IP, nb=1), pkt.getlayer(IP, nb=2):
                if ip and (ip.src == target_ip or ip.dst == target_ip):
                    found = True
        labels.append(int(found))

        raw_bytes = bytes(pkt)
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        if WIN_LENGTH > len(arr):
            arr = np.pad(arr, (0, WIN_LENGTH - len(arr)))
        else:
            arr = arr[:WIN_LENGTH]
        packet_array.append(arr)

    print("Packets 0/1: {}/{}".format(len(labels) - sum(labels), sum(labels)))
    return packet_array, labels


def build_dataset():
    X = []
    y = []

    class_names = sorted([d.name for d in Path(PCAP_DIR).iterdir() if d.is_dir()])

#    label_map = {
#        name: idx
#        for idx, name in enumerate(class_names)
#    }

    for class_name in class_names:
        class_dir = Path(PCAP_DIR) / class_name

        for pcap_file in class_dir.glob("*.pcap"):
            print(f"Processing {pcap_file}")

            images,labels = process_pcap(pcap_file)

            X.extend(images)
            y.extend(labels)

    X = np.array(X, dtype=np.uint8)
    y = np.array(y, dtype=np.int32)
    return X, y, class_names

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    X, y, classes = build_dataset()

    h5f = h5py.File(os.path.join(OUTPUT_DIR, "tf_dataset_pckt.h5"), "w")
    h5f.create_dataset("X", data=X)
    h5f.create_dataset("y", data=y)
    h5f.close()
    print("Dataset saved.")
