# Custom traffic generator: one image for both ends, so the server and the client have exactly the same
# binaries. compose starts it as "custom" (server, 10.10.1.50) and "custom-client" (client, in the network
# namespace of the UE, so its traffic crosses the 5G user plane); the first argument of entrypoint.sh
# (server|client) picks the start script.
# Edit the three marked places: the packages, the local package, and the files the image needs.
FROM debian:13-slim
ENV DEBIAN_FRONTEND=noninteractive

# (1) packages from Debian 13. netcat-openbsd provides nc. Add yours after it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        netcat-openbsd iputils-ping iproute2 iperf3 traceroute tcpdump procps ca-certificates jq \
	mariadb-server mariadb-client mariadb-server-core mariadb-client-core mariadb-common \
	mysql-common libmariadb3 galera-4 socat rsync perl libdbi-perl libconfig-inifiles-perl \
	gawk lsof psmisc passwd iproute2 mariadb-backup mariadb-client-compat mariadb-server-compat \
	mariadb-plugin-provider-lz4 mariadb-plugin-provider-lzma mariadb-plugin-provider-lzo \
	mariadb-plugin-provider-snappy mariadb-plugin-provider-bzip2 \
    && rm -rf /var/lib/apt/lists/*

# (2) your own package: drop the .deb file(s) into custom/pkg/ and rebuild. The directory is copied as
#     is; apt installs every .deb in it together with their dependencies, and nothing happens while the
#     directory is empty.
COPY pkg/ /tmp/pkg/
RUN if ls /tmp/pkg/*.deb >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends /tmp/pkg/*.deb \
        && rm -rf /var/lib/apt/lists/*; \
    fi && rm -rf /tmp/pkg

# (3) the files of the generator: server.sh starts the server side, client.sh whatever the client
#     needs in the background, custom-run sends the requests, custom-serve answers them on the server.
#     Add COPY lines for anything else
#     (configs, data, scripts).
COPY users.json /etc/mirai/db/users.json
COPY entrypoint.sh /custom/
COPY custom-run /usr/local/bin/
RUN chmod +x /custom/*.sh /usr/local/bin/custom-run

ENTRYPOINT ["/custom/entrypoint.sh"]
CMD ["server"]
