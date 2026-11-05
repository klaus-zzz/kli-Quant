"""仅在后端加载研究存储配置；实例化不会连接数据库或启动执行器。"""

import os

from backend.research.repository import Repository
from backend.research.service import ResearchService
from backend.research.storage import Archive


def configured_service():
    keys = (
        "DATABASE_URL",
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
    )
    values = [os.environ.get(f"RESEARCH_{key}") for key in keys]
    if not all(values):
        return None
    dsn, endpoint, bucket, access, secret = values
    return ResearchService(Repository(dsn), Archive(endpoint, bucket, access, secret))
