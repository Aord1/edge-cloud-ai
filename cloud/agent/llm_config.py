"""LLM 运行时配置管理 — 支持热切换模型。

配置持久化到 llm_config.json（已 gitignore），重启后自动恢复。
API Key 存储在本地文件中，不会提交到版本控制。
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "llm_config.json"


class LLMRuntimeConfig:
    """运行时 LLM 配置，支持热更新与持久化。

    model / base_url / temperature / api_key 持久化到 llm_config.json（gitignored）。
    """

    def __init__(self) -> None:
        self.model: str = "gpt-4o"
        self.base_url: str = ""
        self.api_key: str = ""
        self.temperature: float = 0.3
        self._load_from_file()

    def update(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None:
        if model is not None:
            self.model = model
        if base_url is not None:
            self.base_url = base_url
        if api_key is not None:
            self.api_key = api_key
        if temperature is not None:
            self.temperature = temperature
        self._save_to_file()

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "api_key_set": bool(self.api_key),
        }

    def _load_from_file(self) -> None:
        try:
            if CONFIG_FILE.exists():
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.model = data.get("model", self.model)
                self.base_url = data.get("base_url", self.base_url)
                self.api_key = data.get("api_key", self.api_key)
                self.temperature = data.get("temperature", self.temperature)
        except Exception:
            pass

    def _save_to_file(self) -> None:
        try:
            CONFIG_FILE.write_text(
                json.dumps({
                    "model": self.model,
                    "base_url": self.base_url,
                    "api_key": self.api_key,
                    "temperature": self.temperature,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass


llm_runtime = LLMRuntimeConfig()
