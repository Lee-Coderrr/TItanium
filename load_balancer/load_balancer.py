# load_balancer/load_balancer.py
import asyncio
import time
from datetime import datetime
from collections import deque
from aiohttp import web, ClientSession, ClientTimeout
import logging

# 분리된 설정 파일을 임포트합니다.
from config import config

# 기본 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class HealthChecker:
    """백엔드 서비스의 상태를 주기적으로 확인합니다."""

    def __init__(self, backend_url: str, session: ClientSession):
        self.backend_url = backend_url
        self.session = session
        self.is_healthy = True
        self.logger = logging.getLogger('HealthChecker')
        self.task = asyncio.create_task(self._check_loop())
        self.logger.info(f"Health checker for {self.backend_url} started.")

    async def _check_loop(self):
        while True:
            try:
                # API 게이트웨이의 /health 엔드포인트를 호출합니다.
                async with self.session.get(f"{self.backend_url}/health", timeout=5) as response:
                    self.is_healthy = response.status == 200
            except Exception:
                self.is_healthy = False

            status = "HEALTHY" if self.is_healthy else "UNHEALTHY"
            self.logger.info(f"Backend status: {status}")
            await asyncio.sleep(config.HEALTH_CHECK_INTERVAL)


class ReverseProxy:
    """경로 기반 라우팅 및 통계 수집 기능을 갖춘 리버스 프록시"""

    def __init__(self):
        self.session = ClientSession(timeout=ClientTimeout(total=config.REQUEST_TIMEOUT))
        self.health_checker = HealthChecker(config.API_GATEWAY_URL, self.session)
        self.logger = logging.getLogger('ReverseProxy')

        # 통계 관련 속성
        self.start_time = time.time()
        self.total_requests = 0
        self.failed_requests = 0
        self.request_timestamps = deque(maxlen=200)
        self.api_response_times = deque(maxlen=100)
        self.logger.info("Reverse Proxy initialized.")

    async def handle_request(self, request: web.Request) -> web.Response:
        """모든 들어오는 요청을 처리하고 적절한 서비스로 라우팅합니다."""
        self.total_requests += 1
        self.request_timestamps.append(time.time())
        path = request.path

        # 경로에 따라 요청을 분기합니다.
        if path == '/lb-stats':
            return await self.get_proxy_stats(request)

        api_paths = ('/health, /stats', '/login', '/profile', '/cache', '/logout', '/admin')
        if path.startswith(api_paths):
            if self.health_checker.is_healthy:
                return await self.proxy_request(config.API_GATEWAY_URL, request)
            else:
                self.failed_requests += 1
                self.logger.warning("API Gateway is down. Returning 503 Service Unavailable.")
                return web.Response(status=503, text="Service Unavailable: API Gateway is down.")
        else:
            return await self.proxy_request(config.DASHBOARD_UI_URL, request)

    async def proxy_request(self, target_base_url: str, request: web.Request) -> web.Response:
        """실제 요청을 백엔드 서비스로 중계합니다."""
        target_url = f"{target_base_url}{request.path_qs}"
        req_start_time = time.time()

        try:
            headers = dict(request.headers)
            body = await request.read()

            # API 게이트웨이로 보내는 요청에만 내부 비밀 키 헤더를 추가합니다.
            if target_base_url == config.API_GATEWAY_URL:
                headers['X-Internal-Secret'] = config.INTERNAL_API_SECRET

            async with self.session.request(request.method, target_url, headers=headers, data=body) as response:
                duration = time.time() - req_start_time
                if target_base_url == config.API_GATEWAY_URL:
                    self.api_response_times.append(duration)

                response_body = await response.read()
                # CORS 헤더 추가
                response_headers = dict(response.headers)
                response_headers['Access-Control-Allow-Origin'] = '*'
                return web.Response(body=response_body, status=response.status, headers=response_headers)

        except Exception as e:
            self.failed_requests += 1
            self.logger.error(f"Proxy request to {target_url} failed: {e}")
            return web.Response(status=502, text="Bad Gateway")

    async def get_proxy_stats(self, request: web.Request) -> web.Response:
        """프록시의 현재 상태 통계를 JSON으로 반환합니다."""
        now = time.time()
        recent_requests_count = sum(1 for ts in self.request_timestamps if now - ts <= 10)
        rps = recent_requests_count / 10.0
        success_rate = ((self.total_requests - self.failed_requests) / max(self.total_requests, 1)) * 100

        avg_response_time_ms = (sum(self.api_response_times) / len(
            self.api_response_times)) * 1000 if self.api_response_times else 0

        stats = {
            'load_balancer': {
                'total_requests': self.total_requests,
                'success_rate': round(success_rate, 2),
                'requests_per_second': round(rps, 2),
                'avg_response_time_ms': round(avg_response_time_ms, 2)
            },
            'health_check': {
                'backend_servers': 1,
                'healthy_servers': 1 if self.health_checker.is_healthy else 0,
                'server_details': {
                    config.API_GATEWAY_URL: {
                        'healthy': self.health_checker.is_healthy,
                        'avg_response_time': round(avg_response_time_ms, 2)
                    }
                }
            },
            'timestamp': datetime.now().isoformat()
        }
        return web.json_response(stats)


async def main():
    """애플리케이션을 초기화하고 실행합니다."""
    proxy = ReverseProxy()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy.handle_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()

    logging.info(f"Reverse Proxy started at http://{config.HOST}:{config.PORT}")

    # 서버가 계속 실행되도록 유지
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        if not proxy.session.closed:
            await proxy.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server shutting down.")