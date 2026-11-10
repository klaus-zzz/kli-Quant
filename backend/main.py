"""独立于外部服务的最小 HTTP 进程。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.agent.api import router as chat_router
from backend.agent.config import configured_runtime
from backend.agent.cube_api import router as cube_router
from backend.agent.envd import router as envd_router
from backend.agent.tools import router as tool_router
from backend.research.api import install_handlers
from backend.research.api import router as research_router
from backend.research.config import configured_service
from backend.tushare import router


@asynccontextmanager
async def lifespan(app):
    """显式启用时才启动真实接线；配置缺失不能退化成无认证业务入口。"""
    runtime = configured_runtime(app.state.research_service)
    app.state.agent = runtime
    if runtime:
        await runtime.start()
    try:
        yield
    finally:
        if runtime:
            await runtime.stop()
        app.state.agent = None


# 数据工具使用受控入口；健康检查不依赖数据源配置。
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(router)
app.include_router(research_router)
app.include_router(chat_router)
app.include_router(cube_router)
app.include_router(envd_router)
app.include_router(tool_router)
install_handlers(app)
app.state.research_service = configured_service()
app.state.agent = None


@app.get("/api/health")
async def health() -> dict[str, str]:
    """表示当前进程能够响应，不声称外部服务已经就绪。"""
    return {"status": "ok"}
