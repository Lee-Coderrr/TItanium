# api-gateway/api_gateway.py
import asyncio
import logging
import time

import aiohttp
from aiohttp import web, ClientSession

# config.py 파일에서 설정을 가져옵니다.
from config import config

# 기본 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class APIGateway:
    """
    요청 라우팅, 인증 확인, 통계 취합을 담당하는 순수 API 게이트웨이.
    모든 비즈니스 로직은 각 전문 마이크로서비스에 위임합니다.
    """

    def __init__(self):
        self.logger = logging.getLogger('APIGateway')
        self.http_session = ClientSession()
        # API 게이트웨이 자체의 간단한 통계를 위한 변수
        self.start_time = time.time()
        self.request_count = 0

    async def _proxy_request(self, target_url: str, request: web.Request):
        """요청을 지정된 URL로 그대로 전달하는 프록시 헬퍼 함수"""
        headers = dict(request.headers)
        headers.pop('Host', None)  # 호스트 헤더는 프록시 대상에 맞게 자동 설정되도록 제거

        try:
            async with self.http_session.request(
                    request.method,
                    target_url,
                    headers=headers,
                    data=await request.read()
            ) as response:
                # 백엔드 서비스의 응답을 그대로 클라이언트에게 전달
                return web.Response(
                    body=await response.read(),
                    status=response.status,
                    headers=response.headers
                )
        except Exception as e:
            self.logger.error(f"Proxy request to {target_url} failed: {e}")
            return web.json_response({'error': 'Service communication error'}, status=503)

    async def _validate_token(self, request: web.Request) -> dict | None:
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
        except Exception as e:
            self.logger.error(f"Token validation request failed: {e}")
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
        # user-service의 엔드포인트에 맞게 URL 구성
        profile_url = f"{config.services.user_service}/users/id/{user_id}"
        return await self._proxy_request(profile_url, request)

    async def handle_stats(self, request: web.Request):
        self.request_count += 1
        try:
            tasks = [
                self.http_session.get(f"{config.services.user_service}/stats"),
                self.http_session.get(f"{config.services.auth_service}/stats"),
                self.http_session.get(f"{config.services.blog_service}/stats")
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            user_resp, auth_resp, blog_resp = responses

            user_stats = (await user_resp.json()) if isinstance(user_resp, aiohttp.ClientResponse) and user_resp.status == 200 else {}
            auth_stats = (await auth_resp.json()) if isinstance(auth_resp, aiohttp.ClientResponse) and auth_resp.status == 200 else {}
            blog_stats = (await blog_resp.json()) if isinstance(blog_resp, aiohttp.ClientResponse) and blog_resp.status == 200 else {}

            uptime = time.time() - self.start_time
            rps = self.request_count / uptime if uptime > 0 else 0

            combined_stats = {
                'api_gateway': { 'total_requests': self.request_count, 'requests_per_second': round(rps, 2) },
                **user_stats, **auth_stats, **blog_stats
            }
            return web.json_response(combined_stats)
        except Exception as e:
            self.logger.error(f"Error aggregating stats: {e}")
            return web.json_response({'error': 'Failed to aggregate stats from backend services'}, status=500)

    async def handle_health(self, request: web.Request):
        """게이트웨이 자체의 상태를 반환합니다."""
        return web.json_response({'status': 'healthy'})

    async def handle_blog_service_requests(self, request: web.Request):
        """블로그 관련 모든 요청을 경로 변경 없이 blog-service로 전달합니다."""
        self.request_count += 1

        # 더 이상 경로를 변환할 필요가 없음
        target_url = f"{config.services.blog_service}{request.path_qs}"

        self.logger.info(f"Forwarding to Blog Service: '{request.path_qs}' -> '{target_url}'")
        return await self._proxy_request(target_url, request)

# --- 애플리케이션 설정 및 실행 ---
async def main():
    gateway = APIGateway()
    app = web.Application()

    # API 게이트웨이가 처리할 경로들을 정의합니다.
    app.router.add_get("/health", gateway.handle_health)
    app.router.add_post("/login", gateway.handle_login)
    app.router.add_get("/profile", gateway.handle_profile)
    app.router.add_get("/stats", gateway.handle_stats)

    app.router.add_route("*", "/blog", gateway.handle_blog_service_requests)
    app.router.add_route("*", "/blog/{path:.*}", gateway.handle_blog_service_requests)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.port)
    await site.start()

    logging.info(f"✅ API Gateway (Aggregator) started on http://{config.server.host}:{config.server.port}")
    # 서버가 계속 실행되도록 유지
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("API Gateway shutting down.")
