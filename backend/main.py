"""独立于外部服务的最小 HTTP 进程。"""

from fastapi import FastAPI

from backend.tushare import router

# 数据工具使用受控入口；健康检查不依赖数据源配置。
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """表示当前进程能够响应，不声称外部服务已经就绪。"""
    return {"status": "ok"}
