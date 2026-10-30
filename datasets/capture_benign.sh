#!/bin/bash
# capture_benign.sh <chunks> <chunk_s>  -- heavy benign only (no flood, no tunnel needed).
set -u
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE/../infrastructure"
CHUNKS=${1:-8}; CH=${2:-45}; OUT="$HERE/pcap_benign"; mkdir -p "$OUT"
for i in $(seq 1 "$CHUNKS"); do
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b 900M -t "$CH" -l 256
  docker exec -d http-client  bash -c 'http-get all -n 8 >/dev/null 2>&1'
  docker exec -d mqtt-client  bash -c 'mqtt-run -i 0.01 -n 5000 >/dev/null 2>&1'
  docker exec -d video-client bash -c 'e=$(( $(date +%s) + '"$CH"' )); while [ "$(date +%s)" -lt "$e" ]; do video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 & video-play high -t 7 >/dev/null 2>&1 & wait; done'
  sleep $(( CH + 3 )); ./lab.sh pcap stop router >/dev/null 2>&1
  c=$(ls -t captures/router-clients-*.pcap|head -1)
  dest="$OUT/benign-c$(printf '%02d' "$i")-clients.pcap"; mv "$c" "$dest"; rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  printf '  benign chunk %d: %.0fMB\n' "$i" "$(echo "$(stat -c %s "$dest")/1048576"|bc -l)"
done
echo "benign pool: $(ls "$OUT"/*.pcap|wc -l) files, $(du -sh "$OUT"|cut -f1)"
