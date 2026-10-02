from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://prodos:prodos@localhost:5432/prodos"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_frames: str = "prodos/sensors/+/frames"
    retention_days: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()