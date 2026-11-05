FROM python:3.12.15-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.13.7-python3.12-trixie-slim \
    /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

# 安装出口防火墙与降权工具；镜像只包含抓取器自身文件。
# 国内镜像加速索引和软件包下载，仍由 Debian 官方签名校验。
RUN sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get install -y --no-install-recommends nftables util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /usr/local/bin/research-fetcher
WORKDIR /app
COPY . /app/fetcher
ENTRYPOINT ["sh", "/usr/local/bin/research-fetcher"]
