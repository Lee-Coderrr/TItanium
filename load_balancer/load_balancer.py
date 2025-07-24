import asyncio
from aiohttp import web, ClientSession, ClientTimeout
from config import config  # 수정된 config를 import 합니다.
import logging

# 로깅 설정은 그대로 유지
logging.basicConfig(level=logging.INFO)

class ReverseProxy:
    def __init__(self):
        self.api_gateway_url = config.load_balancer.api_gateway_url
        self.dashboard_ui_url = config.load_balancer.dashboard_ui_url
        self.session = ClientSession(timeout=ClientTimeout(total=30))
        self.logger = logging.getLogger('ReverseProxy')
        self.logger.info("리버스 프록시 초기화 완료")
        self.logger.info(f"API Gateway 백엔드: {self.api_gateway_url}")
        self.logger.info(f"Dashboard UI 백엔드: {self.dashboard_ui_url}")

    async def handle_request(self, request: web.Request) -> web.Response:
        target_url = ""
        # 요청 경로에 따라 목표 URL을 분기합니다.
        if request.path == '/':
            target_url = f"{self.dashboard_ui_url}{request.path_qs}"
            self.logger.info(f"Dashboard 요청 라우팅: {target_url}")
        else:
            # 그 외 모든 요청은 API 게이트웨이로 보냅니다.
            target_url = f"{self.api_gateway_url}{request.path_qs}"
            self.logger.info(f"API 요청 라우팅: {target_url}")

        try:
            headers = dict(request.headers)
            body = await request.read()

            async with self.session.request(
                request.method, target_url, headers=headers, data=body
            ) as response:
                response_body = await response.read()
                return web.Response(
                    body=response_body,
                    status=response.status,
                    headers=response.headers
                )
        except Exception as e:
            self.logger.error(f"백엔드 연결 오류: {e}")
            return web.Response(status=502, text="Bad Gateway")

    async def cleanup(self):
        await self.session.close()

async def start_load_balancer():
    proxy = ReverseProxy()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy.handle_request)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.load_balancer.host, config.load_balancer.port)
    await site.start()

    logging.info(f"리버스 프록시 시작: http://{config.load_balancer.host}:{config.load_balancer.port}")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await proxy.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(start_load_balancer())
    except KeyboardInterrupt:
        logging.info("리버스 프록시 종료.")