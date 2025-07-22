import asyncio
import time
import logging
import hashlib
import random
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List

from database_service import db_service
from config import config


class AuthService:
    """사용자 인증 및 세션 관리 서비스 (비동기 백그라운드 작업)"""

    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}
        self.failed_attempts: Dict[str, List[float]] = {}
        self.logger = logging.getLogger('AuthService')
        self.lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def _start_session_cleanup_async(self):
        """비동기 백그라운드 세션 정리 작업 시작"""
        # [수정] 로그 레벨을 INFO에서 DEBUG로 변경
        self.logger.debug("비동기 세션 정리 작업 시작됨")
        while True:
            try:
                await asyncio.sleep(300)  # 5분마다 정리
                cleaned_count = await self.cleanup_expired_sessions()
                if cleaned_count > 0:
                    self.logger.info(f"만료된 세션 정리: {cleaned_count}개")
            except asyncio.CancelledError:
                self.logger.info("세션 정리 작업이 취소되었습니다.")
                break
            except Exception as e:
                self.logger.error(f"세션 정리 오류: {e}")

    async def authenticate(self, username: str, password: Optional[str] = None, ip_address: str = "") -> Dict:
        """사용자 인증"""
        if self._is_ip_blocked(ip_address):
            return {
                'success': False, 'error': 'Too many failed attempts.',
                'blocked_until': self._get_block_end_time(ip_address)
            }

        try:
            user = db_service.get_user(username)
            if user and self._verify_password(username, password):
                session_token = self._generate_session_token(username)
                expires_at = time.time() + config.auth.session_timeout

                async with self.lock:
                    self.active_sessions[session_token] = {
                        'user_id': user['id'], 'username': username, 'created_at': time.time(),
                        'last_access': time.time(), 'ip_address': ip_address, 'expires_at': expires_at
                    }
                    if ip_address in self.failed_attempts:
                        del self.failed_attempts[ip_address]

                self.logger.info(f"사용자 인증 성공: {username} from {ip_address}")
                return {
                    'success': True, 'token': session_token, 'user': user,
                    'expires_at': datetime.fromtimestamp(expires_at).isoformat()
                }
            else:
                self._record_failed_attempt(ip_address)
                self.logger.warning(f"인증 실패: {username} from {ip_address}")
                return {'success': False, 'error': 'Invalid credentials'}
        except Exception as e:
            self.logger.error(f"인증 처리 오류: {e}")
            return {'success': False, 'error': 'Authentication service error'}

    def _verify_password(self, username: str, password: Optional[str]) -> bool:
        password_required = {'admin': 'admin123', 'developer': 'dev123'}
        if username in password_required:
            return password == password_required.get(username)
        return True

    def _generate_session_token(self, username: str) -> str:
        token_data = f"{time.time()}{random.random()}{username}"
        return hashlib.sha256(token_data.encode()).hexdigest()

    async def validate_session(self, token: str, update_access: bool = True) -> Dict:
        """세션 토큰 유효성 검사"""
        async with self.lock:
            session = self.active_sessions.get(token)
            if not session:
                return {'valid': False, 'error': 'Invalid session token'}

            current_time = time.time()
            if current_time >= session['expires_at']:
                del self.active_sessions[token]
                self.logger.info(f"만료된 세션 삭제: {session['username']}")
                return {'valid': False, 'error': 'Session expired'}

            if update_access:
                session['last_access'] = current_time
                session['expires_at'] = current_time + config.auth.session_timeout

            return {
                'valid': True, 'user_id': session['user_id'], 'username': session['username'],
                'expires_at': datetime.fromtimestamp(session['expires_at']).isoformat()
            }

    async def cleanup_expired_sessions(self) -> int:
        """만료된 세션 정리"""
        current_time = time.time()
        expired_tokens = []
        async with self.lock:
            for token, session in self.active_sessions.items():
                if current_time > session['expires_at']:
                    expired_tokens.append(token)
            for token in expired_tokens:
                del self.active_sessions[token]
        return len(expired_tokens)

    def _record_failed_attempt(self, ip_address: str):
        if not ip_address: return
        now = time.time()
        if ip_address not in self.failed_attempts:
            self.failed_attempts[ip_address] = []

        one_hour_ago = now - 3600
        self.failed_attempts[ip_address] = [t for t in self.failed_attempts[ip_address] if t > one_hour_ago]
        self.failed_attempts[ip_address].append(now)

    def _is_ip_blocked(self, ip_address: str) -> bool:
        if not ip_address: return False
        attempts = self.failed_attempts.get(ip_address, [])
        recent_failures = [t for t in attempts if time.time() - t < 3600]
        return len(recent_failures) >= 5

    def _get_block_end_time(self, ip_address: str) -> Optional[str]:
        if not self.failed_attempts.get(ip_address): return None
        last_attempt = max(self.failed_attempts[ip_address])
        return datetime.fromtimestamp(last_attempt + 3600).isoformat()

    def health_check(self) -> Dict:
        return {
            'status': 'healthy',
            'active_sessions': len(self.active_sessions),
            'timestamp': datetime.now().isoformat()
        }

    async def get_active_sessions(self) -> Dict:
        """활성 세션 정보를 요약하여 반환합니다."""
        async with self.lock:
            # 토큰과 같은 민감한 정보는 제외하고 안전한 정보만 요약
            session_list = [
                {
                    'username': session.get('username'),
                    'ip_address': session.get('ip_address'),
                    'created_at': datetime.fromtimestamp(session.get('created_at')).isoformat(),
                    'last_access': datetime.fromtimestamp(session.get('last_access')).isoformat(),
                    'expires_at': datetime.fromtimestamp(session.get('expires_at')).isoformat(),
                }
                for session in self.active_sessions.values()
            ]
            return {
                'active_session_count': len(self.active_sessions),
                'sessions': session_list
            }


# 전역 인증 서비스 인스턴스
auth_service = AuthService()


async def start_auth_service_tasks():
    """인증 서비스의 백그라운드 태스크를 시작하는 함수"""
    if auth_service._cleanup_task is None:
        auth_service._cleanup_task = asyncio.create_task(auth_service._start_session_cleanup_async())