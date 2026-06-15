"""
云端配置 — 所有可配置参数的唯一入口，各模块从此处引用，消除硬编码重定义。
"""

from __future__ import annotations

from pydantic import ConfigDict
from pydantic_settings import BaseSettings
from sqlalchemy import URL


class CloudSettings(BaseSettings):
    # ── 服务 ──
    cloud_host: str = "0.0.0.0"
    cloud_port: int = 8000
    environment: str = "development"   # development | production

    # ── 数据库 ──
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "edge_cloud"
    db_user: str = "postgres"
    db_password: str = ""

    # ── 数据库连接池 ──
    db_pool_size: int = 5
    db_max_overflow: int = 15
    db_pool_recycle: int = 3600      # 连接回收时间（秒）
    db_pool_timeout: int = 30        # 获取连接超时（秒）

    # ── MQTT ──
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: str = "edgecloud"
    mqtt_password: str = ""

    # ── JWT ──
    jwt_secret_key: str = "change-in-production"

    # ── Agent 复核队列 ──
    review_queue_maxsize: int = 200       # 复核队列最大容量
    review_consumer_interval: float = 2.0 # 消费者间隔（秒）

    # ── API 默认值 ──
    api_defects_limit: int = 30

    # ── Agent 工具默认值 ──
    agent_defect_history_limit: int = 10
    agent_defect_stats_hours: int = 24

    # ── RAG 知识库 ──
    embedding_model_id: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    rag_top_k: int = 3
    rag_similarity_threshold: float = 0.5

    # ── 时区 ──
    timezone_hours: int = 8               # UTC+8

    @property
    def db_url(self) -> str:
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)

    model_config = ConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore",
    )


settings = CloudSettings()
