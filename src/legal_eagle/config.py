"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    minimax_model: str = Field(default="minimax/minimax-M3")
    minimax_api_key: Optional[str] = Field(default=None)
    minimax_base_url: Optional[str] = Field(default=None)

    # CourtListener
    courtlistener_base_url: str = Field(
        default="https://www.courtlistener.com/api/rest/v4"
    )
    courtlistener_api_token: Optional[str] = Field(default=None)

    # EUR-Lex
    eurlex_base_url: str = Field(default="https://eur-lex.europa.eu")
    eurlex_sparql_endpoint: str = Field(
        default="https://publications.europa.eu/webapi/rdf/sparql"
    )

    # Supabase
    supabase_url: Optional[str] = Field(default=None)
    supabase_service_key: Optional[str] = Field(default=None)

    # Runtime
    log_level: str = Field(default="INFO")
    cache_ttl_seconds: int = Field(default=900)
    rate_limit_rpm: int = Field(default=30)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
