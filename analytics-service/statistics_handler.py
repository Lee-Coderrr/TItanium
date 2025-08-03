import sqlite3
import logging
from datetime import datetime
from typing import Dict
from db_connector import db

logger = logging.getLogger(__name__)

async def get_system_statistics() -> Dict:
    """시스템의 종합 통계 정보를 조회합니다."""
    try:
        async with db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM access_logs")
            total_requests = cursor.fetchone()['count']

            cursor.execute("SELECT AVG(response_time) as avg_time FROM access_logs")
            avg_response_time = cursor.fetchone()['avg_time'] or 0

            cursor.execute("""
                SELECT status_code, COUNT(*) as count
                FROM access_logs WHERE timestamp > datetime('now', '-1 day')
                GROUP BY status_code
            """)
            status_codes_raw = cursor.fetchall()

            return {
                'total_requests': total_requests,
                'avg_response_time_ms': round(avg_response_time, 2),
                'status_codes_24h': {str(r['status_code']): r['count'] for r in status_codes_raw},
                'timestamp': datetime.now().isoformat()
            }
    except sqlite3.Error as e:
        logger.error(f"Failed to get system statistics: {e}", exc_info=True)
        return {'error': 'Could not retrieve statistics'}

async def check_health() -> Dict:
    """서비스의 상태(DB 연결)를 확인합니다."""
    try:
        async with db.get_connection() as conn:
            conn.execute("SELECT 1")
        return {'status': 'healthy', 'database': 'connected'}
    except sqlite3.Error as e:
        logger.error(f"Health check failed: Database connection error: {e}", exc_info=True)
        return {'status': 'unhealthy', 'database': 'disconnected'}