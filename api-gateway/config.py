# api-gateway/config.py
import os
from dataclasses import dataclass

@dataclass
class ServerConfig:
    """API 게이트웨이 서버 실행 설정"""
    host: str = '0.0.0.0'
    port: int = 8000

@dataclass
class ServiceUrls:
    """호출할 내부 마이크로서비스들의 주소"""
    # k8s-configmap.yml 또는 docker-compose.yml에 정의된 환경 변수 값을 읽어옵니다.
    # 환경 변수가 없을 경우, Docker Compose 환경에서 사용할 기본 서비스 이름을 사용합니다.
    load_balancer: str = os.getenv('LOAD_BALANCER_URL', 'http://load-balancer-service:7100')
    auth_service: str = os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8002')
    user_service: str = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')
    blog_service: str = os.getenv('BLOG_SERVICE_URL', 'http://blog-service:8005')

class Config:
    """전체 설정을 관리하는 클래스"""
    def __init__(self):
        self.server = ServerConfig()
        self.services = ServiceUrls()

# 다른 파일에서 'from config import config'로 쉽게 사용할 수 있도록
# 전역 인스턴스를 생성합니다.
config = Config()
