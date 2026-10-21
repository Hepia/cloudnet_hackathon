#!/bin/bash
# core: runs the ten control-plane functions in one container (NRF and SCP first).
# upf:  creates the ogstun tunnel interface, points the default route at the router on the client
#       network (N6) and runs the UPF. No NAT: UE addresses are routed as they are.
set -euo pipefail
CFG=/etc/open5gs

case "${1:-core}" in
  core)
    pids=()
    trap 'kill "${pids[@]}" 2>/dev/null' TERM INT
    for nf in nrf scp; do
      open5gs-${nf}d -c "$CFG/$nf.yaml" & pids+=($!)
      sleep 1
    done
    for nf in amf smf ausf udm udr pcf nssf bsf; do
      open5gs-${nf}d -c "$CFG/$nf.yaml" & pids+=($!)
    done
    wait -n || true
    echo "entrypoint: a network function exited, stopping the core" >&2
    kill "${pids[@]}" 2>/dev/null || true
    exit 1
    ;;
  upf)
    UE_SUBNET=${UE_SUBNET:-10.45.0.0/16}
    UE_GATEWAY=${UE_GATEWAY:-10.45.0.1}
    N6_GATEWAY=${N6_GATEWAY:-10.10.2.1}
    ip tuntap add name ogstun mode tun 2>/dev/null || true
    ip addr replace "$UE_GATEWAY/${UE_SUBNET#*/}" dev ogstun
    ip link set ogstun up
    ip route replace default via "$N6_GATEWAY"
    echo "entrypoint: ogstun $UE_GATEWAY/${UE_SUBNET#*/}, default route via $N6_GATEWAY"
    exec open5gs-upfd -c "$CFG/upf.yaml"
    ;;
  *)
    exec "$@"
    ;;
esac
