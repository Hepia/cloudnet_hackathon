#!/bin/bash
# generate_big_dataset.sh <prefix> <target_GB> <window_s> <flood_s> <iperf_mbit> <datagram_bytes>
#
# Produces a large, real-world-like labelled DDoS dataset by running many capture
# rounds in the lab5g lab and accumulating the clients-side router captures into
# datasets/pcap_big/ until the cumulative size reaches <target_GB>.
#
# Each round runs the full benign application mix (HTTP, MQTT, RTP video, and a
# high-rate iperf3 UDP stream for bulk benign volume) for <window_s> seconds, and
# overlaps a Mirai SYN flood from the UE (10.45.0.2) for <flood_s> seconds. With the
# calibrated defaults (benign ~123k pps, attack ~72k pps) a 30 s window with a 22 s
# flood lands near 30% attack packets.
#
# Label rule (same as the shipped datasets): a packet is DDoS iff src or dst is the
# UE 10.45.0.2; everything else is benign. Run from infrastructure/ with the lab up.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE/../infrastructure"

PREFIX=${1:-big}
TARGET_GB=${2:-15}
WIN=${3:-30}
FLOOD=${4:-22}
IPB=${5:-900M}
DGRAM=${6:-256}

OUT="$HERE/pcap_big"
mkdir -p "$OUT"
TARGET_BYTES=$(echo "$TARGET_GB * 1073741824" | bc)

round() {  # round <n>: ~WIN s capture, benign for the whole window, flood spanning it
  local n=$1
  ./lab.sh pcap start router >/dev/null 2>&1
  sleep 1
  docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b "$IPB" -t "$WIN" -l "$DGRAM"
  docker exec -d http-client  bash -c 'http-get all -n 6 >/dev/null 2>&1'
  docker exec -d mqtt-client  bash -c 'mqtt-run -i 0.01 -n 3000 >/dev/null 2>&1'
  docker exec -d video-client bash -c '
    end=$(( $(date +%s) + '"$WIN"' ))
    while [ "$(date +%s)" -lt "$end" ]; do
      video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 &
      video-play high -t 7 >/dev/null 2>&1 & wait
    done'
  sleep 2
  docker exec -d custom-client custom-run -t "$FLOOD" -i 1 -d "$FLOOD" >/dev/null 2>&1
  sleep "$WIN"
  ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap | head -1)
  local dest="$OUT/${PREFIX}-ddos-r$(printf '%02d' "$n")-clients.pcap"
  mv "$c" "$dest"
  rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null | head -1)" 2>/dev/null
  echo "$dest"
}

echo "== target ${TARGET_GB}GB, window ${WIN}s, flood ${FLOOD}s, iperf ${IPB}/${DGRAM}B =="
cum=0; n=1
while [ "$(echo "$cum < $TARGET_BYTES" | bc)" -eq 1 ]; do
  f=$(round "$n")
  sz=$(stat -c %s "$f")
  cum=$(echo "$cum + $sz" | bc)
  printf 'round %02d: %-42s %6.1fMB  cum=%5.2fGB\n' \
    "$n" "$(basename "$f")" "$(echo "$sz/1048576"|bc -l)" "$(echo "$cum/1073741824"|bc -l)"
  n=$((n+1))
done
echo "== done: $((n-1)) rounds, $(echo "scale=2;$cum/1073741824"|bc)GB in $OUT =="
