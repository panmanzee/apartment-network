FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 nftables wireguard-tools iperf3 iputils-ping iputils-arping \
    socat netcat-openbsd tcpdump curl procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*
CMD ["sleep","infinity"]
