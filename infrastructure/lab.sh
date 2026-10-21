#!/bin/bash
# Host-side control of the lab. Everything runs inside containers; traffic is started with docker exec.
#
#   ./lab.sh up                  build the images (first time: several minutes) and start everything,
#                                then wait until the UE has a PDU session
#   ./lab.sh down                stop and remove the containers and networks
#   ./lab.sh status              container state, UE address, routes
#   ./lab.sh build [service]     rebuild the images without starting anything (e.g. after editing custom/)
#   ./lab.sh test                end-to-end check: 5G attach, routing, isolation, HTTP, MQTT, RTP, iperf3,
#                                custom generator
#   ./lab.sh run                 the whole campaign: up, capture on the router, HTTP + MQTT + video +
#                                iperf3 from the clients and from the UE, the custom generator through
#                                the UE, stop, present the pcap files (captures/run-<date>/);
#                                PCAP_ON="router upf" to capture on more containers, RUN_DOWN=1 to
#                                tear the lab down afterwards
#
#   ./lab.sh http  [args]        http-client:  http-get   [all|1k|10m ...] [-n COUNT]
#   ./lab.sh mqtt  [args]        mqtt-client:  mqtt-run   [-i INTERVAL] [-n COUNT]
#   ./lab.sh video [args]        video-client: video-play [all|low|medium|high] [-t SECONDS] [-p udp|tcp]
#   ./lab.sh custom [args]       custom-client: custom-run [-s HOST] [-p PORT] [-r REQUEST] [-t SECONDS] [-i INTERVAL] [-d DELAY]
#                                (your generator; runs in the UE network namespace: sends requests up
#                                to the custom server, which sends the requested traffic down to the UE)
#   ./lab.sh ue-http|ue-mqtt|ue-video [args]
#                                the same, but from the UE through the 5G user plane
#   ./lab.sh ue-ping [host]      ping from the UE (default: the HTTP server)
#   ./lab.sh ue-iperf [args]     iperf3 from the UE to the iperf server (e.g. -R for downlink)
#   ./lab.sh exec <container> <command...>
#   ./lab.sh logs <container>    follow logs (core, upf, gnb, ue, http, mqtt, video, ...)
#   ./lab.sh capture <container> [tcpdump args]
#                                live tcpdump inside a container (router, upf, gnb, ue, ...)
#   ./lab.sh pcap start|stats|stop [container]
#                                pcap files for every interface of the router (default), upf or gnb,
#                                written to ./captures/<container>-<network>-<date>.pcap on the host;
#                                stats: packets and bytes per interface and per file so far.
#                                Headers only by default (128 bytes); PCAP_SNAPLEN=0 for full payloads
set -uo pipefail
cd "$(dirname "$0")"

# Docker group membership from /etc/group applies to new logins only; use sg otherwise.
if ! docker version >/dev/null 2>&1 && getent group docker | grep -qw "$USER"; then
  exec sg docker -c "$(printf '%q ' "$0" "$@")"
fi

ue_ip() { docker exec ue ip -4 -o addr show dev uesimtun0 2>/dev/null | awk '{print $4}' | cut -d/ -f1; }

wait_ue() {
  local i
  for i in $(seq 1 "${1:-60}"); do
    ip=$(ue_ip)
    if [ -n "$ip" ]; then echo "UE has PDU session, address $ip"; return 0; fi
    sleep 2
  done
  echo "UE did not get a PDU session; see: ./lab.sh logs ue, ./lab.sh logs gnb, ./lab.sh logs core" >&2
  return 1
}

check() { # check <description> <command...>
  local desc=$1; shift
  if "$@" >/tmp/lab-check.$$ 2>&1; then
    echo "PASS  $desc"; pass=$((pass + 1))
  else
    echo "FAIL  $desc"; sed 's/^/      /' /tmp/lab-check.$$ | tail -5; fail=$((fail + 1))
  fi
  rm -f /tmp/lab-check.$$
}

check_not() { # check_not <description> <command...>: passes when the command fails
  local desc=$1; shift
  if "$@" >/dev/null 2>&1; then echo "FAIL  $desc"; fail=$((fail + 1)); else echo "PASS  $desc"; pass=$((pass + 1)); fi
}

# pcap_ifaces <container>: "<interface> <network>" per interface with an address, lo excluded
pcap_ifaces() {
  docker exec "$1" sh -c 'ip -o -4 addr show | awk "!seen[\$2]++ {print \$2, \$4}"' | while read -r dev addr; do
    case $addr in
      127.*) continue ;;
      10.10.1.*) net=servers ;; 10.10.2.*) net=clients ;; 10.10.3.*) net=core ;; 10.10.4.*) net=radio ;;
      *) net=$dev ;;
    esac
    echo "$dev $net"
  done
}

pcap_start() { # pcap_start <container> <stamp> [dir]: tcpdump on every interface, pcap per interface
  local c=$1 stamp=$2 dir=${3:-}
  if [ -f "captures/.$c.stamp" ]; then echo "capture already running for $c (./lab.sh pcap stop $c first)" >&2; return 1; fi
  [ -z "$dir" ] || docker exec "$c" mkdir -p "/captures/$dir"
  pcap_ifaces "$c" | while read -r dev net; do
    docker exec -d "$c" tcpdump -ni "$dev" -U -s "${PCAP_SNAPLEN:-128}" -Z root -w "/captures/${dir:+$dir/}$c-$net-$stamp.pcap"
    echo "capturing $c $dev ($net) -> captures/${dir:+$dir/}$c-$net-$stamp.pcap"
  done
  echo "${dir:+$dir/}:$stamp" > "captures/.$c.stamp"
  echo "snaplen ${PCAP_SNAPLEN:-128} bytes (PCAP_SNAPLEN=0 keeps full payloads; at iperf3 speed that is gigabytes per second)"
}

pcap_stop() { # pcap_stop <container>
  local c=$1
  docker exec "$c" pkill -INT tcpdump 2>/dev/null || echo "no tcpdump running in $c"
  sleep 1
  docker exec "$c" sh -c 'chown -R '"$(id -u):$(id -g)"' /captures 2>/dev/null'   # tcpdump wrote them as root
  pcap_stats "$c"
  rm -f "captures/.$c.stamp"
}

pcap_files() { # pcap_files <container>: the files of the running (or last) capture, host paths
  local c=$1 rec
  rec=$(cat "captures/.$c.stamp" 2>/dev/null) || return 1
  ls "captures/${rec%%:*}$c"-*-"${rec##*:}".pcap 2>/dev/null
}

pcap_breakdown() { # pcap_breakdown <container> <file...>: packets per protocol, counted inside the container
  local c=$1; shift
  printf '%-36s %8s %8s %8s %8s %8s %8s %8s %8s\n' file total http mqtt rtsp rtp iperf3 custom icmp
  for f in "$@"; do
    docker exec "$c" sh -c '
      f=/captures/${1#captures/}; n() { tcpdump -nn -q -r "$f" "$2" 2>/dev/null | wc -l; }
      printf "%-36s %8d %8d %8d %8d %8d %8d %8d %8d\n" "$(basename "$f")" "$(n x "")" "$(n x "tcp port 80")" \
        "$(n x "tcp port 1883")" "$(n x "tcp port 8554")" "$(n x "udp and not port 8554 and not port 1235 and not icmp")" \
        "$(n x "tcp port 5201")" "$(n x "port 1234 or port 1235")" "$(n x "icmp")"' sh "$f"
  done
}

pcap_stats() { # pcap_stats <container>
  local c=$1 stamp
  echo "== $c interface counters (since container start)"
  printf '%-10s %-8s %12s %14s %12s %14s\n' iface network rx_pkts rx_bytes tx_pkts tx_bytes
  pcap_ifaces "$c" | while read -r dev net; do
    docker exec "$c" awk -v d="$dev" -v n="$net" '$1 == d":" {printf "%-10s %-8s %12d %14d %12d %14d\n", d, n, $3, $2, $11, $10}' /proc/net/dev
  done
  rec=$(cat "captures/.$c.stamp" 2>/dev/null) || { echo "(no capture running for $c)"; return 0; }
  stamp=${rec##*:}
  echo "== pcap files of the capture started $stamp"
  printf '%-40s %10s %14s\n' file packets bytes
  docker exec "$c" sh -c 'for f in /captures/'"${rec%%:*}$c"'-*-'"$stamp"'.pcap; do
      [ -f "$f" ] || continue
      printf "%-40s %10d %14d\n" "$(basename "$f")" "$(tcpdump -nn -q -r "$f" 2>/dev/null | wc -l)" "$(stat -c %s "$f")"
    done'
}

step() { # step <description> <command...>: runs it, logs output, records PASS/FAIL, never stops the campaign
  local desc=$1 t0 t1; shift
  echo; echo "---- $(date +%T) $desc"
  t0=$(date +%s)
  if "$@"; then t1=$(date +%s); echo "---- PASS ($((t1 - t0)) s) $desc"; pass=$((pass + 1))
  else t1=$(date +%s); echo "---- FAIL ($((t1 - t0)) s) $desc"; fail=$((fail + 1)); fi
}

# interactive terminal only when there is one (scripts and cron have none)
if [ -t 0 ] && [ -t 1 ]; then IT=(-it); else IT=(); fi

cmd=${1:-help}; shift || true
case $cmd in
  up)
    mkdir -p captures   # bind-mounted into router, upf and gnb; created here so it belongs to the user
    docker compose up -d --build "$@" && wait_ue 60
    ;;
  down)
    docker compose down "$@"
    ;;
  build)
    docker compose build "$@"
    ;;
  status)
    docker compose ps
    echo
    ip=$(ue_ip); echo "UE address: ${ip:-none}"
    docker exec ue ip route 2>/dev/null | sed 's/^/UE route: /'
    docker exec upf ip -4 -o addr show dev ogstun 2>/dev/null | awk '{print "UPF ogstun: "$4}'
    ;;
  test)
    pass=0; fail=0
    echo "== 5G"
    check "core: ten network functions running" docker exec core sh -c 'test "$(pgrep -c -f open5gs-)" -ge 10'
    check "core: SMF has a PFCP association with the UPF" sh -c 'docker logs core 2>&1 | grep -q "PFCP associated"'
    check "core: gNB connected (NG setup)" sh -c 'docker logs core 2>&1 | grep -q "gNB-N2 accepted"'
    check "ue: PDU session established" wait_ue 30
    ip=$(ue_ip)
    echo "== routing from the UE ($ip) through the UPF and the router"
    check "ue -> UPF gateway 10.45.0.1" docker exec ue ping -c 3 -W 2 10.45.0.1
    check "ue -> router 10.10.2.1" docker exec ue ping -c 3 -W 2 10.10.2.1
    check "ue -> HTTP server 10.10.1.10" docker exec ue ping -c 3 -W 2 10.10.1.10
    check "ue -> http-client 10.10.2.10" docker exec ue ping -c 3 -W 2 10.10.2.10
    check "http-client -> ue $ip (return path)" docker exec http-client ping -c 3 -W 2 "$ip"
    check "http-client -> HTTP server (via router)" docker exec http-client ping -c 3 -W 2 10.10.1.10
    echo "== isolation"
    check_not "router has no default route" docker exec router sh -c 'ip route | grep -q default'
    check_not "http-client cannot reach the host ($(hostname -I | awk '{print $1}'))" docker exec http-client ping -c 1 -W 2 "$(hostname -I | awk '{print $1}')"
    check_not "ue cannot reach the Internet (1.1.1.1)" docker exec ue ping -c 1 -W 2 1.1.1.1
    echo "== applications from the client network"
    check "http-client: downloads all files" docker exec http-client http-get all
    check "mqtt-client: subscribe and publish 3 messages at 0.5 s" docker exec mqtt-client mqtt-run -i 0.5 -n 3
    check "video-client: RTP stream 'low' for 5 s" docker exec video-client video-play low -t 5
    echo "== applications from the UE through the 5G user plane"
    check "ue: downloads all files" docker exec ue http-get all
    check "ue: MQTT 3 messages at 0.5 s" docker exec ue mqtt-run -i 0.5 -n 3
    check "ue: RTP stream 'medium' for 5 s" docker exec ue video-play medium -t 5
    check "ue: iperf3 uplink 3 s" docker exec ue iperf3 -c 10.10.1.40 -t 3
    check "ue: iperf3 downlink 3 s" docker exec ue iperf3 -c 10.10.1.40 -t 3 -R
    check "custom-client (in the UE): requests traffic from the custom server, 3 s" docker exec custom-client custom-run -t 3
    echo
    echo "$pass passed, $fail failed"
    [ "$fail" -eq 0 ]
    ;;
  run)
    pass=0; fail=0
    stamp=$(date +%Y%m%d-%H%M%S); dir=run-$stamp; log=captures/$dir/run.log
    containers=${PCAP_ON:-router}
    mkdir -p "captures/$dir"
    exec > >(tee "$log") 2>&1      # everything below goes to the terminal and to run.log
      echo "lab5g campaign $stamp (log: $log)"
      step "start the lab" "$0" up
      for c in $containers; do step "start capture on $c" pcap_start "$c" "$stamp" "$dir"; done
      sleep 2
      echo; echo "==== traffic from the client network"
      step "http-client: all files, ${HTTP_ROUNDS:-2} rounds"       docker exec http-client http-get all -n "${HTTP_ROUNDS:-2}"
      step "mqtt-client: ${MQTT_COUNT:-10} messages every ${MQTT_INTERVAL:-0.5} s" docker exec mqtt-client mqtt-run -i "${MQTT_INTERVAL:-0.5}" -n "${MQTT_COUNT:-10}"
      step "video-client: all streams, ${VIDEO_SECONDS:-10} s each"  docker exec video-client video-play all -t "${VIDEO_SECONDS:-10}"
      step "http-client: iperf3 uplink ${IPERF_SECONDS:-5} s"      docker exec http-client iperf3 -c 10.10.1.40 -t "${IPERF_SECONDS:-5}"
      echo; echo "==== traffic from the UE through the 5G user plane"
      step "ue: all files, ${HTTP_ROUNDS:-2} rounds"                docker exec ue http-get all -n "${HTTP_ROUNDS:-2}"
      step "ue: ${MQTT_COUNT:-10} messages every ${MQTT_INTERVAL:-0.5} s" docker exec ue mqtt-run -i "${MQTT_INTERVAL:-0.5}" -n "${MQTT_COUNT:-10}"
      step "ue: all streams, ${VIDEO_SECONDS:-10} s each"           docker exec ue video-play all -t "${VIDEO_SECONDS:-10}"
      step "ue: iperf3 uplink ${IPERF_SECONDS:-5} s"               docker exec ue iperf3 -c 10.10.1.40 -t "${IPERF_SECONDS:-5}"
      step "ue: iperf3 downlink ${IPERF_SECONDS:-5} s"             docker exec ue iperf3 -c 10.10.1.40 -t "${IPERF_SECONDS:-5}" -R
      step "custom-client (in the UE): requests traffic from the custom server for ${CUSTOM_DURATION:-10} s" docker exec custom-client custom-run -t "${CUSTOM_DURATION:-10}"
      sleep 2
      echo; echo "==== captures"
      for c in $containers; do
        files=$(pcap_files "$c")
        docker exec "$c" pkill -INT tcpdump 2>/dev/null; sleep 1
        docker exec "$c" sh -c 'chown -R '"$(id -u):$(id -g)"' /captures 2>/dev/null'
        rm -f "captures/.$c.stamp"
        echo "-- $c: packets per protocol (rtp = all other UDP; iperf3 = tcp 5201)"
        # shellcheck disable=SC2086
        pcap_breakdown "$c" $files
        echo "-- $c: files"
        ls -l $files
      done
      echo
      echo "campaign $stamp: $pass steps passed, $fail failed; everything is in captures/$dir/"
      [ "${RUN_DOWN:-0}" != 1 ] || step "stop the lab" docker compose down
    sleep 0.2
    [ "$fail" -eq 0 ]
    ;;
  http)     docker exec "${IT[@]}" http-client http-get "$@" ;;
  mqtt)     docker exec "${IT[@]}" mqtt-client mqtt-run "$@" ;;
  video)    docker exec "${IT[@]}" video-client video-play "$@" ;;
  custom)   docker exec "${IT[@]}" custom-client custom-run "$@" ;;
  ue-http)  docker exec "${IT[@]}" ue http-get "$@" ;;
  ue-mqtt)  docker exec "${IT[@]}" ue mqtt-run "$@" ;;
  ue-video) docker exec "${IT[@]}" ue video-play "$@" ;;
  ue-ping)  docker exec "${IT[@]}" ue ping -c "${PING_COUNT:-5}" "${1:-10.10.1.10}" ;;
  ue-iperf) docker exec "${IT[@]}" ue iperf3 -c 10.10.1.40 "$@" ;;
  exec)     docker exec "${IT[@]}" "$@" ;;
  logs)     docker compose logs -f "$@" ;;
  capture)  c=$1; shift; docker exec "${IT[@]}" "$c" tcpdump -ni any "$@" ;;
  pcap)
    sub=${1:-stats}; c=${2:-router}
    case $sub in
      start) mkdir -p captures; pcap_start "$c" "$(date +%Y%m%d-%H%M%S)" ;;
      stats) pcap_stats "$c" ;;
      stop)  pcap_stop "$c" ;;
      *) echo "usage: ./lab.sh pcap start|stats|stop [router|upf|gnb]" >&2; exit 1 ;;
    esac
    ;;
  help|*)   sed -n '2,/^set -/{/^set -/d;p}' "$0" ;;
esac
