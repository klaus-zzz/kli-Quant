"""显式迁移独立金融开发库，不在服务启动时自动修改数据库。"""

from pathlib import Path

from alembic import command
from alembic.config import Config

from kli_quant.dev import prepare_database

if __name__ == "__main__":
    prepare_database()
    root = Path.cwd().parent / "Fina-Agent"
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")
