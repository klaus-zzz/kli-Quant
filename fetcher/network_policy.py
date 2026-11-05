"""抓取器的应用校验和容器出口共用地址范围，禁止内网及地址转换隧道。"""

import ipaddress

# IPv4 特殊用途地址及云平台控制地址不能作为原文来源。
DENIED_V4 = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.88.99.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "168.63.129.16/32",
)
# 仅开放原生全球单播 IPv6；排除特殊用途、文档地址及 6to4。
DENIED_V6 = ("2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20")
NETWORKS = tuple(ipaddress.ip_network(n) for n in (*DENIED_V4, *DENIED_V6))
GLOBAL_V6 = ipaddress.ip_network("2000::/3")


def is_public(address):
    """统一拒绝非公网、作用域地址和可能转入 IPv4 私网的 IPv6 形式。"""
    ip = ipaddress.ip_address(address)
    return (
        "%" not in address
        and ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and (ip.version == 4 or ip in GLOBAL_V6)
        and not any(ip in network for network in NETWORKS)
    )


def firewall_rules():
    """在 Docker DNS 的目标地址转换前过滤；仅允许 DNS、响应及公网 Web 出站。"""
    return f"""table inet research_egress {{
  chain output {{
    type filter hook output priority -150; policy drop;
    ct state established,related accept
    ip daddr 127.0.0.11 udp dport 53 accept
    ip daddr 127.0.0.11 tcp dport 53 accept
    ip daddr {{ {", ".join(DENIED_V4)} }} reject
    ip6 daddr {{ {", ".join(DENIED_V6)} }} reject
    meta nfproto ipv4 tcp dport {{ 80, 443 }} accept
    ip6 daddr 2000::/3 tcp dport {{ 80, 443 }} accept
  }}
}}
"""


if __name__ == "__main__":
    print(firewall_rules())
