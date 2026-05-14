import os


class Config:
    API_PORT: int = int(os.getenv("API_PORT", "8080"))
    BUFFER_MAX_SIZE: int = int(os.getenv("BUFFER_MAX_SIZE", "100000"))
    BUFFER_TTL_SECONDS: int = int(os.getenv("BUFFER_TTL_SECONDS", "3600"))
    MOCK_MODE: bool = os.getenv("MOCK_MODE", "false").lower() == "true"
    MOCK_INTERVAL: float = float(os.getenv("MOCK_INTERVAL", "0.5"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    MAX_RESPONSE_EVENTS: int = int(os.getenv("MAX_RESPONSE_EVENTS", "5000"))


config = Config()
