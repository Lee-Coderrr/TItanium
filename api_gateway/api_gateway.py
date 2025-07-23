import asyncio
import time
import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Optional

from aiohttp import web

from config import config
from database_service import db_service
from cache_service import cache_service
from auth_service import auth_service


class APIGateway:
    """비동기 API Gateway - 요청 라우팅 및 처리"""

    def __init__(self, instance_id: str, port: int):
        self.instance_id = instance_id
        self.port = port
        self.logger = logging.getLogger(f'APIGateway-{port}')
        self.lock = asyncio.Lock()
        self.reset_stats()
        self.logger.info(f"비동기 API Gateway 초기화: {instance_id} (포트: {port})")

    def reset_stats(self):
        """API 게이트웨이 내부 통계 초기화"""
        self.request_count = 0
        self.response_times = []
        self.start_time = time.time()
        self.error_count = 0
        self.logger.info(f"API Gateway 통계가 초기화되었습니다: {self.instance_id}")

    async def _authenticate_request(self, request: web.Request) -> Optional[Dict]:
        """요청 헤더의 토큰을 검증하고 사용자 컨텍스트를 반환"""
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        token = auth_header[7:]
        # 세션 검증 시 last_access 시간 업데이트
        session = auth_service.validate_session(token, update_access=True)
        if not session.get('valid'):
            return None
        return {'user_id': session['user_id'], 'username': session['username'], 'token': token}

    # --- 각 엔드포인트 핸들러 ---

    async def handle_root(self, request: web.Request) -> web.Response:
        return self._json_response(200, {'service': 'API Gateway (Async)', 'instance_id': self.instance_id})

    async def handle_health_check(self, request: web.Request) -> web.Response:
        db_health = db_service.health_check()
        cache_health = cache_service.health_check()
        auth_health = auth_service.health_check()
        all_healthy = all(s['status'] == 'healthy' for s in [db_health, cache_health, auth_health])
        status_code = 200 if all_healthy else 503
        response_data = {
            'status': 'healthy' if all_healthy else 'degraded',
            'services': {'database': db_health['status'], 'cache': cache_health['status'],
                         'auth': auth_health['status']},
            'timestamp': datetime.now().isoformat()
        }
        return self._json_response(status_code, response_data)

    async def handle_stats(self, request: web.Request) -> web.Response:
        db_stats = db_service.get_statistics()
        db_health = db_service.health_check()
        cache_stats = await cache_service.get_stats()
        auth_stats = await auth_service.get_active_sessions()

        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        uptime = time.time() - self.start_time
        rps = self.request_count / uptime if uptime > 0 else 0
        response_data = {
            'api_gateway': {'instance_id': self.instance_id, 'port': self.port, 'total_requests': self.request_count,
                            'avg_response_time_ms': round(avg_response_time * 1000, 2),
                            'requests_per_second': round(rps, 2)},
            'database': {'stats': db_stats, 'status': db_health.get('status', 'unknown')},
            'cache': cache_stats,
            'auth': auth_stats,
            'timestamp': datetime.now().isoformat()
        }
        return self._json_response(200, response_data)

    async def handle_reset_stats(self, request: web.Request) -> web.Response:
        self.reset_stats()
        return self._json_response(200, {'status': 'ok', 'message': f'API Gateway ({self.instance_id}) stats reset'})

    async def handle_login(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            client_ip = request.get('client_ip', 'N/A')
            auth_result = auth_service.authenticate(data.get('username'), data.get('password'), client_ip)
            status_code = 200 if auth_result.get('success') else 401
            return self._json_response(status_code, auth_result)
        except json.JSONDecodeError:
            return self._json_response(400, {'error': 'Invalid JSON'})

    # --- [추가된 핸들러] ---
    async def handle_logout(self, request: web.Request) -> web.Response:
        """사용자 로그아웃 처리"""
        user_context = await self._authenticate_request(request)
        if not user_context:
            return self._json_response(401, {'error': 'Authentication required'})

        token = user_context['token']
        logout_result = auth_service.logout(token)

        status_code = 200 if logout_result.get('success') else 400
        return self._json_response(status_code, logout_result)

    async def handle_profile(self, request: web.Request) -> web.Response:
        """사용자 프로필 정보 조회"""
        user_context = await self._authenticate_request(request)
        if not user_context:
            return self._json_response(401, {'error': 'Authentication required'})

        user_id = user_context['user_id']
        user_info = db_service.get_user_by_id(user_id)

        if not user_info:
            return self._json_response(404, {'error': 'User not found'})

        # 세션 정보 추가
        session_info = auth_service.get_session_info(user_context['token'])
        user_info['session'] = session_info

        return self._json_response(200, {'success': True, 'user': user_info})

    async def handle_get_cache(self, request: web.Request) -> web.Response:
        """캐시에서 데이터 조회"""
        key = request.match_info.get('key')
        if not key:
            return self._json_response(400, {'error': 'Cache key is required'})

        value = cache_service.get(key)
        if value is not None:
            return self._json_response(200, {'key': key, 'value': value, 'found': True})
        else:
            return self._json_response(404, {'key': key, 'found': False})

    async def handle_set_cache(self, request: web.Request) -> web.Response:
        """캐시에 데이터 저장"""
        key = request.match_info.get('key')
        if not key:
            return self._json_response(400, {'error': 'Cache key is required'})

        try:
            data = await request.json()
            value = data.get('value')
            ttl = data.get('ttl')  # None일 경우 기본값 사용

            if value is None:
                return self._json_response(400, {'error': 'Value is required'})

            success = cache_service.set(key, value, ttl=ttl)
            if success:
                return self._json_response(201, {'key': key, 'success': True})
            else:
                return self._json_response(500, {'error': 'Failed to set cache'})
        except json.JSONDecodeError:
            return self._json_response(400, {'error': 'Invalid JSON'})

    async def handle_admin_sessions(self, request: web.Request) -> web.Response:
        """활성 세션 정보 조회 (관리자용)"""
        user_context = await self._authenticate_request(request)
        # 실제 환경에서는 'admin' 역할(role)을 확인해야 함
        if not user_context or user_context.get('username') != 'admin':
            return self._json_response(403, {'error': 'Administrator access required'})

        active_sessions = auth_service.get_active_sessions()
        return self._json_response(200, active_sessions)

    # --- [여기까지 추가] ---

    async def _log_request_to_db(self, request: web.Request, status_code: int, response_time: float):
        """요청 정보를 비동기적으로 DB에 기록"""
        user_id = None
        # DB 로깅을 위해 다시 인증 컨텍스트를 가져오지만, 이번엔 세션 시간을 갱신하지 않음
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            session = auth_service.validate_session(token, update_access=False)
            if session.get('valid'):
                user_id = session.get('user_id')

        db_service.log_access(
            user_id=user_id,
            endpoint=request.path,
            method=request.method,
            status_code=status_code,
            response_time=response_time,
            server_instance=self.instance_id,
            ip_address=request.get('client_ip', 'N/A'),
            user_agent=request.headers.get('User-Agent', '')
        )

    def _json_response(self, status_code: int, data: Dict) -> web.Response:
        """표준 JSON 응답 생성"""
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type, Authorization'}
        return web.json_response(data, status=status_code, headers=headers)


async def start_api_gateway_instance(server_config):
    """비동기 API Gateway 인스턴스 시작"""
    logger = logging.getLogger(f'APIGateway-{server_config.port}')
    try:
        api_gateway = APIGateway(server_config.instance_id, server_config.port)

        # aiohttp의 표준 미들웨어 팩토리 패턴을 사용
        @web.middleware
        async def middleware_handler(request: web.Request, handler):
            """모든 요청에 대한 로깅 및 응답 시간 측정을 위한 미들웨어"""
            start_time = time.time()
            client_ip = request.remote or 'N/A'
            request['client_ip'] = client_ip

            # 공유 비밀키 검증 (헬스 체크 경로는 예외)
            if request.path != '/health':
                secret_header = request.headers.get('X-Internal-Secret')
                if not secret_header or secret_header != config.internal_api_secret:
                    api_gateway.logger.warning(f"비정상 접근 차단: {client_ip} -> {request.path} (잘못된 비밀키)")
                    return api_gateway._json_response(403, {
                        'error': 'Forbidden',
                        'message': 'Direct access to the API gateway is not allowed.'
                    })

            async with api_gateway.lock:
                api_gateway.request_count += 1

            try:
                # 다음 핸들러(라우터) 호출
                response = await handler(request)

                # 응답 시간 기록 및 DB 로그
                response_time = time.time() - start_time
                api_gateway.response_times.append(response_time)
                if len(api_gateway.response_times) > 100:
                    api_gateway.response_times.pop(0)

                # DB 로깅은 백그라운드 작업으로 실행
                asyncio.create_task(api_gateway._log_request_to_db(request, response.status, response_time))

                return response
            except web.HTTPException as ex:
                # aiohttp가 발생시키는 HTTP 예외 (예: HTTPNotFound)를 정상적으로 처리
                response_time = time.time() - start_time
                api_gateway.response_times.append(response_time)
                asyncio.create_task(api_gateway._log_request_to_db(request, ex.status_code, response_time))
                # 미들웨어에서 오류 카운트
                if ex.status_code >= 500:
                    async with api_gateway.lock:
                        api_gateway.error_count += 1
                return ex  # 예외를 그대로 반환하여 aiohttp가 처리하도록 함
            except Exception as e:
                async with api_gateway.lock:
                    api_gateway.error_count += 1
                api_gateway.logger.error(f"요청 처리 오류: {request.path} - {e}\n{traceback.format_exc()}")
                response_time = time.time() - start_time
                asyncio.create_task(api_gateway._log_request_to_db(request, 500, response_time))
                return api_gateway._json_response(500, {'error': 'Internal server error', 'message': str(e)})

        # 미들웨어를 포함하여 애플리케이션 생성
        app = web.Application(middlewares=[middleware_handler])

        # 기존 라우터
        app.router.add_get("/", api_gateway.handle_root)
        app.router.add_get("/health", api_gateway.handle_health_check)
        app.router.add_get("/stats", api_gateway.handle_stats)
        app.router.add_post("/reset-stats", api_gateway.handle_reset_stats)
        app.router.add_post("/login", api_gateway.handle_login)

        # 추가된 라우터
        app.router.add_post("/logout", api_gateway.handle_logout)
        app.router.add_get("/profile", api_gateway.handle_profile)
        # 동적 경로: {key} 부분에 어떤 문자열이든 올 수 있음
        app.router.add_get("/cache/{key}", api_gateway.handle_get_cache)
        app.router.add_post("/cache/{key}", api_gateway.handle_set_cache)
        app.router.add_get("/admin/sessions", api_gateway.handle_admin_sessions)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, server_config.host, server_config.port)
        await site.start()

        logger.info(f"✅ 비동기 API Gateway 시작: {server_config.instance_id} on port {server_config.port}")
        await asyncio.Event().wait()
    except OSError as e:
        logger.error(f"❌ 포트 {server_config.port}가 이미 사용 중입니다: {e}")
    except Exception as e:
        logger.error(f"❌ API Gateway 시작 실패: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger = logging.getLogger('APIGateway')

    # [수정] 단순화된 config 객체에서 직접 서버 설정을 가져옵니다.
    server_config = config.server

    try:
        # 백그라운드 서비스 태스크 시작
        asyncio.run(start_api_gateway_instance(server_config))
    except KeyboardInterrupt:
        logger.info("API Gateway가 종료되었습니다.")