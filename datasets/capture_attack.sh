#!/bin/bash
# capture_attack.sh <target_attack_millions> <flood_s> <max_floods>
# Build a pool of REAL Mirai SYN-flood traffic as repeated SOLO floods (no benign, so
# the userspace 5G plane is not CPU-starved -> floods are reliable and repeatable).
# Each flood is captured to datasets/pcap_attack/ and its attack-packet count verified;
# only if a flood comes back low do we reset the lab and re-warm the bot.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE/../infrastructure"
TARGET_M=${1:-35}; FLOOD=${2:-90}; MAXF=${3:-16}
OUT="$HERE/pcap_attack"; mkdir -p "$OUT"
UPLOG=/tmp/claude-1000/-home-eryk-cloudnet-hackathon/e1355f62-9722-4021-a4c4-e4900d68af69/scratchpad/cap_up.log
TARGET=$(echo "$TARGET_M * 1000000" | bc)

wait_bot() {  # wait until the bot is connected to its CNC (ESTAB on :23); the bot takes
              # a long, variable time to connect after startup, so poll up to ~4 min
  for _ in $(seq 1 80); do
    docker exec custom-client sh -c 'ss -nt 2>/dev/null | grep -q ":23 "' && { sleep 2; return 0; }
    sleep 3
  done; return 1
}
lab_reset() {
  echo "  -- lab reset --"
  timeout 100 ./lab.sh down >/dev/null 2>&1
  nohup ./lab.sh up > "$UPLOG" 2>&1 &
  local t0=$(date +%s)
  while [ $(( $(date +%s) - t0 )) -lt 200 ]; do grep -q "UE has PDU session" "$UPLOG" 2>/dev/null && break; sleep 4; done
  wait_bot
}

solo_flood() {  # solo_flood <n>; echo attack count, keeps file if good
  local n=$1
  ./lab.sh pcap start router >/dev/null 2>&1; sleep 1
  docker exec -d custom-client custom-run -t "$FLOOD" -i 1 -d "$FLOOD"
  sleep $(( FLOOD + 3 )); ./lab.sh pcap stop router >/dev/null 2>&1
  local c; c=$(ls -t captures/router-clients-*.pcap|head -1)
  local dest="$OUT/attack-ddos-f$(printf '%02d' "$n")-clients.pcap"
  mv "$c" "$dest"; rm -f "$(ls -t captures/router-servers-*.pcap 2>/dev/null|head -1)"
  local a; a=$(tcpdump -r "$dest" -nn 'host 10.45.0.2' 2>/dev/null|wc -l)
  local min=$(( FLOOD * 20000 ))   # expect >=20k pps; else treat as failed
  if [ "$a" -lt "$min" ]; then rm -f "$dest"; echo "0"; else
    printf '  flood %02d: attack=%d (%.0fk pps) %.0fMB\n' "$n" "$a" "$(echo "$a/$FLOOD/1000"|bc -l)" "$(echo "$(stat -c %s "$dest")/1048576"|bc -l)" >&2
    echo "$a"
  fi
}

wait_bot || lab_reset
cum=0; n=1; fails=0
while [ "$(echo "$cum < $TARGET" | bc)" -eq 1 ] && [ "$n" -le "$MAXF" ]; do
  a=$(solo_flood "$n")
  if [ "$a" -gt 0 ]; then cum=$((cum + a)); n=$((n+1)); fails=0
    echo "  cumulative attack: $cum / $TARGET"
  else
    fails=$((fails+1)); echo "  flood $n failed ($fails); re-waiting for bot"
    if wait_bot; then echo "  bot reconnected, retrying"; else
      echo "  bot not connected; resetting lab"; lab_reset
    fi
    [ "$fails" -ge 4 ] && { echo "  too many failures, stopping"; break; }
  fi
done
echo "=== attack pool: $(ls "$OUT"/*.pcap 2>/dev/null|wc -l) files, ~${cum} attack pkts, $(du -sh "$OUT" 2>/dev/null|cut -f1) ==="
