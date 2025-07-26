import os
from dataclasses import dataclass


# 각 서비스의 설정을 정의하는 데이터 클래스들입니다.
@dataclass
class ServerConfig:
    """API 게이트웨이 서버 실행 설정"""
    host: str = '0.0.0.0'
    port: int = 8000
    instance_id: str = 'api-gateway-8000'


@dataclass
class DatabaseConfig:
    """데이터베이스 서비스 설정"""
    db_file: str = 'microservice.db'


@dataclass
class CacheConfig:
    """캐시 서비스 설정"""
    # [수정!] 레디스 호스트 정보 추가
    host: str = os.getenv('REDIS_HOST', 'redis-service')
    port: int = int(os.getenv('REDIS_PORT', '6379'))
    default_ttl: int = 3600

@dataclass
class AuthConfig:
    """인증 서비스 설정"""
    session_timeout: int = 86400


# 전체 설정을 관리하는 클래스입니다.
class Config:
    def __init__(self):
        # 환경 변수에서 공통 설정을 가져옵니다.
        # DATA_DIR은 컨테이너 내부의 데이터 저장 경로를 가리킵니다.
        self.data_dir = os.getenv('DATA_DIR', '/app/data')

        # 로드밸런서로부터의 요청을 검증하기 위한 공유 비밀키입니다.
        self.internal_api_secret = os.getenv('INTERNAL_API_SECRET', 'default-secret')

        # 각 서비스별 설정 인스턴스를 생성합니다.
        self.server = ServerConfig()
        self.database = DatabaseConfig()
        self.cache = CacheConfig()
        self.auth = AuthConfig()

        # 데이터베이스 파일의 전체 경로를 설정합니다.
        self.database.db_file = os.path.join(self.data_dir, self.database.db_file)

        # 데이터 디렉토리가 없으면 생성합니다.
        os.makedirs(self.data_dir, exist_ok=True)


# 애플리케이션 전체에서 사용할 설정 인스턴스를 생성합니다.
config = Config()
