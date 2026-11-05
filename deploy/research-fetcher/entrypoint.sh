#!/bin/sh
set -eu

# 规则安装失败即停止，不能启动一个没有出口隔离的抓取器。
python -m backend.research.network_policy > /tmp/research-egress.nft
nft -f /tmp/research-egress.nft
rm /tmp/research-egress.nft
chown 65532:65532 /opt/venv

# 抓取进程无 root 身份和任何 capability，不能清空防火墙或另建网络命名空间。
exec setpriv --reuid=65532 --regid=65532 --clear-groups \
    --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs \
    sh -c 'uv sync --locked --no-dev && exec uv run --no-sync uvicorn backend.research.fetch_api:app --host 0.0.0.0 --port 18101 --limit-concurrency 8'
