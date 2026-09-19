from functools import lru_cache
import time
from uuid import uuid4

from app.core.config import settings
from app.core.log_config import get_logger
from app.core.exceptions import RateLimitedError
from app.core.redis import get_redis

logger = get_logger(__name__)
_WINDOW_SECONDS =60

class RateLimiter:
    def __init__(self)->None:
        self._redis = get_redis()

    #identity是用户的ID
    async def check(self,identity:str)->None:
        now = time.time()
        key = f"tag:rate_limit:{identity}"
        async with self._redis.pipeline(transaction=True) as pipe:
            #把所有score小于60秒前的成员清掉
            await pipe.zremrangebyscore(key,0,now-_WINDOW_SECONDS)
            #当前窗口的请求数
            await pipe.zcard(key)
            await pipe.zadd(key,{str(uuid4()):now})
            #60秒后自动过期
            await pipe.expire(key,_WINDOW_SECONDS)
            _,count,*_ = await pipe.execute()
        limit = settings.rate_limit_per_minute
        if int(count)>=limit:
            logger.warning(
                "rate limit exceeded identity=%s count=%s limit=%s",
                identity,
                count,limit,
            )
            raise RateLimitedError(
                f"请求过于频繁，每分钟最多{limit}次 请稍后再试"
            )

@lru_cache(maxsize=1)
def get_rate_limiter()->RateLimiter:
    return RateLimiter()