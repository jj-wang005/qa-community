from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEEPSEEK_API_KEY:str
    XIAOMI_MIMO_API_KEY: str
    # LiteLLM 网关 master key
    LITELLM_MASTER_KEY: str
    # LiteLLM 网关：业务代码通过网关访问 LLM，不再直连模型厂商
    LLM_GATEWAY_API_KEY: str
    LLM_GATEWAY_BASE_URL: str = "http://127.0.0.1:4000"
    LLM_GATEWAY_MODEL: str = "mimo-chat"
    # 离线知识库定时重建间隔（小时），默认 6 小时
    KB_REBUILD_INTERVAL_HOURS: int = 6



    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()