"""验证骨架只暴露自身健康状态，不依赖数据或 Agent 服务。"""

from fastapi.testclient import TestClient

from backend.main import app


def test_health() -> None:
    """实际调用应用，检查状态码和对外约定。"""
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_public_routes() -> None:
    """公开路由固定；研究管理功能不作为无认证管理 API 暴露。"""
    assert set(app.openapi()["paths"]) == {
        "/api/health",
        "/api/tushare/{name}",
        "/api/research/runs",
        "/api/research/runs/{run_id}",
        "/api/research/runs/{run_id}/cancel",
        "/api/research/runs/{run_id}/result",
        "/api/research/runs/{run_id}/evidence",
        "/api/research/runs/{run_id}/evidence/{evidence_id}",
        "/api/chat/sessions",
        "/api/chat/sessions/{session}",
        "/api/chat/sessions/{session}/history",
        "/api/chat/sessions/{session}/thinking",
        "/api/chat/sessions/{session}/messages",
        "/api/research/context",
        "/api/research/source",
        "/api/research/evidence/{evidence_id}",
        "/api/research/execute",
        "/api/research/publish",
    }
