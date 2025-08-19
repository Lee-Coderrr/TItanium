# blog-service/blog_service.py
import os
import logging
import aiohttp_jinja2
import jinja2
from aiohttp import web

# --- 기본 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('BlogServiceApp')

# ❗ 요청 로깅을 위한 미들웨어 추가
@web.middleware
async def log_request_middleware(request, handler):
    logger.info(f"Blog service received request for: {request.method} {request.path}")
    response = await handler(request)
    return response

# --- 임시 데이터 저장소 (실제로는 데이터베이스 사용) ---
posts_db = {}
users_db = {}


# --- API 핸들러 함수 ---
async def handle_get_posts(request: web.Request) -> web.Response:
    """모든 블로그 게시물 목록을 반환합니다."""
    return web.json_response(list(posts_db.values()))


async def handle_get_post_by_id(request: web.Request) -> web.Response:
    """ID로 특정 게시물을 찾아 반환합니다."""
    post_id = int(request.match_info['id'])
    post = posts_db.get(post_id)
    if post:
        return web.json_response(post)
    return web.json_response({'error': 'Post not found'}, status=404)


async def handle_login(request: web.Request) -> web.Response:
    """사용자 로그인을 처리하고 간단한 세션 토큰을 반환합니다."""
    data = await request.json()
    username = data.get('username')
    password = data.get('password')
    user = users_db.get(username)
    if user and user['password'] == password:
        # 실제로는 JWT를 사용해야 하지만, 여기서는 간단한 토큰을 사용합니다.
        return web.json_response({'token': f'session-token-for-{username}'})
    return web.json_response({'error': 'Invalid credentials'}, status=401)

async def handle_register(request: web.Request) -> web.Response:
    """사용자 등록을 처리합니다."""
    try:
        data = await request.json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return web.json_response({'error': 'Username and password are required'}, status=400)

        if username in users_db:
            return web.json_response({'error': 'Username already exists'}, status=409) # 409 Conflict

        users_db[username] = {'password': password}
        logger.info(f"New user registered: {username}")
        return web.json_response({'message': 'Registration successful'}, status=201) # 201 Created
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return web.json_response({'error': 'Invalid request'}, status=400)


async def handle_health(request: web.Request) -> web.Response:
    """쿠버네티스를 위한 헬스 체크 엔드포인트"""
    return web.json_response({"status": "ok", "service": "blog-service"})


async def handle_stats(request: web.Request) -> web.Response:
    """대시보드를 위한 통계 엔드포인트"""
    stats_data = {
        "blog_service": {
            "service_status": "online",
            "post_count": len(posts_db)
        }
    }
    return web.json_response(stats_data)


# --- 웹 페이지 서빙 ---
@aiohttp_jinja2.template('index.html')
async def handle_index(request: web.Request):
    """메인 블로그 페이지를 렌더링합니다."""
    return {}


# --- 애플리케이션 설정 및 실행 ---
def create_app() -> web.Application:
    app = web.Application(middlewares=[log_request_middleware])
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')))

    blog_sub_app = web.Application()

    # API 라우팅
    blog_sub_app.router.add_post("/login", handle_login)
    blog_sub_app.router.add_post("/register", handle_register)
    blog_sub_app.router.add_get("/api/posts", handle_get_posts)
    blog_sub_app.router.add_get("/api/posts/{id}", handle_get_post_by_id)

    # UI 및 정적 파일 라우팅 (하위 앱으로 이동)
    blog_sub_app.router.add_static('/static', path=os.path.join(os.path.dirname(__file__), 'static'))
    blog_sub_app.router.add_get('/', handle_index)
    blog_sub_app.router.add_get('/{path:.*}', handle_index)  # SPA를 위해 모든 경로를 index.html로 연결

    app.add_subapp('/blog/', blog_sub_app)

    app.router.add_get("/health", handle_health)
    app.router.add_get("/stats", handle_stats)

    return app


def setup_sample_data():
    """서비스 시작 시 샘플 데이터를 생성합니다."""
    global posts_db, users_db
    posts_db = {
        1: {"id": 1, "title": "첫 번째 블로그 글", "author": "admin",
            "content": "마이크로서비스 아키텍처에 오신 것을 환영합니다! 이 블로그는 자체 UI와 API를 가진 독립적인 서비스입니다."},
        2: {"id": 2, "title": "Kustomize와 Skaffold 활용하기", "author": "dev",
            "content": "인프라 관리가 이렇게 쉬울 수 있습니다. CI/CD 파이프라인을 통해 자동으로 배포됩니다."},
    }
    users_db = {
        'admin': {'password': 'password123'}
    }
    logger.info(f"{len(posts_db)}개의 샘플 게시물과 {len(users_db)}명의 사용자로 초기화되었습니다.")


if __name__ == "__main__":
    setup_sample_data()
    app = create_app()
    port = 8005
    logger.info(f"✅ Blog Service starting on http://0.0.0.0:{port}")
    web.run_app(app, host='0.0.0.0', port=port)
