from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings,SettingsConfigDict
PROJECT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file = PROJECT_ROOT/".env",
        env_file_encoding = "utf-8",
        extra = "ignore",
        case_sensitive = False, #不区分大小写
    )

    #embedding相关设置
    embedding_api_key:str=""
    embedding_base_url:str = ""
    embedding_model:str="text-embedding-v3"

    #embedding维度和BATCH_SIZE
    embedding_dim:int = 1024
    embedding_batch_size:int = 10

    #文档切分的大小
    upload_max_size_mb:int =50
    chunk_size:int =600
    chunk_overlap:int=60

    app_name:str= "rag-knowledge-base"
    log_level:str = "INFO"
    database_url:str = "postgresql+asyncpg://rag:rag@localhost:5432/rag_kb"

    #COS存储桶的参数
    cos_secret_id:str=""
    cos_secret_key:str=""
    cos_region:str=""
    cos_bucket:str=""

    #问答模型的参数
    chat_api_key:str=""
    chat_base_url:str=""
    chat_model:str=""

    #检索TOP-K 交给LLM的chunk数量
    retrieval_top_k:int=5
    #TOP-K中的最高分低于此阈值，拒绝回答
    retrievl_min_score:float=0.6
    #多轮窗口
    chat_history_window:int =5
    #是否打开查询优化
    query_route_enabled:bool = True
    #最大的子查询数量
    multi_query_count:int = 3

    #rrf融合算法中的常量
    rrf_k:int = 60
    #每路关键词的召回数量
    retrieval_recall_top_k:int = 20

    cors_origins:str= ""
    @property
    def cors_origin_list(self)->list[str]:
        return [o.strip  for o in self.cors_origins.split(",") if o.strip()]
    
    @property
    def cos_configured(self)->bool:
        return bool(self.cos_secret_id and self.cos_secret_key and self.cos_bucket)
    
@lru_cache(maxsize=1)
def get_settings()->Settings:
    return Settings()

settings = get_settings()