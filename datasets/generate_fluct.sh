#!/bin/bash
# generate_fluct.sh <prefix> <target_GB> <chunk_s> <avg_attack_frac>
#
# Generates a large, real-world-like DDoS dataset whose attack share FLUCTUATES
# (chunks range from ~0% to flood-heavy) but AVERAGES ~<avg_attack_frac> overall.
#
# Two chunk types, chosen adaptively to steer the cumulative attack fraction toward
# the target (DDoS traffic realistically comes in waves):
#   FLOOD  chunk: light benign + Mirai SYN flood from the UE  -> attack-dominated
#   BENIGN chunk: heavy benign mix, no flood                  -> ~0% attack
# Before every FLOOD chunk a short probe checks the flood actually reaches the router
# (the UE 5G tunnel / Mirai bot are flaky) and recovers (restart bot, then UE+gNB) if
# not. Captures land in datasets/pcap_big/. Run from infrastructure/ with the lab up.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE/../infrastructure"

PREFIX=${1:-big}
TARGET_GB=${2:-15}
CHUNK=${3:-40}
TARGET_FRAC=${4:-0.30}
OUT="$HERE/pcap_big"; mkdir -p "$OUT"
TARGET_BYTES=$(echo "$TARGET_GB * 1073741824" | bc)
DEADLINE=$(( $(date +%s) + 4500 ))   # wall-clock safety cap (75 min)

atk_count() { tcpdump -r "$1" -nn 'host 10.45.0.2' 2>/dev/null | wc -l; }
tot_count() { tcpdump -r "$1" -nn 2>/dev/null | wc -l; }

probe() {
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  docker exec -d custom-client custom-run -t 4 -i 1 -d 4
  sleep 5; ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap|head -1)
  local a; a=$(atk_count "$c"); rm -f "$c" "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  echo "$a"
}
ensure_attack() {
  local a; a=$(probe); [ "$a" -ge 2000 ] && { echo "    probe ok ($a)"; return 0; }
  echo "    probe low ($a) -> restart custom-client"; docker restart custom-client >/dev/null 2>&1; sleep 12
  a=$(probe); [ "$a" -ge 2000 ] && { echo "    recovered ($a)"; return 0; }
  echo "    still low ($a) -> restart gnb+ue+custom-client"
  docker restart gnb >/dev/null 2>&1; sleep 3; docker restart ue >/dev/null 2>&1; sleep 8
  docker restart custom-client >/dev/null 2>&1; sleep 12
  a=$(probe); echo "    after full recovery ($a)"; [ "$a" -ge 2000 ]
}

start_benign() {  # start_benign <iperf_mbit> <datagram>
  docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b "$1" -t "$CHUNK" -l "$2"
  docker exec -d http-client  bash -c 'http-get all -n 6 >/dev/null 2>&1'
  docker exec -d mqtt-client  bash -c 'mqtt-run -i 0.01 -n 4000 >/dev/null 2>&1'
  docker exec -d video-client bash -c '
    end=$(( $(date +%s) + '"$CHUNK"' ))
    while [ "$(date +%s)" -lt "$end" ]; do
      video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 &
      video-play high -t 7 >/dev/null 2>&1 & wait
    done'
}

chunk() {  # chunk <n> <type>; echo "<dest> <total> <attack>"
  local n=$1 type=$2
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  if [ "$type" = flood ]; then
    start_benign 120M 512                        # light benign so the flood is not CPU-starved
    docker exec -d custom-client custom-run -t "$CHUNK" -i 1 -d "$CHUNK"
  else
    start_benign 900M 256                         # heavy benign, no flood
  fi
  sleep $(( CHUNK + 3 )); ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap|head -1)
  local dest="$OUT/${PREFIX}-ddos-${type}-c$(printf '%02d' "$n")-clients.pcap"
  mv "$c" "$dest"; rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  echo "$dest $(tot_count "$dest") $(atk_count "$dest")"
}

echo "== target ${TARGET_GB}GB, chunk ${CHUNK}s, avg attack ~${TARGET_FRAC} =="
cum=0; cumA=0; cumT=0; n=1
while [ "$(echo "$cum < $TARGET_BYTES" | bc)" -eq 1 ] && [ "$(date +%s)" -lt "$DEADLINE" ]; do
  # steer: below target average -> flood chunk, else benign chunk
  frac=$(echo "scale=4; if ($cumT>0) $cumA/$cumT else 0" | bc -l)
  if [ "$(echo "$frac < $TARGET_FRAC" | bc -l)" -eq 1 ]; then type=flood; else type=benign; fi
  [ "$type" = flood ] && { echo "chunk $n (flood): health check"; ensure_attack || { echo "  !! attack unrecoverable; switching to benign"; type=benign; }; }
  read dest tot atk < <(chunk "$n" "$type")
  sz=$(stat -c %s "$dest"); cum=$(echo "$cum + $sz"|bc); cumA=$((cumA+atk)); cumT=$((cumT+tot))
  printf 'chunk %02d %-6s %6.1fMB total=%8d attack=%8d (%5.1f%%)  running_avg=%5.1f%%  cum=%5.2fGB\n' \
    "$n" "$type" "$(echo "$sz/1048576"|bc -l)" "$tot" "$atk" \
    "$(echo "if($tot>0) 100*$atk/$tot else 0"|bc -l)" \
    "$(echo "scale=1; if($cumT>0) 100*$cumA/$cumT else 0"|bc -l)" \
    "$(echo "$cum/1073741824"|bc -l)"
  n=$((n+1))
done
echo "== done: $((n-1)) chunks, $(echo "scale=2;$cum/1073741824"|bc)GB, avg attack $(echo "scale=1; if($cumT>0) 100*$cumA/$cumT else 0"|bc -l)% in $OUT =="
