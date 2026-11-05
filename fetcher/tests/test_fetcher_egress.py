"""在隔离抓取容器内显式运行的出口验收；普通回归不访问网络。"""

import os
import socket
import subprocess
import unittest
import urllib.request
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("RESEARCH_TEST_EGRESS") == "1", "仅隔离容器出口验收"
)
class FetcherEgressTests(unittest.TestCase):
    def test_private_connections_blocked_below_application(self):
        """绕过应用校验直接连自身监听端口，内核仍须拒绝回环和容器私网地址。"""
        private = socket.gethostbyname(socket.gethostname())
        with socket.socket() as listener:
            listener.bind(("0.0.0.0", 80))
            listener.listen()
            for address in ("127.0.0.1", private, "169.254.169.254", "168.63.129.16"):
                with self.subTest(address=address):
                    with self.assertRaises(OSError):
                        socket.create_connection((address, 80), timeout=1).close()
            listener.settimeout(0.1)
            with self.assertRaises(TimeoutError):
                listener.accept()

    def test_ipv6_loopback_blocked(self):
        """IPv6 回环已有监听服务时，仍不能通过直接 socket 绕过出口策略。"""
        with socket.socket(socket.AF_INET6) as listener:
            try:
                listener.bind(("::1", 80))
            except OSError:
                self.skipTest("容器未启用 IPv6 回环")
            listener.listen()
            with self.assertRaises(OSError):
                socket.create_connection(("::1", 80), timeout=1).close()

    def test_worker_cannot_remove_firewall(self):
        """实际应用主进程已降权；测试进程也不能清空规则。"""
        status = dict(
            line.split(":", 1)
            for line in Path("/proc/1/status").read_text().splitlines()
            if ":" in line
        )
        self.assertEqual(status["Uid"].split()[0], "65532")
        self.assertEqual(int(status["CapEff"], 16), 0)
        self.assertEqual(int(status["CapBnd"], 16), 0)
        result = subprocess.run(["nft", "flush", "ruleset"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_public_https_still_works(self):
        """防火墙保留真实公网 HTTPS 和 DNS，不依赖代理环境变量。"""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("https://example.com/", timeout=20) as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
