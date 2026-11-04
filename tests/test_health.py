"""验证骨架只暴露自身健康状态，不依赖数据或 Agent 服务。"""

from fastapi.testclient import TestClient

from backend.main import app


def test_health() -> None:
    """实际调用应用，检查状态码和对外约定。"""
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_only_health_route() -> None:
    """防止初始化阶段误带旧业务接口或框架默认文档入口。"""
    assert {route.path for route in app.routes} == {"/api/health"}
