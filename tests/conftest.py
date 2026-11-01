"""虚构记录与内存归档只用于离线单元测试，不参与运行时接入。"""

import hashlib
from datetime import timedelta

import pytest
from fina_agent.agent.storage import RunStore
from fina_agent.database import Base
from fina_agent.models import Research, Run, utcnow
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from kli_quant.config import Settings


class MemoryArchive:
    """测试替身保留哈希与对象归档语义。"""

    limit = 2000000

    def __init__(self):
        self.objects = {}

    def put(self, run_id, content, media_type):
        digest = hashlib.sha256(content).hexdigest()
        self.objects[digest] = content
        return {"sha256": digest, "key": digest, "bucket": "fictional-test", "size": len(content)}

    def get(self, reference):
        return self.objects[reference["sha256"]]


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        database_url=None,
        model_api_key="fictional-model-key",
        model_base_url="https://model.invalid/v1",
        model_name="fictional-model",
        tushare_token="fictional-token",
        s3_endpoint_url="https://s3.invalid",
        s3_bucket="fictional-test",
        s3_access_key="fictional-access",
        s3_secret_key="fictional-secret",
        cube_api_url="https://cube.invalid",
        cube_template_id="fictional-template",
    )


@pytest.fixture
def store(settings):
    """单元测试用 SQLite；锁与迁移另用真正 PostgreSQL 验证。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        research = Research(title="虚构公司事件")
        session.add(research)
        session.flush()
        run = Run(
            research_id=research.id,
            input={"event": "虚构事件", "source_urls": []},
            policy={},
            status="running",
            as_of=utcnow(),
            deadline=utcnow() + timedelta(minutes=5),
        )
        session.add(run)
        session.commit()
        yield RunStore(session, run, MemoryArchive())
    engine.dispose()
