"""Settings loaded from env / .env file.

See SPEC §8 (revised) for the full env list. All optional providers (Voyage,
Groq, R2, Resend) gracefully degrade when their keys are absent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Walk up from this file (apps/api/src/margin_api/config.py) to the repo root
# so `.env` is found regardless of which directory uvicorn was launched from.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    database_url: str = Field(default="postgresql://margin:margin@localhost:5432/margin")
    jwt_secret: str = Field(default="dev-not-secret-do-not-use-in-prod")
    public_base_url: str = Field(default="http://localhost:3000")
    api_base_url: str = Field(default="http://localhost:8080")

    # --- Embeddings (Voyage primary, local bge-small fallback) ---
    voyage_api_key: str | None = None
    voyage_embed_model: str = "voyage-3.5-lite"
    voyage_embed_dim_raw: int = 1024
    embed_dim: int = 768

    # --- LLM (Groq) ---
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Cloudflare R2 ---
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str = "margin-pages"
    r2_endpoint: str | None = None

    # --- Email (SMTP; if smtp_host unset, magic-link code is returned in the API response) ---
    # Default config uses Resend's SMTP endpoint. Switching providers is just
    # changing these env vars; the code path is provider-agnostic.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str = "resend"
    smtp_password: str | None = None
    smtp_from: str = "Margin <noreply@margin.dev>"
    # Set ONE of these. STARTTLS (port 587) is more reliable on restrictive
    # outbound networks like Render free tier. Implicit TLS (port 465) is
    # faster but blocked on some hosts.
    smtp_use_tls: bool = False
    smtp_start_tls: bool = True
    smtp_timeout: float = 15.0

    # Legacy — kept so existing deploys don't break on env load. No longer read.
    resend_api_key: str | None = None

    # --- Firebase Auth (Google Sign-In via Firebase Web SDK on the dashboard).
    # All three required to enable the /v1/auth/firebase endpoint. Private key
    # is the PEM with literal "\n" sequences (matches the format inside the
    # downloaded service-account JSON); we unescape at init time.
    firebase_project_id: str | None = None
    firebase_client_email: str | None = None
    firebase_private_key: str | None = None

    @property
    def firebase_enabled(self) -> bool:
        return all(
            [
                self.firebase_project_id,
                self.firebase_client_email,
                self.firebase_private_key,
            ]
        )

    # --- Rate limiting ---
    rate_limit_per_minute: int = 60

    # --- Test override ---
    test_database_url: str | None = None

    @property
    def r2_enabled(self) -> bool:
        return all(
            [
                self.r2_account_id,
                self.r2_access_key_id,
                self.r2_secret_access_key,
                self.r2_endpoint,
            ]
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached singleton. Re-read by calling :func:`reset_settings` (tests)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
