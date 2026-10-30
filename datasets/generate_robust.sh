#!/bin/bash
# generate_robust.sh <prefix> <target_GB> <chunk_s> <iperf_mbit> <datagram>
#
# Self-healing generator for the (unreliable) lab5g testbed. Produces a large,
# ~30%-attack, real-world-like dataset in datasets/pcap_big/.
#
# Each chunk runs the benign application mix (HTTP, MQTT, RTP video, iperf3 UDP) for
# <chunk_s> seconds concurrently with a Mirai SYN flood from the UE, and is captured
# on the router. Before every chunk a short probe checks that the flood actually
# reaches the router (the UE 5G tunnel / Mirai bot are flaky); if not, it recovers by
# restarting custom-client (fresh bot) and, if still dead, the UE + gNB. Only chunks
# whose attack share is sane are kept and counted toward the target.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE/../infrastructure"

PREFIX=${1:-big}
TARGET_GB=${2:-15}
CHUNK=${3:-70}
IPB=${4:-600M}
DGRAM=${5:-256}
OUT="$HERE/pcap_big"; mkdir -p "$OUT"
TARGET_BYTES=$(echo "$TARGET_GB * 1073741824" | bc)

atk_count() { tcpdump -r "$1" -nn 'host 10.45.0.2' 2>/dev/null | wc -l; }

probe_attack() {   # returns attack packet count of a short probe capture
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  docker exec -d custom-client custom-run -t 4 -i 1 -d 4
  sleep 5; ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap|head -1)
  local a; a=$(atk_count "$c")
  rm -f "$c" "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  echo "$a"
}

ensure_attack() {  # probe; if no attack, restart bot, then the whole UE path
  local a; a=$(probe_attack)
  if [ "$a" -ge 2000 ]; then echo "  probe ok ($a attack pkts)"; return 0; fi
  echo "  probe LOW ($a); restarting custom-client (fresh bot)..."
  docker restart custom-client >/dev/null 2>&1; sleep 12
  a=$(probe_attack)
  if [ "$a" -ge 2000 ]; then echo "  recovered after bot restart ($a)"; return 0; fi
  echo "  still low ($a); restarting ue + gnb + custom-client..."
  docker restart gnb >/dev/null 2>&1; sleep 3
  docker restart ue  >/dev/null 2>&1; sleep 8
  docker restart custom-client >/dev/null 2>&1; sleep 12
  a=$(probe_attack)
  echo "  after full recovery: $a attack pkts"
  [ "$a" -ge 2000 ]
}

chunk() {  # chunk <n>: capture CHUNK s of benign + flood; echo "<dest> <total> <attack>"
  local n=$1
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b "$IPB" -t "$CHUNK" -l "$DGRAM"
  docker exec -d http-client  bash -c 'http-get all -n 6 >/dev/null 2>&1'
  docker exec -d mqtt-client  bash -c 'mqtt-run -i 0.01 -n 4000 >/dev/null 2>&1'
  docker exec -d video-client bash -c '
    end=$(( $(date +%s) + '"$CHUNK"' ))
    while [ "$(date +%s)" -lt "$end" ]; do
      video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 &
      video-play high -t 7 >/dev/null 2>&1 & wait
    done'
  docker exec -d custom-client custom-run -t "$CHUNK" -i 1 -d "$CHUNK"
  sleep $(( CHUNK + 3 ))
  ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap|head -1)
  local dest="$OUT/${PREFIX}-ddos-c$(printf '%02d' "$n")-clients.pcap"
  mv "$c" "$dest"; rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  local a; a=$(atk_count "$dest"); local t; t=$(tcpdump -r "$dest" -nn 2>/dev/null|wc -l)
  echo "$dest $t $a"
}

echo "== target ${TARGET_GB}GB, chunk ${CHUNK}s, iperf ${IPB}/${DGRAM}B =="
cum=0; n=1; kept=0
while [ "$(echo "$cum < $TARGET_BYTES" | bc)" -eq 1 ]; do
  ensure_attack || { echo "  !! cannot restore attack; stopping at ${cum} bytes"; break; }
  read dest tot atk < <(chunk "$n")
  frac=$(echo "scale=3; $atk/$tot" | bc -l 2>/dev/null)
  sz=$(stat -c %s "$dest")
  keepok=$(echo "$atk >= 0.12*$tot && $atk <= 0.6*$tot" | bc -l 2>/dev/null)
  if [ "$keepok" = "1" ]; then
    cum=$(echo "$cum + $sz" | bc); kept=$((kept+1))
    printf 'chunk %02d KEEP %6.1fMB total=%8d attack=%8d (%.1f%%) cum=%5.2fGB\n' \
      "$n" "$(echo "$sz/1048576"|bc -l)" "$tot" "$atk" "$(echo "100*$frac"|bc -l)" \
      "$(echo "$cum/1073741824"|bc -l)"
  else
    printf 'chunk %02d DROP (attack %.1f%% out of range) total=%d attack=%d\n' \
      "$n" "$(echo "100*$frac"|bc -l)" "$tot" "$atk"
    rm -f "$dest"
  fi
  n=$((n+1))
done
echo "== done: kept $kept chunks, $(echo "scale=2;$cum/1073741824"|bc)GB in $OUT =="
