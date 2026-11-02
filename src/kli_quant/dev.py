"""金融服务使用独立数据库和配置；不向 Fina-Agent 容器安装本包。"""

import os

from dotenv import dotenv_values
from fina_agent.dev import main


def prepare_database():
    """要求单独的研究数据库，阻止两端 Worker 误用同一个队列。"""
    values = {**dotenv_values(".env"), **os.environ}
    url = values.get("KLI_DATABASE_URL")
    if not url or url == values.get("DATABASE_URL"):
        raise RuntimeError("separate_KLI_DATABASE_URL_required")
    os.environ["DATABASE_URL"] = url


if __name__ == "__main__":
    prepare_database()
    main("kli_quant.service:create_service", "fina_agent.worker", factory=True)
