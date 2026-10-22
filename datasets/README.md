# 6G-DALI / NATWORK hackathon — mixed benign + Mirai DDoS datasets

Three packet captures generated in the `infrastructure/` lab5g environment, each mixing
normal application traffic with a Mirai SYN-flood DDoS attack. They are meant to be fed to
the `ddos_cnn_xgb/` detector (and any other participant model) as labelled train/test data.

All traffic was produced inside the self-contained lab (no route to the outside). Benign
traffic comes from the client containers on `10.10.2.0/24`; the attack is a Mirai SYN flood
launched from the UE (`10.45.0.2`) through the 5G user plane. Both were captured together on
the router, headers only (tcpdump snaplen 128).

## Files

`pcap/lab5g-mixed-ddos-ds{1,2,3}-clients.pcap` — the router clients-side interface, which
sees both the client network and the UE, so each file contains the complete benign + attack
mix. (The router servers-side capture is a byte-for-byte redundant view and is not shipped.)

## Label rule

A packet is **DDoS (1)** iff its source or destination IP is the UE `10.45.0.2`, otherwise
**benign (0)**. This is exact because benign traffic is only ever generated from the client
containers (`10.10.2.x`) and the attack only ever from the UE. For `ddos_cnn_xgb`:

```
python convert_pcap_to_h5.py -i datasets/pcap -o tf_dataset/mixed_pckt.h5 \
    -p 64 --target-ip 10.45.0.2 --ddos-name ddos
python split_h5_into_windows.py -i tf_dataset/mixed_pckt.h5 \
    -o tf_dataset/mixed_masked.h5 -w 100 -p 64
python classify_h5.py -i tf_dataset/mixed_masked.h5 -m best_run/run_003
```

The filenames contain `ddos`, which the converter uses together with `--target-ip` to apply
the label above.

## Composition (packets, clients-side capture)

| Dataset | Total | Attack (10.45.0.2) | Benign | Size | Attack % |
| --- | --- | --- | --- | --- | --- |
| ds1 | 499,373 | 207,220 | 292,153 | 54.9 MB | 41% |
| ds2 | 657,875 | 342,007 | 315,868 | 68.5 MB | 52% |
| ds3 | 411,267 | 183,245 | 228,022 | 44.3 MB | 45% |

Benign protocol mix per file (approximate packet counts):

| | HTTP (80) | MQTT (1883) | iperf3 UDP (5201) | RTP video (from .30) |
| --- | --- | --- | --- | --- |
| ds1 | 13,057 | 14,018 | 252,097 | 12,694 |
| ds2 | 13,884 | 14,020 | 275,014 | 12,667 |
| ds3 | 13,521 | 13,930 | 187,512 | 12,772 |

The bulk iperf3 UDP stream provides benign volume (so the dataset is not dominated by the
flood); HTTP, MQTT and RTP video provide protocol diversity. The attack portion is the Mirai
SYN flood (TCP SYN, win 0, randomized ports to `10.10.1.50`) plus the RST/SYN-ACK responses
it draws back toward the UE.

## Verification

Labelling was checked by converting ds1 and comparing against an independent `tcpdump`
count: the converter reported 292,153 benign / 207,220 DDoS, matching exactly. Running the
shipped CNN (`best_run/run_003`) over the windowed, masked ds1 gives a meaningful score on
balanced data (a pure-attack capture would trivially read 100%):

| Metric | benign | DDoS |
| --- | --- | --- |
| precision | 0.997 | 0.785 |
| recall | 0.807 | 0.996 |
| f1 | 0.892 | 0.878 |

Overall accuracy 0.885. The model catches almost every attack packet (recall 0.996) and
mislabels ~19% of benign as attack, so these datasets are useful for improving precision.

## Regeneration

With the lab up (`cd infrastructure && ./lab.sh up`), from `datasets/`:

```
./generate_dataset.sh ds1 2 110M 22     # ~55 MB, 41% attack
./generate_dataset.sh ds2 3 120M 22     # ~68 MB, 52% attack
./generate_dataset.sh ds3 2  90M 20     # ~44 MB, 45% attack
```

Arguments: `<label> <flood_seconds> <iperf_mbit> <window_seconds>`. The flood runs at the
bot's full rate (~60k SYN/s as seen at the router), so flood seconds is the main attack-volume
knob; iperf bitrate and window are the benign-volume knobs.
