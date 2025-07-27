# auth-service/main.py
import asyncio
import logging
from aiohttp import web, ClientSession

from config import config
# auth_service.py는 이제 이 서비스의 일부입니다.
from auth_service import AuthService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AuthServiceApp')


# --- API 핸들러 ---

# AuthService 인스턴스를 app 컨텍스트에 저장하여 공유
async def get_auth_service(app):
    # AuthService는 이제 User Service와 통신해야 합니다.
    http_session = ClientSession()
    app['auth_service'] = AuthService(http_session)
    yield
    await http_session.close()


async def handle_login(request: web.Request) -> web.Response:
    auth_service = request.app['auth_service']
    data = await request.json()
    ip_address = request.remote or 'N/A'
    result = await auth_service.authenticate(
        data.get('username'), data.get('password'), ip_address
    )
    status = 200 if result.get('success') else 401
    return web.json_response(result, status=status)


async def validate_token(request: web.Request) -> web.Response:
    auth_service = request.app['auth_service']
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return web.json_response({'valid': False, 'error': 'Invalid header'}, status=400)

    token = auth_header[7:]
    result = await auth_service.validate_session(token)
    status = 200 if result.get('valid') else 401
    return web.json_response(result, status=status)


# --- 애플리케이션 설정 및 실행 ---
async def main():
    app = web.Application()
    app.cleanup_ctx.append(get_auth_service)  # 앱 시작/종료 시 서비스 생성/정리

    app.router.add_post("/login", handle_login)
    app.router.add_get("/validate", validate_token)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.port)
    await site.start()
    logger.info(f"✅ Auth Service started on port {config.server.port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    # auth_service.py를 수정해야 합니다.
    # 기존 db_service import를 제거하고, aiohttp ClientSession을 통해
    # user-service를 호출하도록 변경해야 합니다.
    asyncio.run(main())
