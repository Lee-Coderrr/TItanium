# load-balancer/load-balancer.py
import asyncio
import time
from datetime import datetime
from collections import deque
from aiohttp import web, ClientSession, ClientTimeout
import logging
from config import config

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
                async with self.session.get(f"{self.backend_url}/health", timeout=5) as response:
                    self.is_healthy = response.status == 200
            except Exception:
                self.is_healthy = False
            status = "HEALTHY" if self.is_healthy else "UNHEALTHY"
            self.logger.info(f"Backend status ({self.backend_url}): {status}")
            await asyncio.sleep(config.HEALTH_CHECK_INTERVAL)


class ReverseProxy:
    """경로 기반 라우팅 및 통계 수집 기능을 갖춘 리버스 프록시"""

    def __init__(self):
        self.session = ClientSession(timeout=ClientTimeout(total=config.REQUEST_TIMEOUT))
        self.health_checker = HealthChecker(config.API_GATEWAY_URL, self.session)
        self.logger = logging.getLogger('ReverseProxy')
        self.start_time = time.time()
        self.total_requests, self.failed_requests = 0, 0
        self.request_timestamps = deque(maxlen=200)
        self.api_response_times = deque(maxlen=100)
        self.logger.info("Reverse Proxy initialized.")

    async def handle_request(self, request: web.Request) -> web.Response:
        self.total_requests += 1
        self.request_timestamps.append(time.time())
        path = request.path

        if path == '/stats':
            return await self.handle_aggregate_stats(request)

        if path == '/lb-health':
            return await self.handle_lb_health(request)

        if path == '/lb-stats':
            return await self.get_proxy_stats(request)

        api_paths = ('/health', '/login', '/profile', '/cache', '/logout', '/admin', '/blog', '/api')
        if path.startswith(api_paths):
            if self.health_checker.is_healthy:
                return await self.proxy_request(config.API_GATEWAY_URL, request)
            else:
                self.failed_requests += 1
                return web.Response(status=503, text="Service Unavailable: API Gateway is down.")
        else:
            return await self.proxy_request(config.DASHBOARD_UI_URL, request)

    async def proxy_request(self, target_base_url: str, request: web.Request) -> web.Response:
        target_url = f"{target_base_url}{request.path_qs}"
        req_start_time = time.time()

        try:
            headers = dict(request.headers)
            headers['X-Forwarded-For'] = request.remote or 'N/A'
            if target_base_url == config.API_GATEWAY_URL:
                headers['X-Internal-Secret'] = config.INTERNAL_API_SECRET

            async with self.session.request(request.method, target_url, headers=headers,
                                            data=await request.read()) as response:
                duration = time.time() - req_start_time
                if target_base_url == config.API_GATEWAY_URL:
                    self.api_response_times.append(duration)
                response_headers = dict(response.headers)
                response_headers['Access-Control-Allow-Origin'] = '*'
                return web.Response(body=await response.read(), status=response.status, headers=response_headers)
        except Exception as e:
            self.failed_requests += 1
            self.logger.error(f"Proxy request to {target_url} failed: {e}")
            return web.Response(status=502, text="Bad Gateway")

    async def handle_aggregate_stats(self, request: web.Request) -> web.Response:
        """API 게이트웨이로부터 백엔드 통계를 받고, 자신의 통계를 합쳐 반환합니다."""
        try:
            # 1. API 게이트웨이에 백엔드 통계를 요청합니다.
            async with self.session.get(f"{config.API_GATEWAY_URL}/stats") as response:
                if response.status != 200:
                    return web.json_response({"error": "Failed to fetch stats from API Gateway"},
                                             status=response.status)
                backend_stats = await response.json()

            # 2. 자신의 통계 데이터를 가져옵니다.
            lb_stats = self._get_proxy_stats_dict()

            # 3. 두 통계 데이터를 병합합니다.
            combined_stats = {**backend_stats, **lb_stats}
            return web.json_response(combined_stats)

        except Exception as e:
            self.logger.error(f"Failed to aggregate all stats: {e}")
            return web.json_response({"error": "Internal error during stats aggregation"}, status=500)

    def _get_proxy_stats_dict(self) -> dict:
        """내부 로직에서 사용할 수 있도록 통계 정보를 딕셔너리로 반환합니다."""
        now = time.time()
        rps = sum(1 for ts in self.request_timestamps if now - ts <= 10) / 10.0
        success_rate = ((self.total_requests - self.failed_requests) / max(self.total_requests, 1)) * 100
        avg_response_time_ms = (sum(self.api_response_times) / len(
            self.api_response_times)) * 1000 if self.api_response_times else 0
        stats = {
            'load-balancer': {'total_requests': self.total_requests, 'success_rate': round(success_rate, 2),
                              'requests_per_second': round(rps, 2),
                              'avg_response_time_ms': round(avg_response_time_ms, 2)},
            # health_check 정보는 이제 Prometheus가 담당하므로 제거하거나 단순화할 수 있습니다.
            'health_check': {'api_gateway_healthy': self.health_checker.is_healthy},
            'timestamp': datetime.now().isoformat()
        }
        return stats

    async def get_proxy_stats(self, request: web.Request) -> web.Response:
        now = time.time()
        rps = sum(1 for ts in self.request_timestamps if now - ts <= 10) / 10.0
        success_rate = ((self.total_requests - self.failed_requests) / max(self.total_requests, 1)) * 100
        avg_response_time_ms = (sum(self.api_response_times) / len(
            self.api_response_times)) * 1000 if self.api_response_times else 0
        stats = {
            'load-balancer': {'total_requests': self.total_requests, 'success_rate': round(success_rate, 2),
                              'requests_per_second': round(rps, 2),
                              'avg_response_time_ms': round(avg_response_time_ms, 2)},
            'health_check': {'healthy_servers': 1 if self.health_checker.is_healthy else 0, 'server_details': {
                config.API_GATEWAY_URL: {'healthy': self.health_checker.is_healthy,
                                         'avg_response_time': round(avg_response_time_ms, 2)}}},
            'timestamp': datetime.now().isoformat()}
        return web.json_response(stats)

    async def handle_lb_health(self, request: web.Request) -> web.Response:
        """Load Balancer 자체의 상태를 반환하는 간단한 핸들러"""
        return web.json_response({'status': 'healthy', 'service': 'load-balancer'})


async def main():
    proxy = ReverseProxy()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy.handle_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    logging.info(f"Reverse Proxy started at http://{config.HOST}:{config.PORT}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server shutting down.")