FROM debian:13-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends iperf3 iputils-ping iproute2 procps \
    && rm -rf /var/lib/apt/lists/*
CMD ["iperf3", "-s"]
