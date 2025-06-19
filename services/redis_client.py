from dotenv import load_dotenv
from typing import Callable, Any
import json
import os
import redis

load_dotenv()

class RedisClient:
    def __init__(self):
        self.redis = redis.Redis.from_url(
            os.getenv("REDISCLOUD_URL"),
            decode_responses=True
        )

    def cache_for_key(self, key: str, func: Callable[[], Any], ttl: int = 900) -> Any:
        try:
            cached = self.redis.get(key)
            if cached is not None:
                return json.loads(cached)
        except (redis.RedisError, json.JSONDecodeError):
            pass  # fall through to recompute

        result = func()
        try:
            self.redis.setex(key, ttl, json.dumps(result))
        except (redis.RedisError, TypeError):
            pass  # cache silently fails

        return result
