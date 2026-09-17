"""Configuração da API lida do `.env` da raiz do mono-repo.

Segredos de integração (Jira, Bitbucket, OpenAI) NÃO passam por aqui: ficam no
Cofre do Windows e são lidos pelo `CredentialStore`.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SprintAI"
    app_version: str = "0.1.0"

    db_host: str = "127.0.0.1"
    db_port: int = 5433
    db_name: str = "sprintai"
    db_user: str = "sprintai"
    db_password: str = "sprintai"
    db_pool_min: int = 1
    db_pool_max: int = 10

    api_host: str = "127.0.0.1"
    api_port: int = 8765

    front_origin: str = "http://localhost:5273"

    # Agendador de sync dentro da API. Desligado nos testes.
    sync_autostart: bool = True

    @property
    def asyncpg_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def sqlalchemy_url(self) -> str:
        return self.asyncpg_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
