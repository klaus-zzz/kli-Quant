FROM python:3.12.15-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.13.7-python3.12-trixie-slim \
    /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

# 仅安装出口防火墙与降权工具；依赖和源码由根 Compose 提供。
RUN apt-get update && apt-get install -y --no-install-recommends nftables util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /usr/local/bin/research-fetcher
ENTRYPOINT ["sh", "/usr/local/bin/research-fetcher"]
