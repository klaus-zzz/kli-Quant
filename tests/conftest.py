"""虚构记录与内存归档只用于离线单元测试，不参与运行时接入。"""

import hashlib
import os
from datetime import UTC, timedelta
from pathlib import Path

import pytest
from fina_agent.agent.storage import RunStore
from fina_agent.applications import applications
from fina_agent.database import Base
from fina_agent.instance import load_instance
from fina_agent.models import Research, Run, utcnow
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from kli_quant.config import Settings


@pytest.fixture(autouse=True)
def quant_instance(monkeypatch, request):
    """测试固定使用底座维护的金融配置，不能误用其他项目实例。"""
    # 替身测试不继承真实追踪凭据，真实联调保留显式授权的服务配置。
    if not request.node.get_closest_marker("live"):
        for name in tuple(os.environ):
            if name.startswith(("LANGSMITH_", "LANGCHAIN_")):
                monkeypatch.delenv(name)
    monkeypatch.setenv(
        "FINA_CONFIG_DIR",
        str(Path(__file__).parents[2] / "Fina-Agent" / ".fina-agent" / "providers" / "kli-quant"),
    )
    load_instance.cache_clear()
    applications.cache_clear()
    yield
    load_instance.cache_clear()
    applications.cache_clear()


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
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def restore_timezone(target, context, attrs):
        # SQLite 丢失时区；HTTP 测试模拟 PostgreSQL 刷新后的 UTC 时间。
        for name in ("as_of", "deadline"):
            value = getattr(target, name)
            if value is not None and value.tzinfo is None:
                setattr(target, name, value.replace(tzinfo=UTC))

    event.listen(Run, "refresh", restore_timezone)

    def restore_loaded_timezone(target, context):
        restore_timezone(target, context, None)

    event.listen(Run, "load", restore_loaded_timezone)
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
        try:
            yield RunStore(session, run, MemoryArchive())
        finally:
            event.remove(Run, "refresh", restore_timezone)
            event.remove(Run, "load", restore_loaded_timezone)
    engine.dispose()
