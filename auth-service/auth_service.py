# auth-service/auth_service.py (대폭 수정 필요)
import time
import logging
import hashlib
import random
from datetime import datetime
from typing import Dict, Optional
from aiohttp import ClientSession

from config import config


class AuthService:
    def __init__(self, http_session: ClientSession):
        self.active_sessions: Dict[str, Dict] = {}
        self.logger = logging.getLogger('AuthServiceLogic')
        # [수정!] 다른 서비스를 호출하기 위한 HTTP 세션
        self.http_session = http_session

    async def _get_user_from_user_service(self, username: str) -> Optional[Dict]:
        """user-service를 호출하여 사용자 정보를 가져옵니다."""
        try:
            url = f"{config.services.user_service}/users/username/{username}"
            async with self.http_session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user from user-service: {e}")
            return None

    async def authenticate(self, username: str, password: Optional[str], ip_address: str = "") -> Dict:
        """사용자 인증 (이제 user-service를 통해 사용자 정보를 가져옴)"""
        user = await self._get_user_from_user_service(username)

        # 실제 운영에서는 해시된 비밀번호를 비교해야 합니다.
        if user and password == "admin123":  # 단순화를 위한 예시
            token = self._generate_session_token(username)
            expires_at = time.time() + config.auth.session_timeout
            self.active_sessions[token] = {
                'user_id': user['id'], 'username': username,
                'expires_at': expires_at, 'ip_address': ip_address
            }
            return {'success': True, 'token': token}
        else:
            return {'success': False, 'error': 'Invalid credentials'}

    async def validate_session(self, token: str) -> Dict:
        """세션 토큰 유효성 검사"""
        session = self.active_sessions.get(token)
        if not session or time.time() >= session['expires_at']:
            return {'valid': False}
        return {'valid': True, 'user_id': session['user_id'], 'username': session['username']}

    def _generate_session_token(self, username: str) -> str:
        return hashlib.sha256(f"{time.time()}{random.random()}{username}".encode()).hexdigest()
