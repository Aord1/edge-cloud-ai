"""
云端配置 — 仅可部署差异化项，其余参数由各模块自行硬编码默认值。
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class CloudSettings(BaseSettings):
    # ── 服务 ──
    cloud_host: str = "0.0.0.0"
    cloud_port: int = 8000
    environment: str = "development"   # development | production

    # ── 数据库 ──
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "edge_cloud"
    db_user: str = "edgecloud"
    db_password: str = ""

    # ── LLM ──
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_base_url: str = ""                      # 空 = 默认官方地址；代理时填入

    # ── MQTT ──
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: str = "edgecloud"
    mqtt_password: str = ""

    # ── JWT ──
    jwt_secret_key: str = "change-in-production"

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = dict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore",
    )


settings = CloudSettings()
