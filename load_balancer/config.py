from dataclasses import dataclass, field
from typing import List

@dataclass
class LoadBalancerConfig:
    host: str = '0.0.0.0'
    port: int = 7100

    # algorithm: str = 'round_robin'
    # health_check_interval: int = 15
    # max_failures: int = 3

    api_gateway_url: str = 'http://api-gateway-service:8000'
    # Nginx는 기본적으로 80 포트를 사용합니다.
    dashboard_ui_url: str = 'http://dashboard-ui-service:80'

class Config:
    def __init__(self):
        self.load_balancer = LoadBalancerConfig()

config = Config()