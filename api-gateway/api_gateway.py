# api-gateway/api_gateway.py
import asyncio
import logging
import time
from aiohttp import web, ClientSession

from config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class APIGateway:
    """요청 라우팅 및 인증을 담당하는 순수 API 게이트웨이"""

    def __init__(self):
        self.logger = logging.getLogger('APIGateway')
        self.http_session = ClientSession()
        self.start_time = time.time()
        self.request_count = 0

    async def _proxy_request(self, target_url: str, request: web.Request, headers_override: dict = None):
        """요청을 지정된 URL로 전달하는 프록시 헬퍼 함수"""
        headers = headers_override if headers_override is not None else dict(request.headers)
        headers.pop('Host', None)

        try:
            async with self.http_session.request(
                    request.method,
                    target_url,
                    headers=headers,
                    data=await request.read()
            ) as response:
                return web.Response(
                    body=await response.read(),
                    status=response.status,
                    headers=response.headers
                )
        except Exception as e:
            self.logger.error(f"Proxy request to {target_url} failed: {e}")
            return web.json_response({'error': 'Service communication error'}, status=503)

    async def _validate_token(self, request: web.Request):
        """auth-service를 호출하여 토큰의 유효성을 검사합니다."""
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        validate_url = f"{config.services.auth_service}/validate"
        try:
            async with self.http_session.get(validate_url, headers={'Authorization': auth_header}) as auth_resp:
                if auth_resp.status == 200:
                    return await auth_resp.json()
                return None
        except Exception:
            return None

    # --- API 핸들러 ---

    async def handle_login(self, request: web.Request):
        """로그인 요청은 auth-service로 직접 전달합니다."""
        self.request_count += 1
        login_url = f"{config.services.auth_service}{request.path_qs}"
        return await self._proxy_request(login_url, request)

    async def handle_profile(self, request: web.Request):
        """프로필 요청은 인증 확인 후 user-service로 전달합니다."""
        self.request_count += 1
        auth_data = await self._validate_token(request)
        if not auth_data or not auth_data.get('valid'):
            return web.json_response({'error': 'Authentication required'}, status=401)

        user_id = auth_data.get('user_id')
        profile_url = f"{config.services.user_service}/users/id/{user_id}"
        return await self._proxy_request(profile_url, request, headers_override=dict(request.headers))

    async def handle_stats(self, request: web.Request):
        """각 서비스에서 통계를 수집하여 취합합니다."""
        self.request_count += 1
        try:
            user_stats_task = self.http_session.get(f"{config.services.user_service}/stats")
            auth_stats_task = self.http_session.get(f"{config.services.auth_service}/stats")
            responses = await asyncio.gather(user_stats_task, auth_stats_task)

            user_stats = await responses[0].json() if responses[0].status == 200 else {}
            auth_stats = await responses[1].json() if responses[1].status == 200 else {}

            uptime = time.time() - self.start_time
            rps = self.request_count / uptime if uptime > 0 else 0

            final_stats = {
                'api_gateway': {'total_requests': self.request_count, 'requests_per_second': round(rps, 2)},
                **user_stats,
                **auth_stats
            }
            return web.json_response(final_stats)
        except Exception as e:
            self.logger.error(f"Error aggregating stats: {e}")
            return web.json_response({'error': 'Failed to aggregate stats'}, status=500)

    async def handle_health(self, request: web.Request):
        """게이트웨이 자체의 상태를 반환합니다 (실제 운영에서는 다운스트림 서비스 헬스체크 포함)."""
        return web.json_response({'status': 'healthy'})


# --- 애플리케이션 설정 및 실행 ---
async def main():
    gateway = APIGateway()
    app = web.Application()

    app.router.add_get("/health", gateway.handle_health)
    app.router.add_post("/login", gateway.handle_login)
    app.router.add_get("/profile", gateway.handle_profile)
    app.router.add_get("/stats", gateway.handle_stats)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.port)
    await site.start()

    logging.info(f"✅ API Gateway started on http://{config.server.host}:{config.server.port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("API Gateway shutting down.")
