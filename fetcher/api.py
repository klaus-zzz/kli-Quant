"""无存储凭据的内部抓取服务，仅运行在受限出口容器。"""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from fetcher.sources import fetch_source

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class FetchRequest(BaseModel):
    """调用方只能给出来源 URL，不能修改代理、连接目标或校验策略。"""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)


@app.post("/fetch")
def fetch(body: FetchRequest):
    return fetch_source(body.url)
