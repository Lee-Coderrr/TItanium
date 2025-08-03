from aiohttp import web
import logging

# 핸들러 함수들을 임포트
import logging_handler
import statistics_handler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def handle_log_request(request: web.Request):
    """POST /logs: 접근 로그를 받아 기록을 위임"""
    try:
        data = await request.json()
        # logging_handler의 함수 호출
        await logging_handler.record_access_log(
            user_id=data.get('user_id'),
            endpoint=data.get('endpoint'),
            method=data.get('method'),
            status_code=data.get('status_code'),
            response_time=data.get('response_time'),
            server_instance=data.get('server_instance', 'unknown'),
            ip_address=request.remote,
            user_agent=request.headers.get('User-Agent', '')
        )
        return web.Response(status=202, text="Log accepted")
    except Exception as e:
        logger.error(f"Log handler error: {e}", exc_info=True)
        return web.Response(status=400, text="Bad Request")

async def handle_statistics_request(request: web.Request):
    """GET /statistics: 통계 조회를 위임"""
    # statistics_handler의 함수 호출
    stats = await statistics_handler.get_system_statistics()
    if 'error' in stats:
        return web.json_response(stats, status=500)
    return web.json_response(stats)

async def handle_health_request(request: web.Request):
    """GET /health: 상태 확인을 위임"""
    # statistics_handler의 함수 호출
    health_status = await statistics_handler.check_health()
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return web.json_response(health_status, status=status_code)

def create_app():
    """웹 애플리케이션 인스턴스 생성 및 라우팅 설정"""
    app = web.Application()
    app.router.add_post('/logs', handle_log_request)
    app.router.add_get('/statistics', handle_statistics_request)
    app.router.add_get('/health', handle_health_request)
    return app

if __name__ == '__main__':
    port = 8004
    app = create_app()
    logger.info(f"🚀 Analytics Service starting on port {port}")
    web.run_app(app, port=port)