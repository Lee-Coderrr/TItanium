import asyncio
import time
from datetime import datetime
from collections import deque
from aiohttp import web, ClientSession, ClientTimeout
import logging
import os


# --- 설정 클래스 (config.py에서 가져오는 대신, 여기서 직접 정의하여 독립성 강화) ---
class AppConfig:
    HOST = '0.0.0.0'
    PORT = 7100
    API_GATEWAY_URL = 'http://api-gateway-service:8000'
    DASHBOARD_UI_URL = 'http://dashboard-ui-service:80'
    HEALTH_CHECK_INTERVAL = 15
    REQUEST_TIMEOUT = 30
    # [추가됨] API 게이트웨이와 공유할 비밀 키. 환경 변수에서 가져옵니다.
    INTERNAL_API_SECRET = os.getenv('INTERNAL_API_SECRET', 'default-secret')


config = AppConfig()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# --- 헬스 체크 로직 (백엔드 서비스 상태를 주기적으로 확인) ---
class HealthChecker:
    def __init__(self, backend_url, session):
        self.backend_url = backend_url
        self.session = session
        self.is_healthy = True
        self.logger = logging.getLogger('HealthChecker')
        self.task = asyncio.create_task(self._check_loop())

    async def _check_loop(self):
        while True:
            try:
                # API Gateway의 헬스체크 엔드포인트를 호출합니다.
                # 헬스 체크 요청에는 비밀 키가 필요 없습니다.
                async with self.session.get(f"{self.backend_url}/health", timeout=5) as response:
                    self.is_healthy = response.status == 200
            except Exception:
                self.is_healthy = False

            status = "HEALTHY" if self.is_healthy else "UNHEALTHY"
            self.logger.info(f"Backend ({self.backend_url}) status: {status}")
            await asyncio.sleep(config.HEALTH_CHECK_INTERVAL)


# --- 로드 밸런서 메인 클래스 ---
class SmartLoadBalancer:
    def __init__(self):
        self.session = ClientSession(timeout=ClientTimeout(total=config.REQUEST_TIMEOUT))
        self.health_checker = HealthChecker(config.API_GATEWAY_URL, self.session)
        self.logger = logging.getLogger('SmartLoadBalancer')

        # 통계 정보
        self.start_time = time.time()
        self.total_requests = 0
        self.failed_requests = 0
        self.request_timestamps = deque(maxlen=200)

    # [핵심] 요청을 경로에 따라 분기하는 핸들러
    async def handle_request(self, request: web.Request) -> web.Response:
        self.total_requests += 1
        self.request_timestamps.append(time.time())

        path = request.path

        # 1. 로드밸런서 자체 엔드포인트 처리
        if path == '/lb-stats':
            return await self.handle_lb_stats(request)

        # 2. UI 관련 요청은 dashboard-ui 서비스로 프록시
        if path == '/' or path.startswith('/script.js') or path.startswith('/style.css'):
            return await self.proxy_request(config.DASHBOARD_UI_URL, request)

        # 3. 그 외 모든 요청은 api-gateway로 프록시
        else:
            if self.health_checker.is_healthy:
                return await self.proxy_request(config.API_GATEWAY_URL, request)
            else:
                self.failed_requests += 1
                return web.Response(status=503, text="Service Unavailable: API Gateway is down.")

    # 백엔드로 요청을 전달하는 프록시 메서드
    async def proxy_request(self, target_base_url: str, request: web.Request) -> web.Response:
        target_url = f"{target_base_url}{request.path_qs}"
        try:
            headers = dict(request.headers)
            body = await request.read()

            # [핵심 수정!] 목표가 API 게이트웨이일 경우, 내부 비밀 키 헤더를 추가합니다.
            if target_base_url == config.API_GATEWAY_URL:
                headers['X-Internal-Secret'] = config.INTERNAL_API_SECRET

            async with self.session.request(
                    request.method, target_url, headers=headers, data=body
            ) as response:
                response_body = await response.read()
                response_headers = dict(response.headers)
                response_headers['Access-Control-Allow-Origin'] = '*'
                return web.Response(
                    body=response_body, status=response.status, headers=response_headers
                )
        except Exception as e:
            self.failed_requests += 1
            self.logger.error(f"Proxy request to {target_url} failed: {e}")
            return web.Response(status=502, text="Bad Gateway")

    # 로드밸런서 자체 통계를 반환하는 핸들러
    async def handle_lb_stats(self, request: web.Request) -> web.Response:
        uptime = time.time() - self.start_time
        now = time.time()
        recent_requests_count = sum(1 for ts in self.request_timestamps if now - ts <= 10)
        rps = recent_requests_count / 10.0
        success_rate = ((self.total_requests - self.failed_requests) / max(self.total_requests, 1)) * 100

        stats = {
            'load_balancer': {
                'total_requests': self.total_requests,
                'success_rate': round(success_rate, 2),
                'requests_per_second': round(rps, 2),
            },
            'health_check': {
                'backend_servers': 1,
                'healthy_servers': 1 if self.health_checker.is_healthy else 0,
                'server_details': {
                    config.API_GATEWAY_URL: {
                        'healthy': self.health_checker.is_healthy,
                        'avg_response_time': 0
                    }
                }
            },
            'timestamp': datetime.now().isoformat()
        }
        return web.json_response(stats)

    async def cleanup(self):
        await self.session.close()


# --- 애플리케이션 시작점 ---
async def main():
    lb = SmartLoadBalancer()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", lb.handle_request)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()

    logging.info(f"Smart Load Balancer (Reverse Proxy) started at http://{config.HOST}:{config.PORT}")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await lb.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server shutting down.")
