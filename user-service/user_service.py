# user-service/user_service.py (수정 후)
import aiohttp
import logging
import random
from aiohttp import web
from cache_service import CacheService
from database_service import UserServiceDatabase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('UserService')

db = UserServiceDatabase()
cache = CacheService()
ANALYTICS_API_URL = "http://analytics-service:8004/logs" # docker-compose 내부 주소

async def log_activity(endpoint, method, status, user_id=None):
    """활동 로그를 Analytics 서비스로 전송합니다."""
    log_data = {
        "endpoint": endpoint, "method": method, "status_code": status,
        "user_id": user_id, "server_instance": "user-service"
    }
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(ANALYTICS_API_URL, json=log_data)
    except Exception as e:
        logger.error(f"Failed to send log to analytics service: {e}")

# --- API 핸들러들 ---

async def handle_health(request: web.Request) -> web.Response:
    """서비스의 상태(DB, Cache)를 확인하는 엔드포인트"""
    db_ok = await db.health_check()
    cache_ok = await cache.ping() # cache_service에 이미 ping 메서드가 존재합니다.

    if db_ok and cache_ok:
        status = {
            "status": "healthy",
            "dependencies": {
                "database": "ok",
                "cache": "ok"
            }
        }
        return web.json_response(status, status=200)
    else:
        status = {
            "status": "unhealthy",
            "dependencies": {
                "database": "ok" if db_ok else "error",
                "cache": "ok" if cache_ok else "error"
            }
        }
        # 서비스가 준비되지 않았음을 알리기 위해 503 코드를 반환합니다.
        return web.json_response(status, status=503)

async def handle_stats(request: web.Request) -> web.Response:
    """[ROLLBACK] 서비스 및 의존성(DB, Cache) 상태 통계를 다시 반환합니다."""
    db_ok = await db.health_check()
    cache_ok = await cache.ping()

    # 캐시 히트율을 시뮬레이션합니다.
    simulated_hit_rate = random.uniform(85.0, 98.0) if cache_ok else 0.0

    stats_data = {
        "user_service": {
            "service_status": "online"
        },
        "database": {
            "status": "healthy" if db_ok else "unhealthy"
        },
        "cache": {
            "status": "healthy" if cache_ok else "unhealthy",
            "hit_ratio": round(simulated_hit_rate, 2)
        }
    }
    return web.json_response(stats_data)

async def get_user_handler(request: web.Request) -> web.Response:
    username = request.match_info['username']

    cached_user = await cache.get_user(username)
    if cached_user:
        logger.info(f"Cache HIT for user: {username}")
        await log_activity(f"/users/{username}", "GET", 200)
        return web.json_response(cached_user)

    logger.info(f"Cache MISS for user: {username}")
    # 2. 캐시에 없으면 DB에서 조회
    user_from_db = await db.get_user_by_username(username)

    if not user_from_db:
        await log_activity(f"/users/{username}", "GET", 404)
        return web.json_response({'error': 'User not found'}, status=404)

    # 3. DB에서 가져온 데이터를 캐시에 저장
    user_response = {"id": user_from_db["id"], "username": user_from_db["username"]}
    await cache.set_user(username, user_response)

    await log_activity(f"/users/{username}", "GET", 200, user_id=user_response["id"])
    return web.json_response(user_response)

async def verify_credentials_handler(request: web.Request) -> web.Response:
    """Auth-Service의 요청을 받아 자격 증명을 확인합니다."""
    data = await request.json()
    username = data.get('username')
    password = data.get('password')
    user = await db.verify_user_credentials(username, password)

    # 로그인 시도 로그 기록
    await log_activity("/users/verify-credentials", "POST", 200 if user else 401)

    if user:
        return web.json_response(user, status=200)
    else:
        return web.json_response({'error': 'Invalid credentials'}, status=401)


def create_app():
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)
    app.router.add_get("/users/{username}", get_user_handler)
    app.router.add_post("/users/verify-credentials", verify_credentials_handler)
    return app

if __name__ == "__main__":
    app = create_app()
    web.run_app(app, port=8001)