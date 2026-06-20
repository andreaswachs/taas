import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_path: str = os.getenv("DB_PATH", "/var/lib/taas-db/tasks.db")
    
    # Audio output
    audio_output_dir: str = os.getenv("AUDIO_OUTPUT_DIR", "/var/lib/taas-audio")
    
    # Model cache
    model_cache_dir: str = os.getenv("MODEL_CACHE_DIR", "/var/lib/taas-models")
    
    # Model configuration
    kitten_model: str = os.getenv("KITTEN_MODEL", "KittenML/kitten-tts-mini-0.8")
    sample_rate: int = int(os.getenv("SAMPLE_RATE", "24000"))
    audio_format: str = os.getenv("AUDIO_FORMAT", "wav")
    
    # Worker configuration
    max_workers: int = int(os.getenv("MAX_WORKERS", "5"))
    max_queue_depth: int = int(os.getenv("MAX_QUEUE_DEPTH", "1000"))
    
    # Text limits
    max_text_length: int = int(os.getenv("MAX_TEXT_LENGTH", "64000"))
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    
    # API versioning
    api_version: str = "v1"
    
    # Available voices from KittenTTS
    available_voices: list[str] = [
        "Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"
    ]
    
    # Default voice
    default_voice: str = "Leo"
    
    # File cleanup configuration
    audio_ttl_hours: int = int(os.getenv("AUDIO_TTL_HOURS", "12"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()