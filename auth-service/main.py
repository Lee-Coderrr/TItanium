# auth-service/main.py
import asyncio
import logging
from aiohttp import web, ClientSession

from config import config
from auth_service import AuthService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AuthServiceApp')


# --- 핸들러 함수들 ---

async def handle_login(request: web.Request) -> web.Response:
    auth_service = request.app['auth_service']
    data = await request.json()
    result = await auth_service.authenticate(data.get('username'), data.get('password'))
    return web.json_response(result, status=200 if result.get('success') else 401)


async def validate_token(request: web.Request) -> web.Response:
    auth_service = request.app['auth_service']
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return web.json_response({'valid': False, 'error': 'Authorization header missing or invalid'}, status=400)

    token = auth_header[7:]
    result = await auth_service.validate_session(token)
    return web.json_response(result, status=200 if result.get('valid') else 401)


async def handle_stats(request: web.Request) -> web.Response:
    auth_service = request.app['auth_service']
    stats = await auth_service.get_active_sessions()
    return web.json_response({'auth': stats})


# --- aiohttp 앱 생명주기 관리 ---

async def app_context(app):
    """앱 시작 시 AuthService 인스턴스를 생성하고, 종료 시 정리합니다."""
    http_session = ClientSession()
    app['auth_service'] = AuthService(http_session)
    yield
    await http_session.close()


# --- 메인 실행 함수 ---

async def main():
    app = web.Application()
    app.cleanup_ctx.append(app_context)

    app.router.add_post("/login", handle_login)
    app.router.add_get("/validate", validate_token)
    app.router.add_get("/stats", handle_stats)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.port)
    await site.start()

    logger.info(f"✅ Auth Service started on http://{config.server.host}:{config.server.port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Auth Service shutting down.")
