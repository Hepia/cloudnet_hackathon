#!/bin/bash
# generate_dataset.sh <label> <flood_seconds> <iperf_mbit> <window_seconds>
#
# Produces one labelled DDoS dataset capture on the lab5g router. Benign traffic
# (HTTP, MQTT, RTP video, bulk iperf3 UDP) is generated from the client network
# (source 10.10.2.x); a Mirai SYN flood is launched from the UE through the 5G
# user plane (source 10.45.0.2). Both are captured together on the router.
#
# Label rule: a packet is DDoS iff its source or destination is the UE (10.45.0.2);
# everything else is benign. Benign is only ever sourced from the client containers
# and the attack only ever from the UE, so this split is exact.
#
# Run from infrastructure/ with the lab up (./lab.sh up). Output pcap lands in
# infrastructure/captures/ ; copy the clients-side file into datasets/pcap/.
#
# Examples (the three shipped datasets):
#   ./generate_dataset.sh ds1 2 110M 22     # ~55 MB, 41% attack
#   ./generate_dataset.sh ds2 3 120M 22     # ~68 MB, 52% attack
#   ./generate_dataset.sh ds3 2  90M 20     # ~44 MB, 45% attack
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE/../infrastructure"
LABEL=${1:-cap}; FLOOD=${2:-2}; IPB=${3:-110M}; WIN=${4:-22}

echo "== [$LABEL] start router capture (snaplen 128) =="
./lab.sh pcap start router >/dev/null 2>&1
sleep 1

echo "== [$LABEL] benign from client network: iperf UDP ${IPB}/${WIN}s, http, video(3x parallel), mqtt =="
docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b "$IPB" -t "$WIN" -l 1200
docker exec -d http-client  bash -c 'http-get all -n 4 >/dev/null 2>&1'
docker exec -d mqtt-client  mqtt-run -i 0.02 -n 1000 >/dev/null 2>&1
docker exec -d video-client bash -c '
  end=$(( $(date +%s) + '"$WIN"' ))
  while [ "$(date +%s)" -lt "$end" ]; do
    video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 &
    video-play high -t 7 >/dev/null 2>&1 & wait
  done'

sleep 9
echo "== [$LABEL] Mirai SYN flood from UE (10.45.0.2), ${FLOOD}s =="
docker exec custom-client custom-run -t "$FLOOD" -i 1 -d "$FLOOD" 2>&1 | grep -E 'syn|requests'

sleep $(( WIN - 9 + 5 ))
echo "== [$LABEL] stop capture =="
./lab.sh pcap stop router >/dev/null 2>&1

C=$(ls -t captures/router-clients-*.pcap | head -1)
tot=$(tcpdump -r "$C" -nn 2>/dev/null | wc -l)
atk=$(tcpdump -r "$C" -nn 'host 10.45.0.2' 2>/dev/null | wc -l)
printf '[%s] %s  packets=%d attack=%d benign=%d size=%.1fMB (attack %.0f%%)\n' \
  "$LABEL" "$(basename "$C")" "$tot" "$atk" "$((tot-atk))" \
  "$(echo "$(stat -c %s "$C")/1048576"|bc -l)" "$(echo "100*$atk/$tot"|bc -l)"
echo "Copy to the dataset with:"
echo "  cp $C ../datasets/pcap/lab5g-mixed-ddos-$LABEL-clients.pcap"