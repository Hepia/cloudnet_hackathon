#!/usr/bin/env python3

"""
Convert PCAP files into an HDF5 dataset of labeled packets.

Each packet is converted into a fixed-length byte array. A packet is labeled
as DDoS (1) if:
  - its PCAP filename contains the specified DDoS filename string, and
  - it contains the specified target IP address.

Otherwise it is labeled as benign (0).

Example:
    python convert_pcap_to_h5.py \
        --input /path/to/pcaps \
        --output tf_dataset/tf_dataset_pckt.h5 \
        --packet-length 64 \
        --target-ip 192.168.20.187 \
        --ddos-name wifi-ddos
"""

import argparse
from pathlib import Path

import h5py
import numpy as np
from scapy.all import rdpcap
from scapy.layers.inet import IP


def parse_args():
    parser = argparse.ArgumentParser(description="Convert PCAP files into an HDF5 packet dataset.")

    parser.add_argument("-i", "--input", type=Path, required=True, help="Directory containing PCAP files.")
    parser.add_argument("-o", "--output",type=Path, required=True, help="Output HDF5 file.")
    parser.add_argument("-p", "--packet-length", type=int, default=64,
                        help="Packet length after truncation/padding (default: 64).")
    parser.add_argument("--target-ip", default="192.168.20.187",
                        help="Target IP address used to identify DDoS packets.")
    parser.add_argument("--ddos-name", default="wifi-ddos", help="Substring identifying DDoS PCAP filenames.")
    return parser.parse_args()


def process_pcap(pcap_path, packet_length, target_ip, ddos_name):
    packets = rdpcap(str(pcap_path))

    packet_array = []
    labels = []

    for pkt in packets:
        found = False

        if ddos_name in str(pcap_path):
            for ip in (
                pkt.getlayer(IP, nb=0),
                pkt.getlayer(IP, nb=1),
                pkt.getlayer(IP, nb=2),
            ):
                if ip and (ip.src == target_ip or ip.dst == target_ip):
                    found = True

        labels.append(int(found))
        arr = np.frombuffer(bytes(pkt), dtype=np.uint8)

        if len(arr) < packet_length:
            arr = np.pad(arr, (0, packet_length - len(arr)))
        else:
            arr = arr[:packet_length]

        packet_array.append(arr)

    print(f"Packets 0/1: {len(labels) - sum(labels)}/{sum(labels)}")

    return packet_array, labels

def build_dataset(input_dir, packet_length, target_ip, ddos_name):
    X = []
    y = []

    for pcap_file in sorted(input_dir.glob("*.pcap")):
        print(f"Processing {pcap_file}")

        packets, labels = process_pcap(pcap_file, packet_length, target_ip, ddos_name)

        X.extend(packets)
        y.extend(labels)

    return (np.asarray(X, dtype=np.uint8), np.asarray(y, dtype=np.int32))


def main():
    args = parse_args()

    X, y = build_dataset(args.input, args.packet_length,args.target_ip, args.ddos_name)

    with h5py.File(args.output, "w") as h5f:
        h5f.create_dataset("X", data=X)
        h5f.create_dataset("y", data=y)

    print(f"Dataset saved to {args.output}")
    print(f"Total packets : {len(y)}")
    print(f"Benign        : {(y == 0).sum()}")
    print(f"DDoS          : {(y == 1).sum()}")

if __name__ == "__main__":
    main()