from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.query.filter import Tag
from redisvl.utils.vectorize import CustomVectorizer

from app.core.config import settings
from app.core.log_config import get_logger

logger = get_logger(__name__)

_CACHE_NAME ="rag_semantic_cache"
_SCOPE_FIELD = "permission_scope"

def _scope_key(permission_scope:list[str])->str:
    #rediSearch的字段是任一有命中的语义，权限要保证完全一致，所以需要将权限做HASH，变成唯一字符串
    #排序是为了确保顺序不同的权限集合的HASH也是一致的
    canonical = "\x00".join(sorted(permission_scope))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def _stub_embed(text:str,**_:object)->list[float]:
    return [0.0]*settings.embedding_dim

@dataclass(frozen=True)
class CachedAnswer:
    answer:str
    citations:list[dict]
    cached_question:str

class SemanticCacheService:
    def __init__(self)->None:
        self._cache = SemanticCache(
            name=_CACHE_NAME,
            redis_url=settings.redis_url,
            distance_threshold=1.0 - settings.semantic_cache_min_similarity,
            #缓存存活时间
            ttl=settings.semantic_cache_ttl_seconds,
            #把文本转换成向量
            vectorizer=CustomVectorizer(_stub_embed),
            #增加一个筛选字段，这个项目主要用于权限
            filterable_fields=[{"name":_SCOPE_FIELD,"type":"tag"}],
            overwrite=False
        )

    #输入问题和权限，返回缓存的数据
    async def lookup(
            self,
            query_embedding:list[float],
            permission_scope:list[str],
    )->CachedAnswer|None:
        scope = _scope_key(permission_scope)
        try:
            #query_embedding是问题，返回的是三个字段的数据，meta里面有引用
            hits = await self._cache.acheck(
                vector=query_embedding,
                filter_expression=Tag(_SCOPE_FIELD)==scope,
                num_results=1,
                return_fields=["prompt","response","metadata"]
            )
        except Exception:
            logger.exception("semantic cache look up failed ,treat as miss")
            return None

        if not hits:
            return None
        hit = hits[0]
        metadata= hit.get("metadata") or {}
        if isinstance(metadata,str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata={}
        return CachedAnswer(
            answer=hit.get("response",""),
            citations=metadata.get("citations",[]),
            cached_question = hit.get("prompt","")
        )

    #将问题，答案，问题的向量，引用和权限范围存入数据库
    async def save(
        self,*,question:str,query_embedding:list[float],
        answer:str,citations:list[dict],permission_scope:list[str]
    )->None:
        try:
            await self._cache.astore(
                prompt=question,
                response=answer,
                vector=query_embedding,
                metadata={"citations":citations},
                filters={_SCOPE_FIELD:_scope_key(permission_scope)}
            )
        except Exception:
            logger.exception("semantic cache save failed skip")

#redis异步客户端
@lru_cache(maxsize=1)
def get_semantic_cache()->SemanticCacheService:
    return SemanticCacheService()