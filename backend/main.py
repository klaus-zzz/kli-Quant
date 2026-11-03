"""独立于外部服务的最小 HTTP 进程。"""

from fastapi import FastAPI

# 骨架只公开健康检查，后续接口由对应开发任务增加。
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """表示当前进程能够响应，不声称外部服务已经就绪。"""
    return {"status": "ok"}
