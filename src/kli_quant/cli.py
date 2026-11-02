"""面向独立金融服务的 HTTP 客户端；服务令牌只从后端环境读取。"""

import argparse
import json
import os
import sys
from uuid import UUID, uuid4

import httpx
from dotenv import dotenv_values


def main():
    """同 scope 查询、取消和复核；请求编号可显式重用以安全重试提交。"""
    parser = argparse.ArgumentParser(description="kli-Quant 金融 HTTP 工具客户端")
    parser.add_argument("--server", default="http://127.0.0.1:8001")
    parser.add_argument("--scope", type=UUID, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    research = commands.add_parser("research")
    research.add_argument("event")
    research.add_argument("--url", action="append", default=[])
    research.add_argument("--parent", type=UUID)
    research.add_argument("--request-id", type=UUID, default=None)
    for name in ("status", "cancel"):
        commands.add_parser(name).add_argument("task_id", type=UUID)
    args = parser.parse_args()
    token = os.environ.get("KLI_TOOL_TOKEN") or dotenv_values(".env").get("KLI_TOOL_TOKEN")
    if not token:
        parser.error("需要后端 KLI_TOOL_TOKEN 配置")
    try:
        with httpx.Client(
            base_url=args.server,
            timeout=30,
            trust_env=False,
            headers={
                "Authorization": "Bearer " + token,
                "X-Task-Scope": str(args.scope),
            },
        ) as client:
            if args.command == "research":
                response = client.post(
                    "/v1/tasks",
                    json={
                        "request_id": str(args.request_id or uuid4()),
                        "input": {"event": args.event, "source_urls": args.url},
                        "parent_task_id": str(args.parent) if args.parent else None,
                    },
                )
            elif args.command == "cancel":
                response = client.post(f"/v1/tasks/{args.task_id}/cancel")
            else:
                response = client.get(f"/v1/tasks/{args.task_id}")
            response.raise_for_status()
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except (httpx.HTTPError, ValueError):
        print("请求失败，请检查服务连接、scope 和任务编号。", file=sys.stderr)
        raise SystemExit(1) from None
