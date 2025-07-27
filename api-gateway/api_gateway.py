# api-gateway/api_gateway.py
import asyncio
import logging
import time
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
        """각 서비스에서 통계를 수집하여 취합합니다."""
        self.request_count += 1
        try:
            # 모든 서비스의 통계 엔드포인트를 동시에 호출합니다.
            tasks = [
                self.http_session.get(f"{config.services.load_balancer}/lb-stats"),
                self.http_session.get(f"{config.services.user_service}/stats"),
                self.http_session.get(f"{config.services.auth_service}/stats")
            ]
            # 한 서비스가 다운되어도 전체가 실패하지 않도록 return_exceptions=True 사용
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            lb_resp, user_resp, auth_resp = responses

            # 각 응답을 JSON으로 변환하고, 실패 시 빈 객체로 처리합니다.
            lb_stats = (await lb_resp.json()) if isinstance(lb_resp,
                                                            web.ClientResponse) and lb_resp.status == 200 else {}
            user_stats = (await user_resp.json()) if isinstance(user_resp,
                                                                web.ClientResponse) and user_resp.status == 200 else {}
            auth_stats = (await auth_resp.json()) if isinstance(auth_resp,
                                                                web.ClientResponse) and auth_resp.status == 200 else {}

            # API 게이트웨이 자체 통계 계산
            uptime = time.time() - self.start_time
            rps = self.request_count / uptime if uptime > 0 else 0

            # 모든 통계 정보를 하나의 객체로 병합합니다.
            combined_stats = {
                'api_gateway': {
                    'total_requests': self.request_count,
                    'requests_per_second': round(rps, 2)
                },
                **lb_stats,
                **user_stats,
                **auth_stats
            }
            return web.json_response(combined_stats)
        except Exception as e:
            self.logger.error(f"Error aggregating stats: {e}")
            return web.json_response({'error': 'Failed to aggregate stats from backend services'}, status=500)

    async def handle_health(self, request: web.Request):
        """게이트웨이 자체의 상태를 반환합니다."""
        return web.json_response({'status': 'healthy'})


# --- 애플리케이션 설정 및 실행 ---
async def main():
    gateway = APIGateway()
    app = web.Application()

    # API 게이트웨이가 처리할 경로들을 정의합니다.
    app.router.add_get("/health", gateway.handle_health)
    app.router.add_post("/login", gateway.handle_login)
    app.router.add_get("/profile", gateway.handle_profile)
    app.router.add_get("/stats", gateway.handle_stats)

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
