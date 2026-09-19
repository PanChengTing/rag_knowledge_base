from functools import lru_cache

import redis.asyncio as aioredis

from app.core.config import settings

#redis异步客户端
@lru_cache(maxsize=1)
def get_redis()->aioredis.Redis:
    return aioredis.from_url(settings.redis_url,decode_response=True)