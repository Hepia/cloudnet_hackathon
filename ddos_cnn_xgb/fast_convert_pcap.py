#!/usr/bin/env python3
"""
Streaming PCAP -> HDF5 converter (memory-safe replacement for convert_pcap_to_h5.py).

Produces the SAME output format and label rule as convert_pcap_to_h5.py:
  X : uint8 [num_packets, packet_length]   (first `packet_length` bytes, zero-padded)
  y : int32 [num_packets]                  (1 = DDoS, 0 = benign)

Label rule (identical to the shipped converter):
  a packet is DDoS (1) iff  `--ddos-name` is a substring of the pcap filename
  AND the IPv4 source or destination address equals `--target-ip`.

Unlike the shipped converter it never calls scapy rdpcap (which loads the whole
capture into RAM); it mmaps the classic-pcap file and parses record headers
directly, appending to resizable HDF5 datasets in chunks. This scales to many GB.

Supported link types: EN10MB (1, Ethernet II) and LINUX_SLL (113).
Supported pcap magics: usec/nsec, little- and big-endian. (pcapng is not classic
pcap; tcpdump -w writes classic pcap, which is what the lab uses.)
"""
import argparse
import mmap
import struct
from pathlib import Path

import h5py
import numpy as np


def ip_to_bytes(ip):
    return bytes(int(o) for o in ip.split("."))


def parse_global_header(mm):
    magic = mm[:4]
    # magic is the native-endian image of 0xA1B2C3D4 (or 0xA1B23C4D for nanosecond):
    # bytes A1 B2 C3 D4 on disk -> big-endian file; D4 C3 B2 A1 -> little-endian file.
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        raise ValueError(f"not a classic pcap file (magic {magic!r})")
    # global header is 24 bytes; network (link type) is the last u32
    network = struct.unpack(endian + "I", mm[20:24])[0]
    return endian, network


def ip_offsets(network):
    # byte offset of the IPv4 src address within the frame, and the ethertype offset
    if network == 1:          # EN10MB: 14-byte Ethernet header, ethertype at 12
        return 26, 12, 0x0800
    if network == 113:        # LINUX_SLL: 16-byte header, protocol at 14
        return 28, 14, 0x0800
    raise ValueError(f"unsupported link type {network}")


def convert_file(path, h5f, packet_length, target_ip, ddos_name, chunk):
    target = ip_to_bytes(target_ip)
    is_ddos_file = ddos_name in str(path)

    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            endian, network = parse_global_header(mm)
            src_off, eth_off, ip_ethertype = ip_offsets(network)
            rec_hdr = struct.Struct(endian + "IIII")
            size = len(mm)
            off = 24

            Xd = h5f["X"]
            yd = h5f["y"]

            Xbuf = np.zeros((chunk, packet_length), dtype=np.uint8)
            ybuf = np.zeros((chunk, ), dtype=np.int32)
            n = 0
            total = 0
            ddos = 0

            def flush(count):
                if count == 0:
                    return
                base = Xd.shape[0]
                Xd.resize(base + count, axis=0)
                yd.resize(base + count, axis=0)
                Xd[base:base + count] = Xbuf[:count]
                yd[base:base + count] = ybuf[:count]

            while off + 16 <= size:
                _, _, incl_len, _ = rec_hdr.unpack_from(mm, off)
                off += 16
                end = off + incl_len
                if end > size:
                    break
                take = incl_len if incl_len < packet_length else packet_length
                row = Xbuf[n]
                row[:take] = np.frombuffer(mm, dtype=np.uint8, count=take, offset=off)
                if take < packet_length:
                    row[take:] = 0

                label = 0
                if is_ddos_file and incl_len >= src_off + 8:
                    ethertype = (mm[off + eth_off] << 8) | mm[off + eth_off + 1]
                    if ethertype == ip_ethertype:
                        src = mm[off + src_off:off + src_off + 4]
                        dst = mm[off + src_off + 4:off + src_off + 8]
                        if src == target or dst == target:
                            label = 1
                            ddos += 1
                ybuf[n] = label

                n += 1
                total += 1
                off = end
                if n == chunk:
                    flush(n)
                    n = 0
            flush(n)
            return total, ddos
        finally:
            mm.close()


def main():
    ap = argparse.ArgumentParser(description="Streaming PCAP -> HDF5 (memory-safe).")
    ap.add_argument("-i", "--input", type=Path, required=True,
                    help="PCAP file or directory of .pcap files.")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output HDF5 file.")
    ap.add_argument("-p", "--packet-length", type=int, default=64)
    ap.add_argument("--target-ip", default="10.45.0.2")
    ap.add_argument("--ddos-name", default="ddos")
    ap.add_argument("--chunk", type=int, default=1_000_000, help="Packets buffered per flush.")
    args = ap.parse_args()

    if args.input.is_dir():
        files = sorted(args.input.glob("*.pcap"))
    else:
        files = [args.input]
    if not files:
        raise SystemExit(f"no pcap files under {args.input}")

    with h5py.File(args.output, "w") as h5f:
        h5f.create_dataset("X", shape=(0, args.packet_length), maxshape=(None, args.packet_length),
                           dtype=np.uint8, chunks=(args.chunk, args.packet_length),
                           compression=None)
        h5f.create_dataset("y", shape=(0,), maxshape=(None,), dtype=np.int32,
                           chunks=(args.chunk,))
        grand_total = grand_ddos = 0
        for f in files:
            total, ddos = convert_file(f, h5f, args.packet_length, args.target_ip,
                                       args.ddos_name, args.chunk)
            print(f"{f.name}: packets={total} ddos={ddos} benign={total - ddos}", flush=True)
            grand_total += total
            grand_ddos += ddos
        h5f.attrs["target_ip"] = args.target_ip
        h5f.attrs["packet_length"] = args.packet_length

    print(f"TOTAL packets={grand_total} ddos={grand_ddos} benign={grand_total - grand_ddos} "
          f"({100.0 * grand_ddos / max(grand_total, 1):.1f}% attack)")
    print(f"saved {args.output}")


if __name__ == "__main__":
    main()
