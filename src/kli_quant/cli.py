"""量化应用的最小 HTTP 客户端，不持有模型或数据源凭据。"""

import argparse
import json
import sys

import httpx


def main():
    """提交事件或查看执行；服务地址只能由操作用户配置。"""
    parser = argparse.ArgumentParser(description="kli-Quant 量化研究客户端")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    commands = parser.add_subparsers(dest="command", required=True)
    research = commands.add_parser("research")
    research.add_argument("event")
    research.add_argument("--url", action="append", default=[])
    research.add_argument("--topic", help="已有主题编号：创建新执行复核旧判断")
    status = commands.add_parser("status")
    status.add_argument("run_id")
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=args.server, timeout=30, trust_env=False) as client:
            if args.command == "research":
                path = f"/api/researches/{args.topic}/runs" if args.topic else "/api/researches"
                response = client.post(
                    path,
                    json={"application": "kli-quant", "event": args.event, "source_urls": args.url},
                )
            else:
                response = client.get(f"/api/runs/{args.run_id}")
            response.raise_for_status()
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except (httpx.HTTPError, ValueError):
        print("请求失败，请检查服务连接、应用安装与执行编号。", file=sys.stderr)
        raise SystemExit(1) from None
