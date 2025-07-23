import asyncio
import time
import os
from datetime import datetime
from collections import deque
from typing import List, Dict, Optional

from aiohttp import web, ClientSession, ClientTimeout
from config import config
import logging


class HealthChecker:
    """비동기 방식으로 백엔드 서버 헬스 체크"""

    def __init__(self, servers: List[str], session: ClientSession, check_interval: int = 10):
        self.servers = servers
        self.session = session
        self.check_interval = check_interval
        self.server_status = {server: True for server in servers}
        self.server_response_times = {server: [] for server in servers}
        self.server_last_check = {server: 0 for server in servers}
        self.server_failure_count = {server: 0 for server in servers}
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger('HealthChecker')
        self.logger.info(f"헬스 체커 시작: {len(servers)}개 서버 모니터링")
        self.health_task = asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self):
        """주기적으로 모든 서버의 헬스 체크를 실행하는 메인 루프"""
        initial_delay = 15
        self.logger.debug(f"헬스 체커 유예 시간 시작: {initial_delay}초 후 첫 체크 시작")
        await asyncio.sleep(initial_delay)
        self.logger.debug("헬스 체커 유예 시간 종료. 주기적인 헬스 체크 시작.")

        while True:
            try:
                await self._check_all_servers()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"헬스 체크 루프 오류: {e}")
                await asyncio.sleep(5)

    async def _check_all_servers(self):
        """모든 백엔드 서버에 대해 비동기적으로 헬스 체크 실행"""
        tasks = [self._check_server(server) for server in self.servers]
        await asyncio.gather(*tasks)

    async def _check_server(self, server: str):
        """개별 서버의 헬스 체크를 수행하고 상태를 업데이트"""
        try:
            start_time = time.time()
            async with self.session.get(
                    f"http://{server}/health",
                    timeout=ClientTimeout(total=5),
                    headers={'User-Agent': 'AsyncLoadBalancer/1.0'}
            ) as response:
                response_time = (time.time() - start_time) * 1000
                async with self.lock:
                    self.server_last_check[server] = time.time()
                    if response.status == 200:
                        was_unhealthy = not self.server_status.get(server, False)
                        self.server_status[server] = True
                        self.server_failure_count[server] = 0
                        self.server_response_times[server].append(response_time)
                        if len(self.server_response_times[server]) > 10:
                            self.server_response_times[server].pop(0)
                        if was_unhealthy:
                            self.logger.info(f"✅ 서버 복구됨: {server} ({response_time:.2f}ms)")
                    else:
                        await self._mark_server_unhealthy(server, f"HTTP {response.status}")
        except Exception as e:
            async with self.lock:
                await self._mark_server_unhealthy(server, f"Connection error: {e}")

    async def _mark_server_unhealthy(self, server: str, reason: str):
        """서버를 비정상 상태로 표시"""
        was_healthy = self.server_status.get(server, False)
        self.server_failure_count[server] += 1
        if self.server_failure_count[server] >= config.load_balancer.max_failures:
            if was_healthy:
                self.server_status[server] = False
                self.logger.warning(f"❌ 서버 비정상: {server} ({reason})")
        else:
            self.logger.debug(f"⚠️ 서버 체크 실패: {server} ({reason}) - {self.server_failure_count[server]}/{config.load_balancer.max_failures}")

    async def get_healthy_servers(self) -> List[str]:
        async with self.lock:
            return [server for server, status in self.server_status.items() if status]

    async def get_server_stats(self, server: str) -> Dict:
        response_times = self.server_response_times.get(server, [])
        return {
            'healthy': self.server_status.get(server, False),
            'failure_count': self.server_failure_count.get(server, 0),
            'last_check': self.server_last_check.get(server, 0),
            'avg_response_time': sum(response_times) / len(response_times) if response_times else 0,
        }

    async def get_all_stats(self) -> Dict:
        async with self.lock:
            healthy_count = sum(1 for status in self.server_status.values() if status)
            server_details = {}
            for server in self.servers:
                server_details[server] = await self.get_server_stats(server)

            return {
                'total_servers': len(self.servers),
                'healthy_servers': healthy_count,
                'unhealthy_servers': len(self.servers) - healthy_count,
                'check_interval': self.check_interval,
                'server_details': server_details
            }


class LoadBalancer:
    def __init__(self, lb_config, session: ClientSession):
        self.config = lb_config
        self.algorithm = lb_config.algorithm
        self.servers = lb_config.backend_servers
        self.session = session
        self.health_checker = HealthChecker(self.servers, self.session, lb_config.health_check_interval)
        self.current_index = 0
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger('LoadBalancer')
        self.start_time = time.time()
        self.total_requests = 0
        self.failed_requests = 0
        self.request_timestamps = deque(maxlen=config.load_balancer.max_failures * 100)
        self.logger.info(f"비동기 로드밸런서 초기화 완료: {self.algorithm} 알고리즘")

    async def get_next_server(self) -> Optional[str]:
        healthy_servers = await self.health_checker.get_healthy_servers()
        if not healthy_servers:
            self.logger.error("사용 가능한 건강한 서버가 없습니다")
            return None
        async with self.lock:
            server = healthy_servers[self.current_index % len(healthy_servers)]
            self.current_index += 1
            return server

    async def reset_stats(self):
        async with self.lock:
            self.total_requests = 0
            self.failed_requests = 0
            self.request_timestamps.clear()
            self.logger.info("로드밸런서 통계가 초기화되었습니다.")

    async def get_stats(self) -> Dict:
        async with self.lock:
            uptime = time.time() - self.start_time
            now = time.time()
            recent_requests_count = sum(1 for ts in self.request_timestamps if now - ts <= 10)
            requests_per_second = recent_requests_count / 10.0
            success_rate = ((self.total_requests - self.failed_requests) /
                            max(self.total_requests, 1) * 100)
            health_check_stats = await self.health_checker.get_all_stats()
            avg_response_time = 0
            if health_check_stats.get('server_details'):
                all_times = [
                    stats.get('avg_response_time')
                    for stats in health_check_stats['server_details'].values()
                    if stats.get('avg_response_time') > 0
                ]
                if all_times:
                    avg_response_time = sum(all_times) / len(all_times)

            return {
                'load_balancer': {
                    'algorithm': self.algorithm,
                    'uptime_seconds': round(uptime, 2),
                    'total_requests': self.total_requests,
                    'failed_requests': self.failed_requests,
                    'success_rate': round(success_rate, 2),
                    'requests_per_second': round(requests_per_second, 2),
                    'avg_response_time_ms': round(avg_response_time, 2)
                },
                'backend_servers': health_check_stats.get('server_details', {}),
                'health_check': health_check_stats,
                'timestamp': datetime.now().isoformat()
            }

    async def handle_request(self, request: web.Request) -> web.Response:
        cors_headers = {'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type, Authorization'}

        if request.path == '/':
            dashboard_path = './data/index.html'
            if os.path.exists(dashboard_path):
                return web.FileResponse(dashboard_path)
            else:
                return web.Response(text="<h1>Dashboard not found</h1>", content_type='text/html', status=404)

        if request.path == '/favicon.ico':
            return web.Response(status=204)

        if request.method == 'OPTIONS':
            return web.Response(headers=cors_headers)

        if request.path == '/lb-stats':
            stats = await self.get_stats()
            return web.json_response(stats, headers=cors_headers)

        if request.path == '/reset-stats' and request.method == 'POST':
            await self.reset_stats()
            return web.json_response({'status': 'ok', 'message': 'Load balancer stats reset'}, headers=cors_headers)

        if request.path == '/lb-health':
            healthy = await self.health_checker.get_healthy_servers()
            status = 200 if healthy else 503
            return web.json_response(
                {'status': 'healthy' if healthy else 'degraded'},
                status=status,
                headers=cors_headers
            )

        self.request_timestamps.append(time.time())

        async with self.lock:
            self.total_requests += 1

        backend_server = await self.get_next_server()
        if not backend_server:
            async with self.lock: self.failed_requests += 1
            return web.json_response(
                {'error': 'No healthy backend servers available'}, status=503, headers=cors_headers)

        try:
            url = f"http://{backend_server}{request.path_qs}"
            headers = dict(request.headers)
            headers.pop('Host', None)
            headers['X-Forwarded-For'] = request.remote or 'N/A'
            headers['X-Internal-Secret'] = config.internal_api_secret

            body = await request.read()

            async with self.session.request(
                    request.method, url, headers=headers, data=body,
                    timeout=ClientTimeout(total=30)
            ) as response:
                response_body = await response.read()
                response_headers = dict(response.headers)
                response_headers.update(cors_headers)
                response_headers['X-Load-Balancer'] = 'Async-Active'
                response_headers['X-Backend-Server'] = backend_server

                return web.Response(
                    body=response_body,
                    status=response.status,
                    headers=response_headers
                )
        except Exception:
            async with self.lock:
                self.failed_requests += 1
            return web.json_response({'error': 'Backend server connection failed'}, status=502, headers=cors_headers)


async def start_load_balancer(lb_config):
    logger = logging.getLogger('LoadBalancer')
    logger.info("⚖️ 비동기 로드밸런서 시작 중...")
    async with ClientSession() as session:
        load_balancer = LoadBalancer(lb_config, session)
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", load_balancer.handle_request)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, lb_config.host, lb_config.port)
        await site.start()
        logger.info(f"✅ 비동기 로드밸런서 시작 완료: http://{lb_config.host}:{lb_config.port}")
        try:
            while True: await asyncio.sleep(3600)
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    # [수정] print() 대신 로거 사용
    logger = logging.getLogger('LoadBalancer')
    try:
        asyncio.run(start_load_balancer(config.load_balancer))
    except KeyboardInterrupt:
        logger.info("로드밸런서가 종료되었습니다.")