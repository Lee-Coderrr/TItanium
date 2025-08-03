# user-service/database_service.py (수정 후)
import asyncio
import sqlite3
import logging
from typing import Optional, Dict

from config import config
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

class UserServiceDatabase:
    def __init__(self, db_file=config.database.db_file):
        self.db_file = db_file
        self.lock = asyncio.Lock()
        self._initialize_db()

    def _initialize_db(self):
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT NOT NULL,
                        password_hash TEXT NOT NULL
                    )
                ''')
        except sqlite3.Error as e:
            logger.error(f"User DB initialization failed: {e}", exc_info=True)
            raise

    async def add_user(self, username: str, email: str, password: str) -> Optional[int]:
        """사용자를 추가하고 해시된 비밀번호를 저장합니다."""
        password_hash = generate_password_hash(password)
        async with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                                   (username, email, password_hash))
                    return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None # 이미 존재하는 사용자

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """사용자 이름으로 사용자 정보를 조회합니다."""
        async with self.lock:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
                user = cursor.fetchone()
                return dict(user) if user else None

    async def verify_user_credentials(self, username: str, password: str) -> Optional[Dict]:
        """사용자 자격 증명을 확인합니다."""
        user = await self.get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            # 비밀번호 해시는 제외하고 정보 반환
            return {"id": user["id"], "username": user["username"], "email": user["email"]}
        return None

    async def health_check(self) -> bool:
        """데이터베이스 연결 상태를 확인합니다."""
        async with self.lock:
            try:
                with sqlite3.connect(self.db_file) as conn:
                    # 간단한 쿼리를 실행하여 연결을 테스트합니다.
                    conn.execute("SELECT 1")
                return True
            except Exception as e:
                logger.error(f"Database health check failed: {e}")
                return False