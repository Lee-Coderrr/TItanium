# api_gateway/cache_service.py
import asyncio
import logging
import json
from typing import Any, Optional, Dict

import redis.asyncio as redis
from config import config


class CacheService:
    """레디스 기반 비동기 캐시 서비스"""

    def __init__(self):
        self.logger = logging.getLogger('CacheService')
        try:
            # 레디스 클라이언트 초기화
            self.redis_client = redis.Redis(
                host=config.cache.host,
                port=config.cache.port,
                db=0,
                decode_responses=True  # 응답을 자동으로 UTF-8로 디코딩
            )
            self.logger.info(f"✅ 레디스 캐시 서비스 초기화 완료: {config.cache.host}:{config.cache.port}")
        except Exception as e:
            self.logger.error(f"❌ 레디스 클라이언트 초기화 실패: {e}")
            self.redis_client = None

    async def get(self, key: str) -> Optional[Any]:
        """캐시에서 값 조회"""
        if not self.redis_client:
            return None
        try:
            value = await self.redis_client.get(key)
            if value:
                # JSON으로 저장된 값을 파이썬 객체로 변환
                return json.loads(value)
            return None
        except Exception as e:
            self.logger.error(f"캐시 조회 오류 ({key}): {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """캐시에 값 저장"""
        if not self.redis_client:
            return False

        ttl = ttl or config.cache.default_ttl
        try:
            # 파이썬 객체를 JSON 문자열로 변환하여 저장
            serializable_value = json.dumps(value)
            await self.redis_client.setex(key, ttl, serializable_value)
            return True
        except Exception as e:
            self.logger.error(f"캐시 저장 오류 ({key}): {e}")
            return False

    async def get_stats(self) -> Dict:
        """레디스 서버의 상세 통계 정보를 반환합니다."""
        if not self.redis_client:
            return {'error': 'Redis client not initialized'}

        try:
            info = await self.redis_client.info()
            hit_count = int(info.get('keyspace_hits', 0))
            miss_count = int(info.get('keyspace_misses', 0))
            total_accesses = hit_count + miss_count
            hit_ratio = (hit_count / total_accesses) * 100 if total_accesses > 0 else 0

            return {
                'item_count': info.get('db0', {}).get('keys', 0),
                'total_accesses': total_accesses,
                'hit_count': hit_count,
                'miss_count': miss_count,
                'hit_ratio': round(hit_ratio, 2),
                'memory_usage_mb': round(info.get('used_memory', 0) / (1024 * 1024), 2),
                'redis_version': info.get('redis_version'),
            }
        except Exception as e:
            self.logger.error(f"캐시 통계 조회 오류: {e}")
            return {'error': str(e)}

    async def health_check(self) -> Dict:
        """레디스 서버 연결 상태 확인"""
        if not self.redis_client:
            return {'status': 'unhealthy', 'error': 'Redis client not initialized'}
        try:
            if await self.redis_client.ping():
                return {'status': 'healthy'}
            else:
                return {'status': 'unhealthy', 'error': 'Ping failed'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}


# 전역 캐시 서비스 인스턴스
cache_service = CacheService()