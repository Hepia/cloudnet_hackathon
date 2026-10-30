#!/bin/bash
# generate_m.sh <target_GB> <chunk_s>  — reliable single-pass concurrent capture using only
# the stable "normal" chunk (benign -b 400M + flood => ~30% attack) on the PATCHED lab.
# Accumulates into datasets/pcap_big until the WHOLE directory reaches <target_GB>.
# Gentle recovery: one lab reset after 2 consecutive wedged chunks; stop after 3 resets.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE/../infrastructure"
TARGET_GB=${1:-15}; CHUNK=${2:-60}; OUT="$HERE/pcap_big"; mkdir -p "$OUT"
UP=/tmp/claude-1000/-home-eryk-cloudnet-hackathon/e1355f62-9722-4021-a4c4-e4900d68af69/scratchpad/gm_up.log
dir_gb(){ echo "scale=3; $(du -sb "$OUT" | cut -f1)/1073741824" | bc; }
wait_bot(){ for _ in $(seq 1 60); do docker exec custom-client sh -c 'ss -nt 2>/dev/null|grep -q ":23 "' && { sleep 2; return 0; }; sleep 3; done; return 1; }
lab_reset(){ echo "  -- lab reset --"; timeout 100 ./lab.sh down >/dev/null 2>&1; nohup ./lab.sh up >"$UP" 2>&1 & local t0; t0=$(date +%s); while [ $(( $(date +%s)-t0 )) -lt 200 ]; do grep -q "UE has PDU session" "$UP" 2>/dev/null && break; sleep 4; done; wait_bot; sleep 3; }
chunk(){ local n=$1
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b 400M -t "$CHUNK" -l 256
  docker exec -d http-client  bash -c 'http-get all -n 6 >/dev/null 2>&1'
  docker exec -d mqtt-client  bash -c 'mqtt-run -i 0.01 -n 6000 >/dev/null 2>&1'
  docker exec -d video-client bash -c 'e=$(( $(date +%s)+'"$CHUNK"' )); while [ "$(date +%s)" -lt "$e" ]; do video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 & video-play high -t 7 >/dev/null 2>&1 & wait; done'
  docker exec -d custom-client custom-run -t "$CHUNK" -i 1 -d "$CHUNK"
  sleep $(( CHUNK + 3 )); ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap|head -1)
  local dest="$OUT/big-ddos-m$(printf '%03d' "$n")-$(date +%H%M%S)-clients.pcap"; mv "$c" "$dest"; rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  local atk; atk=$(tcpdump -r "$dest" -nn 'host 10.45.0.2' 2>/dev/null|wc -l); local tot; tot=$(tcpdump -r "$dest" -nn 2>/dev/null|wc -l)
  printf 'chunk %03d %6.1fMB total=%8d attack=%8d (%4.1f%%) dir=%.2fGB\n' "$n" "$(echo "$(stat -c %s "$dest")/1048576"|bc -l)" "$tot" "$atk" "$(echo "if($tot>0)100*$atk/$tot else 0"|bc -l)" "$(dir_gb)" >&2
  echo "$atk"
}
wait_bot || lab_reset
n=1; cfail=0; resets=0
while [ "$(echo "$(dir_gb) < $TARGET_GB"|bc)" -eq 1 ]; do
  a=$(chunk "$n"); n=$((n+1))
  if [ "$a" -lt 100000 ]; then cfail=$((cfail+1)); echo "  wedged chunk ($cfail consec)"
    if [ "$cfail" -ge 2 ]; then resets=$((resets+1)); [ "$resets" -gt 3 ] && { echo "too many resets, stopping"; break; }; lab_reset; cfail=0; fi
  else cfail=0; fi
done
echo "== done: dir=$(dir_gb)GB, $(ls "$OUT"/*.pcap|wc -l) files, $resets resets =="
