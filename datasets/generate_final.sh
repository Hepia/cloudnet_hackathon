#!/bin/bash
# generate_final.sh <prefix> <target_GB> <chunk_s>
# Single-pass REAL concurrent capture on the PATCHED lab (nr-ue drops excess uplink, so the
# UE tunnel no longer wedges). Benign app mix + Mirai SYN flood run together and are captured
# on the router. The attack share FLUCTUATES across chunks (benign-only -> ~0%, normal -> ~30%,
# flood-heavy -> ~55%) but AVERAGES ~30%. Files land in datasets/pcap_big/. Run from
# infrastructure/ with the patched lab up and the bot connected.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE/../infrastructure"
PREFIX=${1:-big}; TARGET_GB=${2:-15}; CHUNK=${3:-60}
OUT="$HERE/pcap_big"; mkdir -p "$OUT"
TARGET_BYTES=$(echo "$TARGET_GB * 1073741824" | bc)

wait_bot(){ for _ in $(seq 1 60); do docker exec custom-client sh -c 'ss -nt 2>/dev/null|grep -q ":23 "' && return 0; sleep 3; done; return 1; }
lab_reset(){ echo "  -- lab reset --"; timeout 100 ./lab.sh down >/dev/null 2>&1; nohup ./lab.sh up >/tmp/claude-1000/-home-eryk-cloudnet-hackathon/e1355f62-9722-4021-a4c4-e4900d68af69/scratchpad/gf_up.log 2>&1 & local t0=$(date +%s); while [ $(( $(date +%s)-t0 )) -lt 200 ]; do grep -q "UE has PDU session" /tmp/claude-1000/-home-eryk-cloudnet-hackathon/e1355f62-9722-4021-a4c4-e4900d68af69/scratchpad/gf_up.log 2>/dev/null && break; sleep 4; done; wait_bot; }

benign(){ # benign <iperf_mbit> <datagram>
  docker exec -d http-client  iperf3 -c 10.10.1.40 -u -b "$1" -t "$CHUNK" -l "$2"
  docker exec -d http-client  bash -c 'http-get all -n 6 >/dev/null 2>&1'
  docker exec -d mqtt-client  bash -c 'mqtt-run -i 0.01 -n 6000 >/dev/null 2>&1'
  docker exec -d video-client bash -c 'e=$(( $(date +%s)+'"$CHUNK"' )); while [ "$(date +%s)" -lt "$e" ]; do video-play low -t 7 >/dev/null 2>&1 & video-play medium -t 7 >/dev/null 2>&1 & video-play high -t 7 >/dev/null 2>&1 & wait; done'
}

# fluctuation pattern (one entry per chunk, cycled): n=benign-only(0%), m=normal(~30%), h=flood-heavy(~55%)
PATTERN=(m m h m n m m h m m n m h m m); P=0

wait_bot || lab_reset
cum=0; n=1
while [ "$(echo "$cum < $TARGET_BYTES" | bc)" -eq 1 ]; do
  t=${PATTERN[$(( P % ${#PATTERN[@]} ))]}; P=$((P+1))
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  case $t in
    n) benign 500M 256 ;;                                           # benign only
    m) benign 400M 256; docker exec -d custom-client custom-run -t "$CHUNK" -i 1 -d "$CHUNK" ;;  # ~30%
    h) benign 120M 512; docker exec -d custom-client custom-run -t "$CHUNK" -i 1 -d "$CHUNK" ;;  # flood-heavy
  esac
  sleep $(( CHUNK + 3 )); ./lab.sh pcap stop router >/dev/null 2>&1
  c=$(ls -t captures/router-clients-*.pcap|head -1)
  dest="$OUT/${PREFIX}-ddos-$(printf '%03d' "$n")-$t-clients.pcap"; mv "$c" "$dest"; rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  sz=$(stat -c %s "$dest"); atk=$(tcpdump -r "$dest" -nn 'host 10.45.0.2' 2>/dev/null|wc -l); tot=$(tcpdump -r "$dest" -nn 2>/dev/null|wc -l)
  cum=$(echo "$cum + $sz"|bc)
  printf 'chunk %03d [%s] %6.1fMB total=%8d attack=%8d (%4.1f%%) cum=%5.2fGB\n' "$n" "$t" "$(echo "$sz/1048576"|bc -l)" "$tot" "$atk" "$(echo "if($tot>0)100*$atk/$tot else 0"|bc -l)" "$(echo "$cum/1073741824"|bc -l)"
  # unexpected wedge on a flood chunk -> reset
  if { [ "$t" = m ] || [ "$t" = h ]; } && [ "$atk" -lt 100000 ]; then echo "  flood chunk low attack; resetting"; lab_reset; fi
  n=$((n+1))
done
echo "== done: $((n-1)) chunks, $(echo "scale=2;$cum/1073741824"|bc)GB in $OUT =="
