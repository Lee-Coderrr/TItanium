# load_balancer/config.py
import os
from dataclasses import dataclass


@dataclass
class Config:
    """로드밸런서 설정 클래스"""
    # 서버 설정
    HOST: str = os.getenv('LB_HOST', '0.0.0.0')
    PORT: int = int(os.getenv('LB_PORT', '7100'))

    # 프록시 대상 URL
    API_GATEWAY_URL: str = os.getenv('API_GATEWAY_URL', 'http://api-gateway-service:8000')
    DASHBOARD_UI_URL: str = os.getenv('DASHBOARD_UI_URL', 'http://dashboard-ui-service:80')

    # 헬스 체크 설정
    HEALTH_CHECK_INTERVAL: int = int(os.getenv('HEALTH_CHECK_INTERVAL', '15'))

    # [수정!] 타임아웃 및 보안 설정
    REQUEST_TIMEOUT: int = int(os.getenv('REQUEST_TIMEOUT', '30'))
    INTERNAL_API_SECRET: str = os.getenv('INTERNAL_API_SECRET', 'default-secret-for-local-dev')


# 다른 파일에서 쉽게 임포트하여 사용할 수 있도록 전역 인스턴스 생성
config = Config()