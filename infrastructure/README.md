# lab5g: a self-contained 5G traffic lab in Docker

Fifteen containers, four private Docker networks, nothing reachable from outside and no way out.
A simulated UE attaches to an Open5GS core through a UERANSIM gNB; its user plane leaves the UPF
into the client network. Three application clients and the UE request content from an HTTP server,
an MQTT broker, an RTP video server and an iperf3 server that live in a separate server network,
behind a router. A fifth server and a client that lives inside the UE are the two ends of your own
traffic generator (`custom/`). All traffic is started with `docker exec` (wrapped by `lab.sh`).

```
                       servers 10.10.1.0/24                   clients 10.10.2.0/24
  ┌───────────┐  .10   │                                      │  .10  ┌──────────────┐
  │ http      ├────────┤                                      ├───────┤ http-client  │
  │ nginx     │        │                                      │       └──────────────┘
  ├───────────┤  .20   │                                      │  .20  ┌──────────────┐
  │ mqtt      ├────────┤        ┌─────────────────┐           ├───────┤ mqtt-client  │
  │ mosquitto │        │   .1/.2│     router      │.1/.2      │       └──────────────┘
  ├───────────┤  .30   ├────────┤  10.45/16 via   ├───────────┤  .30  ┌──────────────┐
  │ video     ├────────┤        │  10.10.2.100    │           ├───────┤ video-client │
  │ mediamtx  │        │        └─────────────────┘           │       └──────────────┘
  ├───────────┤  .40   │                                      │ .100  ┌──────────────┐  N6 (ogstun 10.45.0.1/16)
  │ iperf     ├────────┤                                      ├───────┤ upf          │
  ├───────────┤  .50   │                                      │       │ open5gs-upfd │
  │ custom    ├────────┤                                      │       └──────┬───────┘
  │ server.sh │        │                      core 10.10.3.0/24 (N2/N3/N4)   │ .20
  └───────────┘        ┌────────┐ .5     ┌────────┐ .10        .30 ┌───────┐ │
                       │ mongo  ├────────┤  core  ├────────────────┤  gnb  ├─┘
                       └────────┘        │ 10 NFs │   N2 SCTP, N3  │ nr-gnb│
                                         └────────┘                └───┬───┘ .30
                                                       radio 10.10.4.0/24 │
                                                                   .40 ┌───┴───────────────┐
                                                                       │  ue               │ uesimtun0 10.45.0.x
                                                                       │  nr-ue            │ default route -> tunnel
                                                                       │  + custom-client  │ same network namespace
                                                                       └───────────────────┘
```

| Container | Image | Address | Role |
| --- | --- | --- | --- |
| `router` | debian 13 | 10.10.1.1 (.2), 10.10.2.1 (.2) | forwards between the two networks, routes `10.45.0.0/16` to the UPF, has no default route |
| `http` | nginx 1.27 | 10.10.1.10 | serves `/files/{1k,10k,100k,1m,10m,100m}.bin` (random bytes), directory listing on `/files/` |
| `mqtt` | eclipse-mosquitto 2.0 | 10.10.1.20 | open broker on 1883, every connection and subscription logged |
| `video` | mediamtx 1.21 + ffmpeg | 10.10.1.30 | RTSP on 8554: `low` (320x240, 300 kb/s), `medium` (640x480, 1 Mb/s), `high` (1280x720, 3 Mb/s), H.264/AAC, started on demand, RTP over UDP or TCP |
| `iperf` | debian 13 | 10.10.1.40 | `iperf3 -s` |
| `custom` | debian 13 + nc, iperf3, your packages | 10.10.1.50 | server side of your own generator: `custom-serve` takes requests on TCP 1234 and sends the requested traffic back to the requester, see [Custom traffic generator](#custom-traffic-generator) |
| `http-client` | debian 13 + curl | 10.10.2.10 | `http-get` |
| `mqtt-client` | debian 13 + mosquitto clients | 10.10.2.20 | `mqtt-run` |
| `video-client` | debian 13 + ffmpeg | 10.10.2.30 | `video-play` |
| `custom-client` | same image as `custom` | UE namespace (10.45.0.x) | `custom-run`: client side of your own generator; shares the network namespace of the UE, so its requests go up and the requested traffic comes down through the 5G user plane; iperf3 receiver on 1235 |
| `mongo` | mongo 8.0 | 10.10.3.5 | subscriber database, provisioned from `5g/mongo-init/subscribers.js` at first start |
| `core` | Open5GS v2.8.0 (built from source) | 10.10.3.10 | NRF, SCP, AMF, SMF, AUSF, UDM, UDR, PCF, NSSF, BSF in one container |
| `upf` | same image | 10.10.3.20, 10.10.2.100 | UPF; `ogstun` 10.45.0.1/16; default route to the router; no NAT |
| `gnb` | UERANSIM v3.2.7 (built from source) | 10.10.3.30, 10.10.4.30 | gNB, PLMN 001/01, TAC 1 |
| `ue` | same image + curl, mosquitto clients, ffmpeg, iperf3 | 10.10.4.40, tunnel 10.45.0.x | UE `imsi-001010123456780`; default route through `uesimtun0` |

Addresses are fixed in `docker-compose.yml` and repeated in the configs under `5g/`. The clients,
the UE (and with it `custom-client`) and `custom` have the server names (`http`, `mqtt`, `video`,
`iperf`, `custom`) in `/etc/hosts`.

## Requirements

Verified on this machine: Debian 13, kernel 6.12, Docker Engine 26.1 (`docker.io` package),
user in the `docker` group, 22 cores, 30 GB RAM.

- Docker Compose v2 and a buildx newer than the `docker-buildx` package of Debian 13. Both are
  installed as user plugins in `~/.docker/cli-plugins/` (compose v5.6.0, buildx v0.38.0), which
  the `docker` CLI prefers over the system ones. No root needed.
- `/dev/net/tun` on the host (UPF and UE tunnels) and the `sctp` kernel module, which the kernel
  loads on its own when the AMF opens its first SCTP socket (verified; `lsmod | grep sctp`).
- Internet access only to build the images (base images, apt, GitHub); none afterwards.

## Use

```bash
./lab.sh run         # the whole campaign, see below
./lab.sh up          # builds on first run (Open5GS and UERANSIM from source: several minutes), starts
                     # everything and waits until the UE has a PDU session
./lab.sh test        # end to end: 5G, routing in both directions, isolation, HTTP, MQTT, RTP, iperf3, custom
./lab.sh build [svc] # rebuild images without starting (e.g. after editing custom/)
./lab.sh status
./lab.sh down
```

### One command: start, capture, traffic, results

```bash
./lab.sh run
```

starts the lab (builds first if needed), starts tcpdump on both router interfaces, runs the traffic
from the client network and then from the UE through the 5G user plane, stops the capture and prints
the result:

| Step | Default | Knob |
| --- | --- | --- |
| HTTP: every file, from http-client and from the UE | 2 rounds | `HTTP_ROUNDS` |
| MQTT: subscribe, publish at a fixed interval, from mqtt-client and from the UE | 10 messages, 0.5 s | `MQTT_COUNT`, `MQTT_INTERVAL` |
| video: the three RTP streams, from video-client and from the UE | 10 s each | `VIDEO_SECONDS` |
| iperf3: http-client uplink; UE uplink and downlink | 5 s each | `IPERF_SECONDS` |
| custom: `custom-run` from custom-client (in the UE) requests traffic from the custom server, which sends it down to the UE | 10 s | `CUSTOM_DURATION`, `CUSTOM_REQUEST`, `CUSTOM_INTERVAL`, `CUSTOM_DELAY`, `CUSTOM_SERVER`, `CUSTOM_PORT` |
| capture | router, headers only (128 bytes) | `PCAP_ON="router upf gnb"`, `PCAP_SNAPLEN=0` |
| afterwards | lab keeps running | `RUN_DOWN=1` |

Everything lands in `captures/run-<date>/`: `router-clients-<date>.pcap`, `router-servers-<date>.pcap`
(open them in Wireshark) and `run.log` with every step's output, PASS/FAIL and duration, and a table
of packets per protocol per file (HTTP, MQTT, RTSP, RTP, iperf3, custom, ICMP). Example:

```bash
VIDEO_SECONDS=20 IPERF_SECONDS=10 PCAP_ON="router upf" ./lab.sh run
```

Captures keep 128 bytes per packet by default, which is enough for every header and for all
statistics (packet lengths are recorded). `PCAP_SNAPLEN=0` keeps the payloads; with iperf3 running at
tens of Gbit/s between containers that is several gigabytes per second of capture.

Traffic, all via `docker exec` (`./lab.sh exec <container> <command>` for anything else):

```bash
./lab.sh http all -n 3            # http-client: every file, three rounds   -> file, code, bytes, s, MB/s
./lab.sh http 10m 100m            # only these files
./lab.sh mqtt -i 0.2 -n 50        # mqtt-client: subscribe to lab/#, publish 50 messages at 5 Hz
./lab.sh mqtt -i 1 -n 0           # ... forever (Ctrl-C)
./lab.sh video all -t 10          # video-client: receive each RTSP/RTP stream for 10 s
./lab.sh video high -t 30 -p tcp  # one stream, RTP interleaved in TCP
./lab.sh custom -t 10             # custom-client, through the UE: request traffic from the custom server for 10 s (one request every 1 + 3 s)
./lab.sh custom -r "SEND tcp 5 10M" -d 5   # ... a different request: TCP, 5 s at 10 Mb/s, requests spaced by 1 + 5 s

./lab.sh ue-http all              # the same three tools from the UE, through gNB -> UPF -> router
./lab.sh ue-mqtt -i 0.5 -n 20
./lab.sh ue-video low -t 10
./lab.sh ue-ping 10.10.1.10       # ping from the UE
./lab.sh ue-iperf -t 10           # iperf3 uplink to the iperf server; -R for downlink

./lab.sh logs core                # or upf, gnb, ue, http, mqtt, video, ...
./lab.sh capture router -n icmp   # live tcpdump inside a container (Ctrl-C to stop)
./lab.sh capture upf -ni ogstun   # user-plane packets after GTP decapsulation
```

Packet captures by hand, on the router's two interfaces, written as pcap files to `captures/`:

```bash
./lab.sh pcap start               # tcpdump on the servers side and the clients side of the router
./lab.sh http all; ./lab.sh ue-video low -t 10     # ... any traffic ...
./lab.sh pcap stats               # packets and bytes so far, per interface and per file
./lab.sh pcap stop                # stops tcpdump, prints the final summary
ls captures/                      # router-servers-<date>.pcap, router-clients-<date>.pcap (open in Wireshark)
```

`./lab.sh pcap start upf` captures on the UPF instead (its N3 side, N6 side and `ogstun`), and
`./lab.sh pcap start gnb` on the gNB; `pcap stop` and `pcap stats` take the same container name.

On the host, the bridges are named `lab-servers`, `lab-clients`, `lab-core` and `lab-radio`, so
`sudo tcpdump -ni lab-clients` sees the traffic of a whole network.

More UEs: `UE_COUNT=3 docker compose up -d ue` starts three UEs with consecutive IMSIs (five are
provisioned). Only the first tunnel carries the container's default route; use `ping -I uesimtun1`
for the others.

## How the isolation works

Each network sets `com.docker.network.bridge.inhibit_ipv4`, so the host does not take the gateway
address of the bridge (no address at all). Docker still installs `default via 10.10.x.1` in every
container; the router container adds those addresses to its own interfaces and so becomes the
gateway. The router has no default route, the UPF's default route points at the router, the UE's at
its tunnel. There is no NAT anywhere: the UE is reachable from the clients at its 10.45.0.x address
(router and UPF forward it), and the servers see the UE address in their logs.

Subscriber keys: K `00112233445566778899aabbccddeeff`, OPc `63BFA50EE6523365FF14C1F45F88737D`
(`5g/mongo-init/subscribers.js` and `5g/ueransim/ue.yaml`).

## Custom traffic generator

Two containers built from the same image (`custom/Dockerfile`), so both ends have exactly the same
binaries: `custom` (server, 10.10.1.50, server network) and `custom-client` (client). The client
has no network of its own: it joins the network namespace of the UE (`network_mode: service:ue`),
so it sees `uesimtun0`, uses the UE address (10.45.0.x) and its default route, and every packet it
sends goes UE -> gNB -> UPF -> router -> server, like the `ue-*` commands. It therefore shows up in
the pcap files of the gNB and the UPF (inside GTP) and of the router (column `custom`, ports 1234
and 1235). Hostname and `/etc/hosts` are the UE's, so `custom`, `http`, ... resolve.

As delivered it is a request/response generator: the client asks, the server sends. `custom-serve`
on the server listens on TCP 1234 with `nc`; `custom-run` on the client sends a one-line request to
it with `nc`, prints the one-line reply and the server then generates the requested traffic
towards the address the request came from (the UE, 10.45.0.x), with iperf3 against the receiver
that `client.sh` runs on port 1235 in custom-client. So the request goes up through the 5G user
plane and the traffic comes down through it (UPF -> gNB -> UE), one job at a time (the receiver
takes one test at a time; the reply says `started` or `queued`). `./lab.sh test` and `./lab.sh run`
exercise it as is:

```
./lab.sh custom -t 10                        # 10 s of "SEND udp 3 1M" requests, one every 1 + 3 s
./lab.sh custom -r "SEND tcp 5 10M" -d 5     # a different request, spaced by 1 + 5 s (no overlap)
./lab.sh logs custom                         # the requests and the iperf3 result of every job
./lab.sh logs custom-client                  # what the receiver got
```

Request: `SEND [tcp|udp] [SECONDS] [RATE] [PORT]` (defaults udp, 3, 1M bits/s, 1235; `RATE` 0 = as
fast as possible). Anything else is answered with `ERR` and logged. The reply is
`OK job N started|queued: udp 1M for 3 s -> 10.45.0.2:1235`.

`custom-run` options: `-s HOST` (default `CUSTOM_SERVER` or `10.10.1.50`; a host name is printed with its address), `-p PORT` (`CUSTOM_PORT`,
1234), `-r REQUEST` (`CUSTOM_REQUEST`, `SEND udp 3 1M`), `-t SECONDS` (`CUSTOM_DURATION`, 10: how long
requests are sent), `-i INTERVAL` (`CUSTOM_INTERVAL`, 1), `-d DELAY` (`CUSTOM_DELAY`, 3): extra seconds
added to the wait after every request, so that requests are spaced by `INTERVAL + DELAY`; keep it at
the `SECONDS` of the request and the jobs do not overlap. The wait after the last request covers
its job, so the traffic is over when `custom-run` returns. The client starts after the UE; its
receiver is up at once, the requests only get through once the PDU session is up (`./lab.sh status`).

To make it yours, edit the files in `custom/` and rebuild with `./lab.sh up` (or `./lab.sh build custom`;
both containers pick up the new image):

1. `Dockerfile`, block (1): the Debian 13 packages you need (`netcat-openbsd` provides `nc`).
2. `pkg/`: drop your own `.deb` file(s) here; block (2) installs them with apt at build time.
3. `Dockerfile`, block (3): `COPY` lines for configs, data or scripts your generator needs.
4. `server.sh`: the start commands of the server, one background line each (runs in `custom`);
   as delivered `custom-serve`. Its function `request()` is where a request line becomes traffic:
   change the iperf3 command, add request types, or replace it with your own generator.
5. `client.sh`: anything the client needs running in the background (runs in `custom-client`;
   as delivered the iperf3 receiver). Anything that listens there is reachable at the UE address.
6. `custom-run`, function `traffic()`: sends `$REQUEST` to `$SERVER:$PORT` and prints the reply;
   the loop around it runs it every `CUSTOM_INTERVAL + CUSTOM_DELAY` seconds until `CUSTOM_DURATION` (`-t`) is reached.
7. `docker-compose.yml`, services `custom` and `custom-client`: `cap_add`, `sysctls`, `volumes` or
   `environment` if the generator needs them (addresses, names and networks stay; the client keeps
   `network_mode: service:ue`, which rules out `hostname`, `extra_hosts`, `ports` and `networks`).
8. `lab.sh`: the `custom` steps in `test` and `run`, and the ports counted in the `custom` column of
   `pcap_breakdown` (1234, 1235) if yours differ.

## This hackathon: Mirai attack + the UERANSIM uplink patch

The generic lab above is specialised for the DDoS-detection hackathon in two ways. Both
are already built into the images; this section documents them.

**The custom generator is a real Mirai botnet.** `custom/pkg/` holds
`mirai-bot-and-cnc_1.0_amd64.deb` (CNC + bot), so block (2) of `custom/Dockerfile`
installs Mirai into both `custom` and `custom-client`. `custom/entrypoint.sh` starts the
Mirai **CNC first and waits until it listens on `:23`**, then starts the **bot** (started
in the other order the bot's first connect fails and only recovers after a long backoff).
`custom/users.json` is overlaid to `/etc/mirai/db/users.json` with the SLA/QoS caps
removed (`cooldown=0`, `duration_limit=3600`, `max_bots=-1`) so floods are not throttled.
Because the bot runs in the UE namespace, its **SYN flood crosses the real 5G user plane**
(UE → gNB → UPF → router → target `10.10.1.50`). `custom-run` authenticates to the CNC and
issues the flood command:

```
docker exec custom-client sh -c 'ss -nt | grep ":23 "'   # bot <-> CNC established
docker exec -d custom-client custom-run -t 30 -i 1 -d 30 # task a 30 s SYN flood
```

**The UERANSIM UE uplink is patched so the flood survives capture.** Stock UERANSIM
v3.2.7 wedged the UE uplink to ~0 packets under the flood: the single-threaded
`TUN → appTask → nasTask (per-packet NAS ciphering) → RLS → UDP` chain uses **unbounded**
queues, so the `nasTask` backlog grew without bound and the tunnel stalled — captures
looked full (wired benign kept flowing) but held **no attack packets**. The patch in
`5g/ueransim/patch/` adds `NtsTask::pendingCount()` and makes the TUN receiver **drop
uplink packets once the `nasTask` backlog exceeds 4096**, bounding the queue so the tunnel
stays live. It is overlaid onto the UERANSIM source before `make` in
`5g/ueransim/Dockerfile`, i.e. compiled in by `./lab.sh up` — nothing to run by hand.

> If the UE ever wedges or comes up with the wrong address, do a **full reset**
> (`./lab.sh down && ./lab.sh up`); an in-place `docker restart` gives the UE a new IP and
> breaks routing.

Capturing, labelling and composing this traffic into datasets is covered in
`../datasets/README.md`; the detector that consumes them is in `../ddos_cnn_xgb/README.md`.

## Layout

```
docker-compose.yml       networks, 15 services, fixed addresses
lab.sh                   up / down / build / status / test / run / pcap and the docker exec wrappers
5g/open5gs/              Dockerfile (source build), config/*.yaml for the 10 NFs and the UPF, entrypoint.sh
5g/ueransim/             Dockerfile (source build), gnb.yaml, ue.yaml, entrypoint.sh
5g/mongo-init/           subscribers.js, run by the mongo image at first start
router/                  Dockerfile, entrypoint.sh (gateway addresses, routes)
servers/http|mqtt|video|iperf
clients/bin/             http-get, mqtt-run, video-play (installed in the clients and in the UE)
clients/http|mqtt|video  Dockerfiles
custom/                  your traffic generator, one image for both ends: Dockerfile, pkg/ (your .deb),
                         entrypoint.sh (server|client), server.sh (start commands of the server),
                         client.sh, custom-serve (request server), custom-run (request client)
captures/                pcap files written by ./lab.sh pcap (ignored by git)
```
