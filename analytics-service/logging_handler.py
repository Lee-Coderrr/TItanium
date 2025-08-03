import sqlite3
import logging
from typing import Optional
from db_connector import db

logger = logging.getLogger(__name__)

async def record_access_log(
    user_id: Optional[int], endpoint: str, method: str,
    status_code: int, response_time: float, server_instance: str,
    ip_address: str = "", user_agent: str = ""
):
    """접근 로그를 데이터베이스에 기록합니다."""
    sql = """
        INSERT INTO access_logs
        (user_id, endpoint, method, status_code, response_time,
         server_instance, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (user_id, endpoint, method, status_code, response_time,
              server_instance, ip_address, user_agent)

    try:
        async with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to record access log: {e}", exc_info=True)