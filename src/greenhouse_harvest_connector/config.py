from __future__ import annotations

from dataclasses import dataclass
import os


def _read_env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class GreenhouseConfig:
    client_id: str
    client_secret: str
    user_id: str | None = None
    token_url: str = "https://auth.greenhouse.io/token"
    base_url: str = "https://harvest.greenhouse.io/v3"
    per_page: int = 200

    @classmethod
    def from_env(cls) -> "GreenhouseConfig":
        per_page = int(_read_env("GREENHOUSE_PER_PAGE", "200") or "200")
        if per_page < 1 or per_page > 500:
            raise ValueError("GREENHOUSE_PER_PAGE must be between 1 and 500")
        return cls(
            client_id=_read_env("GREENHOUSE_CLIENT_ID", required=True) or "",
            client_secret=_read_env("GREENHOUSE_CLIENT_SECRET", required=True) or "",
            user_id=_read_env("GREENHOUSE_USER_ID"),
            per_page=per_page,
        )


@dataclass(frozen=True)
class RedshiftConfig:
    host: str
    database: str
    user: str
    password: str
    port: int = 5439
    schema: str = "public"
    iam: bool = False

    @classmethod
    def from_env(cls) -> "RedshiftConfig":
        return cls(
            host=_read_env("REDSHIFT_HOST", required=True) or "",
            database=_read_env("REDSHIFT_DATABASE", required=True) or "",
            user=_read_env("REDSHIFT_USER", required=True) or "",
            password=_read_env("REDSHIFT_PASSWORD", required=True) or "",
            port=int(_read_env("REDSHIFT_PORT", "5439") or "5439"),
            schema=_read_env("REDSHIFT_SCHEMA", "public") or "public",
            iam=(_read_env("REDSHIFT_IAM", "false") or "false").lower() == "true",
        )


@dataclass(frozen=True)
class GoogleSheetsConfig:
    service_account_json: str
    spreadsheet_id: str
    worksheet_name: str

    @classmethod
    def from_env(cls) -> "GoogleSheetsConfig":
        return cls(
            service_account_json=_read_env("GOOGLE_SERVICE_ACCOUNT_JSON", required=True) or "",
            spreadsheet_id=_read_env("GOOGLE_SHEETS_SPREADSHEET_ID", required=True) or "",
            worksheet_name=_read_env("GOOGLE_SHEETS_WORKSHEET", required=True) or "",
        )
