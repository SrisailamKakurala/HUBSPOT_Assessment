from utils.env import ENV
import redis.asyncio as redis
from kombu.utils.url import safequote # type: ignore

print(ENV.REDIS_HOST)

redis_host = safequote(ENV.REDIS_HOST)
redis_client = redis.Redis(host=redis_host, port=ENV.REDIS_PORT, db=0)

async def add_key_value_redis(key, value, expire=None):
    await redis_client.set(key, value)
    if expire:
        await redis_client.expire(key, expire)

async def get_value_redis(key):
    return await redis_client.get(key)

async def delete_key_redis(key):
    await redis_client.delete(key)
