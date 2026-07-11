from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 默认通道（可与 grok/gemini 分 key）
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""

    # Grok 通道（不填则回退 llm_*）
    grok_base_url: str = ""
    grok_api_key: str = ""
    grok_model: str = "grok-3"

    # Gemini 通道（不填则回退 llm_*）
    gemini_base_url: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_design_model: str = ""

    host: str = "127.0.0.1"
    port: int = 8787
    output_dir: str = "outputs"

    # 单次调用超时（秒）；multi-agent 可能较慢
    llm_timeout: float = 300

    @property
    def design_model(self) -> str:
        return self.gemini_design_model or self.gemini_model

    def grok_url(self) -> str:
        return (self.grok_base_url or self.llm_base_url).rstrip("/")

    def gemini_url(self) -> str:
        return (self.gemini_base_url or self.llm_base_url).rstrip("/")

    def grok_key(self) -> str:
        return self.grok_api_key or self.llm_api_key

    def gemini_key(self) -> str:
        return self.gemini_api_key or self.llm_api_key

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent.parent / p
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
