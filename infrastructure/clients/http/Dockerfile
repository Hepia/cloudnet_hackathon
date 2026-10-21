FROM debian:13-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl iputils-ping iproute2 iperf3 traceroute tcpdump procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY clients/bin/http-get /usr/local/bin/
CMD ["tail", "-f", "/dev/null"]
