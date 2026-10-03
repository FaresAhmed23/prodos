from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://prodos:prodos@localhost:5432/prodos"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_frames: str = "prodos/sensors/+/frames"
    mqtt_topic_events: str = "prodos/events"
    retention_days: int = 7

    # F-5. The key is the switch: absent -> template provider, present -> LLM.
    llm_api_base: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    # Hard ceiling on the LLM call. Alerts must not wait on a model any longer
    # than this before falling back to the template.
    llm_timeout: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()