import asyncio
import sqlite3
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, db_file="analytics.db"):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.db_file = db_file
            cls._instance._initialize_db()
        return cls._instance

    def _initialize_db(self):
        """DB 파일과 테이블이 존재하는지 확인하고 없으면 생성합니다."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # 접근 로그 테이블
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS access_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                        endpoint TEXT NOT NULL, method TEXT NOT NULL,
                        status_code INTEGER, response_time REAL,
                        server_instance TEXT, ip_address TEXT, user_agent TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # 시스템 메트릭 테이블 (향후 확장용)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, metric_name TEXT NOT NULL,
                        metric_value REAL NOT NULL, server_instance TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                logger.info("Analytics DB tables initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"DB initialization failed: {e}", exc_info=True)
            raise

    @asynccontextmanager
    async def get_connection(self):
        """비동기 Lock으로 보호되는 DB 커넥션을 제공하는 컨텍스트 관리자"""
        async with self._lock:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

# 전역 DB 인스턴스
db = Database()