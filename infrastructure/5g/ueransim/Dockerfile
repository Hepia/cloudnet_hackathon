# UERANSIM (gNB and UE simulator) built from source. Build context is the repository root so the
# UE gets the same traffic scripts as the clients (clients/bin). Command "gnb" or "ue" selects the role.
FROM ubuntu:22.04 AS build
ARG UERANSIM_VERSION=v3.2.7
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates make gcc g++ cmake libsctp-dev lksctp-tools \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${UERANSIM_VERSION}" https://github.com/aligungr/UERANSIM.git /src/ueransim
WORKDIR /src/ueransim
COPY 5g/ueransim/patch/ /src/ueransim/src/
RUN make -j"$(nproc)"

FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsctp1 lksctp-tools iproute2 iputils-ping iperf3 curl mosquitto-clients ffmpeg \
        tcpdump traceroute procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/ueransim/build/nr-gnb /src/ueransim/build/nr-ue /src/ueransim/build/nr-cli \
                  /src/ueransim/build/nr-binder /src/ueransim/build/libdevbnd.so /usr/local/bin/
COPY 5g/ueransim/gnb.yaml 5g/ueransim/ue.yaml /etc/ueransim/
COPY 5g/ueransim/entrypoint.sh /entrypoint.sh
COPY clients/bin/ /usr/local/bin/
RUN chmod +x /entrypoint.sh /usr/local/bin/*
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ue"]
