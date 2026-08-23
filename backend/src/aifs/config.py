"""Deployment settings for the AIFS backend.

Settings are read from environment variables (prefix ``AIFS_``) and an
optional ``.env`` file; see ``.env.example``. The deployment layer injects
``basis_set_pool`` into ``RestInputRequest``, so rendered cards never contain
a machine-local path.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment-level configuration of the AIFS backend."""

    model_config = SettingsConfigDict(
        env_prefix="AIFS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    #: Root path of the deployed REST basis set pool.
    basis_set_pool: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the cached deployment settings."""
    return Settings()
