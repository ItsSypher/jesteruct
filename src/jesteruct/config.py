"""Runtime settings. Every field reads from JST_<NAME> (or .env); the OpenRouter key also reads OPENROUTER_API_KEY."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JST_", env_file=".env", env_ignore_empty=True, extra="ignore")

    # providers
    openrouter_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("JST_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    )
    openrouter_base_url: str = "https://openrouter.ai/api"
    jev_model: str = "typesafe/jev-1.13"
    vision_model: str = "google/gemini-3.8-flash"
    jev_rpm: int = 1000  # below Jev's 1,200/min limit, shared by every replica when Valkey is configured
    jev_batch_size: int = 1  # pages per Jev request; see docs/ARCHITECTURE.md for the measured effect
    jev_batch_wait_ms: int = 100  # how long a partial batch waits for more pages
    vision_rpm: int = 600
    jev_timeout_s: float = 30
    vision_timeout_s: float = 90

    # routing
    review_threshold: float = 0.5  # raw path probability below this sends a page to LH when no calibration is loaded
    use_calibration: bool = True  # decide review on the shipped calibration (src/jesteruct/calibration.json)
    ocr_backend: Literal["auto", "apple", "rapid"] = "auto"

    # execution
    cpu_workers: int = 0  # 0 means os.cpu_count(); set from the container CPU limit in Kubernetes
    page_concurrency: int = 8
    probe_timeout_s: float = 60

    # intake limits
    max_file_mb: int = 200
    max_pages: int = 2000
    max_children: int = 500
    max_depth: int = 3
    max_image_pixels: int = 120_000_000

    # service
    store_url: str = "file://.jst"
    # obstore options, e.g. {"endpoint": "http://seaweedfs:8333"} and {"allow_http": "true"}
    store_config: dict[str, str] = Field(default_factory=dict)
    store_client_options: dict[str, str] = Field(default_factory=dict)
    valkey_url: str | None = None
    stream: str = "jst:jobs"
    group: str = "workers"
    worker_max_docs: int = 2
    max_deliveries: int = 3
    max_backlog: int = 1000
    claim_idle_s: int = 120

    @property
    def cpu_count(self) -> int:
        return self.cpu_workers or os.cpu_count() or 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
