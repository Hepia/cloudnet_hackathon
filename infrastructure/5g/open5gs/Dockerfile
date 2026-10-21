# Open5GS built from source on Debian 13. One image serves both the core (control plane) and the UPF;
# the command ("core" or "upf") selects the role, see entrypoint.sh.
FROM debian:trixie-slim AS build
ARG OPEN5GS_VERSION=v2.8.0
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates python3 python3-pip python3-setuptools python3-wheel \
        ninja-build build-essential flex bison cmake meson pkg-config \
        libsctp-dev libgnutls28-dev libgcrypt-dev libssl-dev libidn-dev libmongoc-dev libbson-dev \
        libyaml-dev libnghttp2-dev libmicrohttpd-dev libcurl4-gnutls-dev libtins-dev libtalloc-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${OPEN5GS_VERSION}" https://github.com/open5gs/open5gs.git /src/open5gs
WORKDIR /src/open5gs
RUN meson setup build --prefix=/opt/open5gs && ninja -C build && ninja -C build install

FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsctp1 libgnutls30t64 libgcrypt20 libssl3t64 libidn12 libmongoc-1.0-0t64 libbson-1.0-0t64 \
        libyaml-0-2 libnghttp2-14 libmicrohttpd12t64 libcurl3t64-gnutls libtins4.5 libtalloc2 \
        iproute2 iputils-ping procps tcpdump \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/open5gs /opt/open5gs
RUN printf '/opt/open5gs/lib\n/opt/open5gs/lib/x86_64-linux-gnu\n' > /etc/ld.so.conf.d/open5gs.conf && ldconfig \
    && if ldd /opt/open5gs/bin/open5gs-*d | grep -q "not found"; then ldd /opt/open5gs/bin/open5gs-*d | grep "not found"; exit 1; fi \
    && mkdir -p /var/log/open5gs
COPY config/ /etc/open5gs/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV PATH=/opt/open5gs/bin:$PATH
ENTRYPOINT ["/entrypoint.sh"]
CMD ["core"]
