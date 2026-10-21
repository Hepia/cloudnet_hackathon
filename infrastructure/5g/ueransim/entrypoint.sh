#!/bin/bash
# gnb: runs the gNB (N2 and N3 on the core network, radio link on the radio network).
# ue:  runs UE_COUNT UEs with consecutive IMSIs. As soon as the first PDU session is up (uesimtun0 has
#      an address) the default route is moved into the tunnel, so plain ping/curl/iperf3 from this
#      container go through the 5G user plane. The radio network stays reachable as a connected route.
set -euo pipefail
case "${1:-ue}" in
  gnb)
    exec nr-gnb -c /etc/ueransim/gnb.yaml
    ;;
  ue)
    nr-ue -c /etc/ueransim/ue.yaml -n "${UE_COUNT:-1}" &
    pid=$!
    trap 'kill $pid 2>/dev/null' TERM INT
    (
      while true; do
        if ip -4 addr show dev uesimtun0 2>/dev/null | grep -q inet \
           && ! ip route show default 2>/dev/null | grep -q uesimtun0; then
          ip route replace default dev uesimtun0
          echo "entrypoint: default route via uesimtun0 ($(ip -4 -o addr show dev uesimtun0 | awk '{print $4}'))"
        fi
        sleep 2
      done
    ) &
    wait $pid
    ;;
  *)
    exec "$@"
    ;;
esac
