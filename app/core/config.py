from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：config.py 位于 app/core/ 下，上溯两级即项目根。
# 用绝对路径定位 .env，避免依赖当前工作目录导致脚本在非项目根运行时报配置缺失
BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEEPSEEK_API_KEY:str
    # LiteLLM 网关：业务代码通过网关访问 LLM，不再直连模型厂商
    LLM_GATEWAY_API_KEY: str
    LLM_GATEWAY_BASE_URL: str = "http://127.0.0.1:4000"
    LLM_GATEWAY_MODEL: str = "mimo-chat"
    # Outbox 增量同步之外的全量校验间隔（小时），用于兜底修复漏同步。
    KB_FULL_RECONCILE_INTERVAL_HOURS: int = 24
    # 事务 Outbox 的轮询频率、同一问题变更的合并窗口和单批上限。
    KB_SYNC_POLL_SECONDS: int = 1
    KB_SYNC_DEBOUNCE_SECONDS: int = 5
    KB_SYNC_BATCH_SIZE: int = 100



    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env")

settings = Settings()
