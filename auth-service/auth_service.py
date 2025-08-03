import jwt
import aiohttp
import logging
from datetime import datetime, timedelta, timezone
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.JWT_SECRET = config.INTERNAL_API_SECRET
        self.JWT_ALGORITHM = "HS256"
        self.JWT_EXP_DELTA_SECONDS = timedelta(hours=24)
        self.USER_SERVICE_VERIFY_URL = f"{config.USER_SERVICE_URL}/users/verify-credentials"
        logger.info("Auth service initialized for JWT-based authentication.")

    async def _verify_user_from_service(self, username, password):
        """(Helper) User-service에 자격 증명 확인을 요청하는 로직"""
        payload = {"username": username, "password": password}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.USER_SERVICE_VERIFY_URL, json=payload) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Error connecting to user-service: {e}")
            return None

    async def login(self, username, password):
        """사용자 로그인 및 JWT 토큰 발급"""
        # 헬퍼 함수를 통해 자격 증명 확인
        user_data = await self._verify_user_from_service(username, password)

        if not user_data:
            logger.warning(f"Login failed for '{username}': Invalid credentials or service error.")
            return {"status": "failed", "message": "Invalid username or password"}

        user_id = user_data.get("id")
        jwt_payload = {
            'user_id': user_id,
            'username': username,
            'exp': datetime.now(timezone.utc) + self.JWT_EXP_DELTA_SECONDS
        }
        token = jwt.encode(jwt_payload, self.JWT_SECRET, algorithm=self.JWT_ALGORITHM)

        logger.info(f"Login successful for '{username}'. JWT token created.")
        return {"status": "success", "token": token}

    def verify_token(self, token):
        try:
            decoded_payload = jwt.decode(
                token,
                self.JWT_SECRET,
                algorithms=[self.JWT_ALGORITHM]
            )
            logger.info(f"Token verified successfully for user_id: {decoded_payload.get('user_id')}")
            return {"status": "success", "data": decoded_payload}
        except jwt.ExpiredSignatureError:
            logger.warning("Token verification failed: Token has expired.")
            return {"status": "failed", "message": "Token has expired"}
        except jwt.InvalidTokenError as e:
            logger.error(f"Token verification failed: Invalid token. Reason: {e}")
            return {"status": "failed", "message": "Invalid token"}