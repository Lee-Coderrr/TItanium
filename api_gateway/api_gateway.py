# api-gateway/api_gateway.py
import asyncio
import logging
from aiohttp import web, ClientSession

# config도 단순화됩니다.
from config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class APIGateway:
    def __init__(self):
        self.logger = logging.getLogger('APIGateway')
        self.http_session = ClientSession()

    async def _proxy_request(self, target_url: str, request: web.Request):
        """요청을 다른 서비스로 그대로 전달합니다."""
        headers = dict(request.headers)
        # 호스트 헤더는 프록시 대상에 맞게 변경되므로 제거
        headers.pop('Host', None)

        async with self.http_session.request(
                request.method,
                f"{target_url}{request.path_qs}",
                headers=headers,
                data=await request.read()
        ) as response:
            return web.Response(
                body=await response.read(),
                status=response.status,
                headers=response.headers
            )

    async def handle_login(self, request: web.Request):
        """로그인 요청은 auth-service로 전달합니다."""
        return await self._proxy_request(config.services.auth_service, request)

    async def handle_profile(self, request: web.Request):
        """프로필 요청은 인증 확인 후 user-service로 전달합니다."""
        # 1. 토큰 유효성 검사 (auth-service 호출)
        auth_header = request.headers.get('Authorization')
        validate_url = f"{config.services.auth_service}/validate"
        async with self.http_session.get(validate_url, headers={'Authorization': auth_header}) as auth_resp:
            if auth_resp.status != 200:
                return web.json_response({'error': 'Authentication failed'}, status=401)
            auth_data = await auth_resp.json()
            user_id = auth_data.get('user_id')

        # 2. 인증 성공 시, user-service로 요청 전달
        # 실제로는 /profile/{user_id} 와 같이 경로를 수정해야 합니다.
        # 여기서는 단순화를 위해 /profile을 그대로 전달합니다.
        return await self._proxy_request(config.services.user_service, request)


async def main():
    gateway = APIGateway()
    app = web.Application()

    # 라우팅 규칙: 각 경로를 적절한 서비스로 매핑
    app.router.add_post("/login", gateway.handle_login)
    app.router.add_get("/profile", gateway.handle_profile)
    # ... 다른 라우트들도 추가 ...

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.port)
    await site.start()
    logging.info(f"✅ API Gateway started on port {config.server.port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
