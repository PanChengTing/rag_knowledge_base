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

    #agent rag的配置项
    #是否启用agent循环
    agent_loop_enabled:bool = True
    #最大循环次数
    agent_loop_max_rounds:int = 3

    #重排的相关参数
    rerank_enabled:bool = True
    rerank_base_url:str = (
        "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    )
    rerank_model:str = "qwen3-rerank"
    rerank_api_key:str ="" #留空的时候复用chat_api_key
    rerank_min_score:float = 0.3 #相关度阈值，一般再【0，1】0.3是经验值
    rerank_timeout:float = 8.0 #请求超时

    #答案校验
    verify_answer_enabled:bool = True
    #可观测性
    langsmith_tracing:bool=False
    langsmith_api_key:str=""
    langsmith_project:str="rag-knowledge-base"
    langsmith_endpoint:str="https://api.smith.langchain.com"
    langsmith_run_url_prefix:str =""

    #认证签名密钥
    jwt_secret:str =""
    jwt_algorithm:str = "HS256"
    #过期时间
    jwt_expire_minutes:int = 1440

    default_admin_username:str="admin"
    default_admin_password:str="admin"
    default_admin_display_name:str="管理员"

    cors_origins:str= ""
    @property
    def cors_origin_list(self)->list[str]:
        return [o.strip  for o in self.cors_origins.split(",") if o.strip()]
    @property
    def observablility_enabled(self)->bool:
        return bool(self.langsmith_tracing and self.langsmith_api_key)
    @property
    def cos_configured(self)->bool:
        return bool(self.cos_secret_id and self.cos_secret_key and self.cos_bucket)
    @property
    def effective_rerank_api_key(self)->str:
        return self.rerank_api_key or self.chat_api_key
    
@lru_cache(maxsize=1)
def get_settings()->Settings:
    return Settings()

settings = get_settings()