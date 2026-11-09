# 使用官方版本标签，保留 CubeSandbox 的 envd、tini 和启动契约。
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM ghcr.io/tencentcloud/cubesandbox-base:2026.16
COPY --from=uv /uv /usr/local/bin/uv

# 官方 base 不含 Python；安装固定版本与独立 CLI 环境。
COPY sandbox/requirements.lock /tmp/kli-quant-requirements.lock
RUN UV_PYTHON_INSTALL_DIR=/opt/kli-quant/python uv venv --python 3.12.15 /opt/kli-quant/venv \
    && uv pip sync --python /opt/kli-quant/venv/bin/python --require-hashes \
        --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        /tmp/kli-quant-requirements.lock \
    && rm /tmp/kli-quant-requirements.lock \
    && uv cache clean

# 保留 axi.json 声明的包路径；不复制环境配置、控制端 SDK 或后端代码。
COPY sandbox/cli/*.py sandbox/cli/axi.json sandbox/cli/restricted.json /opt/kli-quant/sandbox/cli/
COPY sandbox/cli/contracts/ /opt/kli-quant/sandbox/cli/contracts/
ENV AXI_CONFIG=/opt/kli-quant/sandbox/cli/axi.json \
    PATH=/opt/kli-quant/venv/bin:$PATH
# 将 CLI 包路径注册到独立环境；envd 不继承 PYTHONPATH，创建接口也禁止注入它。
RUN /opt/kli-quant/venv/bin/python -c "import site; from pathlib import Path; Path(site.getsitepackages()[0], 'kli_quant_cli.pth').write_text('/opt/kli-quant\n')"
