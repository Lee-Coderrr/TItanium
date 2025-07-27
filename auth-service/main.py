# auth-service/auth_service.py
import time
import logging
import hashlib
import random
from datetime import datetime
from typing import Dict, Optional

from aiohttp import ClientSession
from config import config


class AuthService:
    """사용자 인증 및 세션 관리를 전담하는 서비스 로직"""

    def __init__(self, http_session: ClientSession):
        self.active_sessions: Dict[str, Dict] = {}
        self.logger = logging.getLogger('AuthServiceLogic')
        # 다른 마이크로서비스와 통신하기 위한 aiohttp 클라이언트 세션
        self.http_session = http_session

    async def _get_user_from_user_service(self, username: str) -> Optional[Dict]:
        """user-service를 호출하여 사용자 정보를 가져옵니다."""
        url = f"{config.services.user_service}/users/username/{username}"
        try:
            async with self.http_session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                self.logger.warning(f"User '{username}' not found in user-service (status: {response.status}).")
                return None
        except Exception as e:
            self.logger.error(f"Error calling user-service at {url}: {e}")
            return None

    async def authenticate(self, username: str, password: Optional[str]) -> Dict:
        """사용자 인증을 수행합니다."""
        user = await self._get_user_from_user_service(username)

        # 실제 운영 환경에서는 해시된 비밀번호를 비교해야 합니다.
        # 여기서는 학습을 위해 간단한 문자열 비교를 사용합니다.
        password_required = {'admin': 'admin123', 'developer': 'dev123'}
        is_password_valid = (username not in password_required) or (password == password_required.get(username))

        if user and is_password_valid:
            token = self._generate_session_token(username)
            expires_at = time.time() + config.auth.session_timeout

            self.active_sessions[token] = {
                'user_id': user['id'],
                'username': username,
                'created_at': time.time(),
                'last_access': time.time(),
                'expires_at': expires_at,
            }
            self.logger.info(f"Authentication successful for user: {username}")
            return {'success': True, 'token': token}
        else:
            self.logger.warning(f"Authentication failed for user: {username}")
            return {'success': False, 'error': 'Invalid credentials'}

    async def validate_session(self, token: str) -> Dict:
        """세션 토큰의 유효성을 검사합니다."""
        session = self.active_sessions.get(token)

        if not session or time.time() >= session['expires_at']:
            if session:
                del self.active_sessions[token]
            return {'valid': False, 'error': 'Session expired or invalid'}

        # 세션 유효 기간 갱신
        session['last_access'] = time.time()
        session['expires_at'] = time.time() + config.auth.session_timeout

        return {'valid': True, 'user_id': session['user_id'], 'username': session['username']}

    async def get_session_info(self, token: str) -> Optional[Dict]:
        """토큰에 해당하는 세션의 상세 정보를 반환합니다."""
        session = self.active_sessions.get(token)
        if not session:
            return None
        return {
            'username': session.get('username'),
            'created_at': datetime.fromtimestamp(session.get('created_at')).isoformat(),
            'last_access': datetime.fromtimestamp(session.get('last_access')).isoformat(),
            'expires_at': datetime.fromtimestamp(session.get('expires_at')).isoformat(),
        }

    async def get_active_sessions(self) -> Dict:
        """현재 활성화된 모든 세션의 정보를 반환합니다 (통계용)."""
        session_list = [await self.get_session_info(token) for token in self.active_sessions.keys()]
        return {
            'active_session_count': len(self.active_sessions),
            'sessions': [s for s in session_list if s]  # None이 아닌 세션만 포함
        }

    def _generate_session_token(self, username: str) -> str:
        """안전한 세션 토큰을 생성합니다."""
        return hashlib.sha256(f"{time.time()}{random.random()}{username}".encode()).hexdigest()
