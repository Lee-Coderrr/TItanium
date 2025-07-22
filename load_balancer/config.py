from dataclasses import dataclass, field
from typing import List

@dataclass
class LoadBalancerConfig:
    host: str = '0.0.0.0'
    port: int = 7100
    backend_servers: List[str] = field(default_factory=list)
    algorithm: str = 'round_robin'
    health_check_interval: int = 15

class Config:
    def __init__(self):
        self.load_balancer = LoadBalancerConfig(
            backend_servers=['api-gateway:8000']
        )

config = Config()