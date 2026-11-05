"""固定对象读写；只有服务端生成的键和配置能到达对象存储。"""

import hashlib
import json
from uuid import uuid4

import boto3
from botocore.config import Config

from backend.research.models import ResearchError

MAX_OBJECT_BYTES = 24 * 1024 * 1024


def encode(value) -> bytes:
    """固定 JSON 编码用于输入、输出和内容校验，不接受 NaN。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


class Archive:
    """后端独占 S3 凭据；不返回预签名 URL 或开放任意对象键读取。"""

    def __init__(self, endpoint, bucket, access_key, secret_key):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
            config=Config(
                connect_timeout=5,
                read_timeout=20,
                retries={"max_attempts": 0},
                s3={"addressing_style": "path"},
            ),
        )

    def put(self, run_id, value):
        """每次写入使用新键，失败不会覆盖既有版本。"""
        data = encode(value)
        if len(data) > MAX_OBJECT_BYTES:
            raise ResearchError("object_too_large", 413)
        digest = hashlib.sha256(data).hexdigest()
        key = f"research/{run_id}/{uuid4()}/{digest}.json"
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType="application/json"
        )
        ref = {"object_key": key, "sha256": digest, "size": len(data)}
        self.read(ref)
        return ref

    def read(self, ref):
        """每次读取验证长度和摘要，篡改对象不能参与发布或重放。"""
        response = self.client.get_object(Bucket=self.bucket, Key=ref["object_key"])
        stream = response["Body"]
        try:
            data = stream.read(MAX_OBJECT_BYTES + 1)
        finally:
            stream.close()
        if (
            len(data) != ref["size"]
            or hashlib.sha256(data).hexdigest() != ref["sha256"]
        ):
            raise ResearchError("content_mismatch")
        return json.loads(data)
