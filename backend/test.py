import asyncio
from redis_client import add_key_value_redis, get_value_redis

async def test():
    await add_key_value_redis("mykey", "myvalue", 60)
    val = await get_value_redis("mykey")
    print(val)

asyncio.run(test())
