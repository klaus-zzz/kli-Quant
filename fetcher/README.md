# 原文抓取服务

独立提供 `POST /fetch`，请求体为 `{"url": "https://example.com/"}`。
返回抓取状态、原始字节、摘要、固定段落编号及时间信息；失败时返回稳定错误分类。
本服务不依赖后端代码，不读取数据库、S3 或数据源凭据，仅供可信后端通过内部网络调用。

使用 [Scrapling](https://github.com/D4Vinci/Scrapling) 0.5.1（BSD-3-Clause）
静态 HTTP 抓取与 HTML 解析，底层 HTTP/TLS 使用
[curl_cffi](https://curl-cffi.readthedocs.io/en/latest/api.html) 0.17.0。
只支持 HTML/纯文本，不启动浏览器，不支持动态页面和 PDF。

## 部署与边界

镜像、启动脚本、源码、依赖锁文件和测试均在本目录。根 Compose 从本目录构建并
只挂载本目录源码；部署时可修改服务名或网络地址，在后端设置完整接口地址：

```dotenv
RESEARCH_FETCHER_URL=http://my-fetcher:18101/fetch
```

该地址由后端部署环境控制，业务请求不能覆盖。根 Compose 提供开发默认值；
独立启动后端时需显式配置。配置缺失或服务不可用时返回 `fetcher_unavailable`，不回退直连。

每次抓取及每级重定向检查全部 IPv4/IPv6 解析结果，仅允许公网标准 80/443 端口。
通过 curl 的 [RESOLVE](https://curl.se/libcurl/c/CURLOPT_RESOLVE.html) 固定已验证 IP，
保留原域名的 Host、SNI 和 TLS 校验；不继承环境代理，不自动重试。
最多 5 次请求，共享 20 秒请求预算，单响应上限 4 MiB；系统 DNS 查询使用系统解析器超时。
固定 IP 适配使用 Scrapling 私有接口，升级依赖时须保留真实 HTTP/TLS 回归。

部署须保留根 Compose 中的隔离网络、挂载和启动权限配置：启动时通过
[nftables](https://www.nftables.org/) 仅放行 Docker DNS、已有连接的响应及公网 Web 出站，
规则安装失败即退出；随后以普通用户和零 capability 运行。服务不加入中间件网络，
不发布宿主端口。需要 Linux Docker、nftables 和 Compose ≥2.33.1。

## 验证

在本目录执行独立测试，依赖由本目录的 `pyproject.toml` 和 `uv.lock` 管理：

```bash
uv sync --locked
uv run pytest
```

出口验收需从仓库根目录显式针对已启动的隔离开发服务执行：

```bash
docker compose exec -T --user 65532:65532 -e RESEARCH_TEST_EGRESS=1 research-fetcher python - < fetcher/tests/test_fetcher_egress.py
```
