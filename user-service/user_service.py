# user-service/user_service.py
import asyncio
import logging
from aiohttp import web

from config import config
from database_service import db_service
from cache_service import cache_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('UserService')


# --- API 핸들러 ---

async def handle_health(request: web.Request) -> web.Response:
    db_health = db_service.health_check()
    cache_health = await cache_service.health_check()
    is_healthy = db_health['status'] == 'healthy' and cache_health['status'] == 'healthy'
    return web.json_response({'status': 'healthy' if is_healthy else 'degraded'})

async def handle_stats(request: web.Request) -> web.Response:
    db_stats = db_service.get_statistics()
    cache_stats = await cache_service.get_stats()
    db_health = db_service.health_check()

    response_data = {
        'database': {'stats': db_stats, 'status': db_health.get('status', 'unknown')},
        'cache': cache_stats
    }
    return web.json_response(response_data)


async def get_user_by_id(request: web.Request) -> web.Response:
    user_id = int(request.match_info['user_id'])
    cache_key = f"user_profile:{user_id}"
    cached_user = await cache_service.get(cache_key)
    if cached_user:
        return web.json_response(cached_user)
    user = db_service.get_user_by_id(user_id)
    if not user:
        return web.json_response({'error': 'User not found'}, status=404)
    await cache_service.set(cache_key, user, ttl=config.cache.default_ttl)
    return web.json_response(user)


# [추가!] 사용자 이름으로 사용자를 조회하는 핸들러
async def get_user_by_username(request: web.Request) -> web.Response:
    username = request.match_info['username']
    # 캐싱은 ID 기반으로만 하므로 여기서는 직접 DB를 조회합니다.
    user = db_service.get_user(username)
    if not user:
        return web.json_response({'error': 'User not found'}, status=404)
    return web.json_response(user)


# --- 애플리케이션 설정 및 실행 ---
async def main():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)
    app.router.add_get("/users/id/{user_id}", get_user_by_id)
    # [추가!] username 조회 라우트를 추가합니다.
    app.router.add_get("/users/username/{username}", get_user_by_username)


    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.port)
    await site.start()
    logger.info(f"✅ User Service started on port {config.server.port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())