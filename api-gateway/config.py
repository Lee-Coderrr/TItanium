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
    # k8s-configmap.yml에 정의된 환경 변수 값을 읽어옵니다.
    auth_service: str = os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8002')
    user_service: str = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')

class Config:
    def __init__(self):
        self.server = ServerConfig()
        self.services = ServiceUrls()

config = Config()
