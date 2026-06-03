import logging
import json
from typing import Optional, Any
import redis
from shared.config.settings import settings

logger = logging.getLogger(__name__)

class RedisCache:
    """
    Sử dụng Redis để cache kết quả dự đoán của mô hình, tránh việc tính toán 
    hoặc truy xuất MLflow liên tục cho cùng một mã tài sản trong một phiên giao dịch.
    """
    def __init__(self):
        try:
            self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            logger.info("Successfully connected to Redis cache.")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            self.client = None

    def get(self, key: str) -> Optional[Any]:
        """Gets data from cache."""
        if not self.client:
            return None
        try:
            val = self.client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.error(f"Redis get error: {str(e)}")
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Sets data in cache with a TTL (default: 5 minutes)."""
        if not self.client:
            return False
        try:
            serialized = json.dumps(value)
            self.client.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {str(e)}")
            return False

# Singleton instance
redis_cache = RedisCache()
