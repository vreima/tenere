from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_token: str
    mongo_url: str
    database: str
    collection: str

    model_config = SettingsConfigDict(
        env_file="tenere/.env", env_file_encoding="utf-8", extra="allow"
    )


settings = Settings()  # type: ignore
