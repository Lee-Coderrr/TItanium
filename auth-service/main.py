import logging
from aiohttp import web

# 최신 코드를 임포트합니다.
from config import config
from auth_service import AuthService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AuthServiceApp')


# --- 핸들러 함수들 (최신 AuthService에 맞게 수정) ---

async def handle_login(request: web.Request) -> web.Response:
    """로그인 요청을 처리하고 JWT 토큰을 반환합니다."""
    auth_service = request.app['auth_service']
    try:
        data = await request.json()
        # 최신 'login' 메서드 호출
        result = await auth_service.login(data.get('username'), data.get('password'))
        status = 200 if result.get('status') == 'success' else 401
        return web.json_response(result, status=status)
    except Exception:
        return web.json_response({"status": "failed", "message": "Invalid request body"}, status=400)


async def validate_token(request: web.Request) -> web.Response:
    """토큰 유효성을 검증합니다."""
    auth_service = request.app['auth_service']
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return web.json_response({'valid': False, 'error': 'Authorization header missing or invalid'}, status=400)

    token = auth_header.split(' ')[1]
    # 최신 'verify_token' 메서드 호출
    result = auth_service.verify_token(token)
    is_valid = result.get('status') == 'success'
    return web.json_response(result, status=200 if is_valid else 401)


async def handle_health(request: web.Request) -> web.Response:
    """(추가된 부분) 헬스 체크 요청을 처리합니다."""
    # 간단하게 서비스가 살아있음을 알리는 응답을 반환합니다.
    return web.json_response({"status": "ok", "service": "auth-service"})

async def handle_stats(request: web.Request) -> web.Response:
    """서비스의 간단한 통계를 반환합니다."""
    # 현재는 활성 세션을 추적하지 않으므로 기본값을 반환합니다.
    stats_data = {
        "auth": {
            "service_status": "online",
            "active_session_count": 0
        }
    }
    return web.json_response(stats_data)


# --- aiohttp 앱 생명주기 관리 (더 간단하게 수정) ---

async def app_context(app):
    """앱 시작 시 AuthService 인스턴스를 생성합니다."""
    app['auth_service'] = AuthService()
    yield
    # 특별한 정리 로직이 없으므로 비워둡니다.


# --- 메인 실행 함수 ---

def create_app() -> web.Application:
    """웹 애플리케이션 인스턴스를 생성하고 라우팅을 설정합니다."""
    app = web.Application()
    app.cleanup_ctx.append(app_context)

    # 최신 API 엔드포인트에 맞게 라우터 재구성
    app.router.add_post("/login", handle_login)
    app.router.add_get("/verify", validate_token) # /validate 대신 /verify를 사용 (혹은 통일)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)

    return app

if __name__ == "__main__":
    app = create_app()
    port = config.server.port
    logger.info(f"✅ Auth Service starting on http://{config.server.host}:{port}")
    web.run_app(app, host=config.server.host, port=port)