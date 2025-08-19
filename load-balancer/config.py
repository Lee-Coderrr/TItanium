# load-balancer/config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    """로드밸런서 설정 클래스"""
    HOST: str = os.getenv('LB_HOST', '0.0.0.0')
    PORT: int = int(os.getenv('LB_PORT', '7100'))
    API_GATEWAY_URL: str = os.getenv('API_GATEWAY_URL', 'http://api-gateway-service:8000')
    DASHBOARD_UI_URL: str = os.getenv('DASHBOARD_UI_URL', 'http://dashboard-ui-service:80')
    blog_service: str = os.getenv('BLOG_SERVICE_URL', 'http://blog-service:8005')

    HEALTH_CHECK_INTERVAL: int = int(os.getenv('HEALTH_CHECK_INTERVAL', '15'))
    REQUEST_TIMEOUT: int = int(os.getenv('REQUEST_TIMEOUT', '30'))
    INTERNAL_API_SECRET: str = os.getenv('INTERNAL_API_SECRET', 'default-secret')

config = Config()