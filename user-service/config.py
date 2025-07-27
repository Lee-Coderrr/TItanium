# user-service/config.py
import os
from dataclasses import dataclass

@dataclass
class ServerConfig:
    host: str = '0.0.0.0'
    port: int = 8001 # 다른 서비스와 겹치지 않는 포트 사용

@dataclass
class DatabaseConfig:
    db_file: str = '/data/app.db' # PVC 마운트 경로

@dataclass
class CacheConfig:
    host: str = os.getenv('REDIS_HOST', 'redis-service')
    port: int = int(os.getenv('REDIS_PORT', '6379'))
    default_ttl: int = 300

class Config:
    def __init__(self):
        self.server = ServerConfig()
        self.database = DatabaseConfig()
        self.cache = CacheConfig()

config = Config()
