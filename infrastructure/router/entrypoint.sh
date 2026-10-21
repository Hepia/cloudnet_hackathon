#!/bin/bash
# Router between the server network and the client network.
# Docker reserves the gateway address of every network, and with inhibit_ipv4 assigns it to nothing
# on the host. This container adds those addresses to its own interfaces, so the default route that
# Docker installs in every other container ends here. It has no default route itself: nothing leaves.
set -euo pipefail
GATEWAYS=${GATEWAYS:-10.10.1.1/24 10.10.2.1/24}
UE_SUBNET=${UE_SUBNET:-10.45.0.0/16}
UE_VIA=${UE_VIA:-10.10.2.100}

for gw in $GATEWAYS; do
  prefix=${gw%.*}.
  dev=$(ip -o -4 addr show | awk -v p="$prefix" 'index($4, p) == 1 {print $2; exit}')
  [ -n "$dev" ] || { echo "router: no interface in ${prefix}0" >&2; exit 1; }
  ip addr add "$gw" dev "$dev"
  echo "router: $gw on $dev"
done
ip route del default 2>/dev/null || true
ip route replace "$UE_SUBNET" via "$UE_VIA"
echo "router: routes"; ip route
exec tail -f /dev/null
