"""领域凭据仅由安装应用的后端进程读取。"""

from fina_agent.config import Settings as PlatformSettings
from pydantic import Field, SecretStr


class Settings(PlatformSettings):
    """继承部署配置以兼容现有取数工具，不向模型传递此对象。"""

    tushare_token: SecretStr | None = None
    http_tool_token: SecretStr | None = Field(default=None, validation_alias="KLI_TOOL_TOKEN")
