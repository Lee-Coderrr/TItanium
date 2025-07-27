# auth-service/config.py
import os
from dataclasses import dataclass

@dataclass
class ServerConfig:
    """Auth Service 서버 실행 설정"""
    host: str = '0.0.0.0'
    port: int = 8002 # 다른 서비스와 겹치지 않는 포트

@dataclass
class AuthConfig:
    """인증 관련 설정"""
    session_timeout: int = 86400  # 세션 유효 시간 (24시간)

@dataclass
class ServiceUrls:
    """호출할 다른 마이크로서비스의 주소"""
    # k8s-configmap.yml에 정의된 환경 변수 값을 읽어옵니다.
    user_service: str = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')

class Config:
    def __init__(self):
        self.server = ServerConfig()
        self.auth = AuthConfig()
        self.services = ServiceUrls()

# 다른 파일에서 쉽게 임포트할 수 있도록 전역 인스턴스 생성
config = Config()
