import redis.asyncio as redis
import json
import logging
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        try:
            self.redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
            logger.info(f"Cache service initialized and connected to Redis at {config.REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    async def get_user(self, user_id):
        if not self.redis_client:
            return None
        try:
            user_data = await self.redis_client.get(f"user:{user_id}")
            if user_data:
                logger.info(f"Cache HIT for user ID: {user_id}")
                return json.loads(user_data)
            logger.info(f"Cache MISS for user ID: {user_id}")
            return None
        except Exception as e:
            logger.error(f"Redis GET error for user ID {user_id}: {e}")
            return None

    async def set_user(self, user_id, user_data, expiration_secs=3600):
        if not self.redis_client:
            return
        try:
            await self.redis_client.set(
                f"user:{user_id}",
                json.dumps(user_data),
                ex=expiration_secs
            )
            logger.info(f"Cached data for user ID: {user_id} with {expiration_secs}s expiry.")
        except Exception as e:
            logger.error(f"Redis SET error for user ID {user_id}: {e}")

    async def clear_user(self, user_id):
        if not self.redis_client:
            return
        try:
            await self.redis_client.delete(f"user:{user_id}")
            logger.info(f"Cleared cache for user ID: {user_id}")
        except Exception as e:
            logger.error(f"Redis DEL error for user ID {user_id}: {e}")

    async def ping(self):
        if not self.redis_client:
            return False
        try:
            return await self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis PING error: {e}")
            return False