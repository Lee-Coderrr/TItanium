import asyncio
import time
import logging
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional, Dict, List

from config import config

class CacheService:
    """메모리 기반 캐시 서비스 (비동기 백그라운드 작업)"""

    def __init__(self):
        self.cache: Dict[str, Dict] = {}
        self.access_count = defaultdict(int)
        self.hit_count = 0
        self.miss_count = 0
        self.logger = logging.getLogger('CacheService')
        self.lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def _start_cleanup_task_async(self):
        """비동기 백그라운드 캐시 정리 작업 시작"""
        # [수정] 로그 레벨을 INFO에서 DEBUG로 변경
        self.logger.debug("비동기 캐시 정리 작업 시작됨")
        while True:
            try:
                await asyncio.sleep(config.cache.cleanup_interval)
                expired_count = await self.cleanup_expired()
                if expired_count > 0:
                    self.logger.info(f"정리 완료: {expired_count}개 만료된 캐시 항목 삭제")
            except asyncio.CancelledError:
                self.logger.info("캐시 정리 작업이 취소되었습니다.")
                break
            except Exception as e:
                self.logger.error(f"캐시 정리 오류: {e}")

    async def get(self, key: str) -> Optional[Any]:
        """캐시에서 값 조회"""
        async with self.lock:
            if key in self.cache:
                data = self.cache[key]
                if time.time() < data['expire_time']:
                    self.access_count[key] += 1
                    self.hit_count += 1
                    return data['value']
                else:
                    del self.cache[key]
            self.miss_count += 1
            return None

    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """캐시에 값 저장"""
        ttl = ttl or config.cache.default_ttl
        async with self.lock:
            try:
                serializable_value = self._make_serializable(value)
                self.cache[key] = {
                    'value': serializable_value,
                    'expire_time': time.time() + ttl,
                    'size': len(str(serializable_value))
                }
                await self._check_memory_usage()
                return True
            except Exception as e:
                self.logger.error(f"캐시 저장 오류 ({key}): {e}")
                return False

    async def cleanup_expired(self) -> int:
        """만료된 캐시 정리"""
        current_time = time.time()
        expired_keys = []
        async with self.lock:
            for key, data in self.cache.items():
                if current_time > data['expire_time']:
                    expired_keys.append(key)
            for key in expired_keys:
                if key in self.cache: del self.cache[key]
                if key in self.access_count: del self.access_count[key]
        return len(expired_keys)

    def _make_serializable(self, value: Any) -> Any:
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return str(value)

    async def _check_memory_usage(self):
        """메모리 사용량 체크 및 LRU 삭제 (lock 안에서 호출되어야 함)"""
        total_size = sum(data['size'] for data in self.cache.values())
        max_size_bytes = config.cache.max_memory_mb * 1024 * 1024
        if total_size > max_size_bytes:
            sorted_keys = sorted(self.cache.keys(), key=lambda k: self.access_count.get(k, 0))
            delete_count = max(1, len(sorted_keys) // 5)
            for key in sorted_keys[:delete_count]:
                if key in self.cache: del self.cache[key]
                if key in self.access_count: del self.access_count[key]
            self.logger.warning(f"메모리 한계 도달, LRU 삭제: {delete_count}개 항목")

    def health_check(self) -> Dict:
        return {
            'status': 'healthy',
            'cache_size': len(self.cache),
            'timestamp': datetime.now().isoformat()
        }

    async def get_stats(self) -> Dict:
        """캐시 서비스의 상세 통계 정보를 반환합니다."""
        async with self.lock:
            total_access = self.hit_count + self.miss_count
            hit_ratio = (self.hit_count / total_access) * 100 if total_access > 0 else 0

            # 현재 메모리 사용량 계산
            current_size_bytes = sum(data.get('size', 0) for data in self.cache.values())

            return {
                'item_count': len(self.cache),
                'total_accesses': total_access,
                'hit_count': self.hit_count,
                'miss_count': self.miss_count,
                'hit_ratio': round(hit_ratio, 2),
                'memory_usage_bytes': current_size_bytes,
                'memory_limit_mb': config.cache.max_memory_mb,
                'timestamp': datetime.now().isoformat()
            }

# 전역 캐시 서비스 인스턴스
cache_service = CacheService()

async def start_cache_service_tasks():
    """캐시 서비스의 백그라운드 태스크를 시작하는 함수"""
    if cache_service._cleanup_task is None:
        cache_service._cleanup_task = asyncio.create_task(cache_service._start_cleanup_task_async())