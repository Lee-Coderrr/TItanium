# auth-service/config.py
import os
from dataclasses import dataclass

@dataclass
class ServerConfig:
    host: str = '0.0.0.0'
    port: int = 8002 # 다른 서비스와 겹치지 않는 포트 사용

@dataclass
class AuthConfig:
    session_timeout: int = 86400 # 24시간

# [중요!] 다른 마이크로서비스를 호출하기 위한 URL
@dataclass
class ServiceUrls:
    user_service: str = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')

class Config:
    def __init__(self):
        self.server = ServerConfig()
        self.auth = AuthConfig()
        self.services = ServiceUrls()

config = Config()
