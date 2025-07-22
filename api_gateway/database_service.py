# database_service.py
# 데이터베이스 서비스 - 사용자 정보 및 로그 관리

import sqlite3
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, List
from config import config


class DatabaseService:
    """데이터베이스 서비스 - 사용자 관리 및 접근 로그"""

    def __init__(self, db_file: str = None):
        self.db_file = db_file or config.database.db_file
        self.logger = logging.getLogger('DatabaseService')
        self.lock = threading.Lock()
        self.init_database()

    def init_database(self):
        """데이터베이스 초기화"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            # 사용자 테이블
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS users
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               username
                               TEXT
                               UNIQUE
                               NOT
                               NULL,
                               email
                               TEXT
                               NOT
                               NULL,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               last_access
                               TIMESTAMP,
                               is_active
                               BOOLEAN
                               DEFAULT
                               TRUE
                           )
                           ''')

            # 접근 로그 테이블
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS access_logs
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               user_id
                               INTEGER,
                               endpoint
                               TEXT,
                               method
                               TEXT,
                               status_code
                               INTEGER,
                               response_time
                               REAL,
                               timestamp
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               server_instance
                               TEXT,
                               ip_address
                               TEXT,
                               user_agent
                               TEXT,
                               FOREIGN
                               KEY
                           (
                               user_id
                           ) REFERENCES users
                           (
                               id
                           )
                               )
                           ''')

            # 시스템 메트릭 테이블
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS system_metrics
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               metric_name
                               TEXT,
                               metric_value
                               REAL,
                               server_instance
                               TEXT,
                               timestamp
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           )
                           ''')

            # 인덱스 생성
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_user_id ON access_logs(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON access_logs(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_metrics_name ON system_metrics(metric_name)')

            # 샘플 데이터 삽입
            self._insert_sample_data(cursor)

            conn.commit()
            conn.close()

            self.logger.info("✅ 데이터베이스 초기화 완료")

        except Exception as e:
            self.logger.error(f"❌ 데이터베이스 초기화 실패: {e}")
            raise

    def _insert_sample_data(self, cursor):
        """샘플 데이터 삽입"""
        sample_users = [
            ('admin', 'admin@company.com'),
            ('user1', 'user1@company.com'),
            ('user2', 'user2@company.com'),
            ('developer', 'dev@company.com'),
            ('tester', 'test@company.com'),
            ('testuser', 'testuser@company.com'),
            ('demo', 'demo@company.com'),
            ('test', 'test@company.com'),
            # 로드 테스터에서 사용할 추가 사용자들
            *[(f'user{i}', f'user{i}@company.com') for i in range(10, 51)]
        ]

        cursor.executemany(
            'INSERT OR IGNORE INTO users (username, email) VALUES (?, ?)',
            sample_users
        )

    def ensure_users_exist(self, usernames: List[str]):
        """
        주어진 사용자명 목록이 데이터베이스에 존재하도록 보장합니다.
        이미 존재하는 사용자는 무시하고, 없는 사용자만 추가합니다.
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()

                # (username, email) 형태의 튜플 리스트 생성
                # 테스트용이므로 이메일은 간단하게 만듭니다.
                users_to_add = [(username, f'{username}@test.com') for username in usernames]

                # INSERT OR IGNORE: 프라이머리 키(username)가 중복되면 무시합니다.
                cursor.executemany(
                    'INSERT OR IGNORE INTO users (username, email) VALUES (?, ?)',
                    users_to_add
                )

                conn.commit()
                conn.close()

                self.logger.info(f"{cursor.rowcount}명의 신규 테스트 사용자를 DB에 추가했습니다.")
                return True
            except Exception as e:
                self.logger.error(f"테스트 사용자 추가 중 오류 발생: {e}")
                return False

    def get_user(self, username: str) -> Optional[Dict]:
        """사용자 정보 조회"""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()

                cursor.execute('''
                               SELECT id, username, email, created_at, last_access, is_active
                               FROM users
                               WHERE username = ?
                                 AND is_active = TRUE
                               ''', (username,))

                result = cursor.fetchone()
                conn.close()

                if result:
                    return {
                        'id': result[0],
                        'username': result[1],
                        'email': result[2],
                        'created_at': result[3],
                        'last_access': result[4],
                        'is_active': bool(result[5])
                    }

                return None

            except Exception as e:
                self.logger.error(f"사용자 조회 오류 ({username}): {e}")
                return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """ID로 사용자 정보 조회"""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()

                cursor.execute('''
                               SELECT id, username, email, created_at, last_access, is_active
                               FROM users
                               WHERE id = ?
                                 AND is_active = TRUE
                               ''', (user_id,))

                result = cursor.fetchone()
                conn.close()

                if result:
                    return {
                        'id': result[0],
                        'username': result[1],
                        'email': result[2],
                        'created_at': result[3],
                        'last_access': result[4],
                        'is_active': bool(result[5])
                    }

                return None

            except Exception as e:
                self.logger.error(f"사용자 조회 오류 (ID: {user_id}): {e}")
                return None

    def update_last_access(self, user_id: int):
        """사용자 마지막 접근 시간 업데이트"""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()

                cursor.execute('''
                               UPDATE users
                               SET last_access = CURRENT_TIMESTAMP
                               WHERE id = ?
                               ''', (user_id,))

                conn.commit()
                conn.close()

            except Exception as e:
                self.logger.error(f"마지막 접근 시간 업데이트 오류 (ID: {user_id}): {e}")

    def log_access(self, user_id: Optional[int], endpoint: str, method: str,
                   status_code: int, response_time: float, server_instance: str,
                   ip_address: str = "", user_agent: str = ""):
        """접근 로그 기록"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute('''
                           INSERT INTO access_logs
                           (user_id, endpoint, method, status_code, response_time,
                            server_instance, ip_address, user_agent)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (user_id, endpoint, method, status_code, response_time,
                                 server_instance, ip_address, user_agent))

            conn.commit()
            conn.close()

            # 사용자가 있으면 마지막 접근 시간 업데이트
            if user_id:
                self.update_last_access(user_id)

        except Exception as e:
            self.logger.error(f"접근 로그 기록 오류: {e}")

    def record_metric(self, metric_name: str, metric_value: float,
                      server_instance: str):
        """시스템 메트릭 기록"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute('''
                           INSERT INTO system_metrics (metric_name, metric_value, server_instance)
                           VALUES (?, ?, ?)
                           ''', (metric_name, metric_value, server_instance))

            conn.commit()
            conn.close()

        except Exception as e:
            self.logger.error(f"메트릭 기록 오류: {e}")

    def get_statistics(self) -> Dict:
        """데이터베이스 통계 정보 조회"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            # 총 사용자 수
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = TRUE')
            total_users = cursor.fetchone()[0]

            # 총 요청 수
            cursor.execute('SELECT COUNT(*) FROM access_logs')
            total_requests = cursor.fetchone()[0]

            # 평균 응답 시간
            cursor.execute('SELECT AVG(response_time) FROM access_logs')
            avg_response_time = cursor.fetchone()[0] or 0

            # 최근 24시간 요청 수
            cursor.execute('''
                           SELECT COUNT(*)
                           FROM access_logs
                           WHERE timestamp > datetime('now', '-1 day')
                           ''')
            recent_requests = cursor.fetchone()[0]

            # 서버별 요청 통계
            cursor.execute('''
                           SELECT server_instance, COUNT(*), AVG(response_time)
                           FROM access_logs
                           WHERE timestamp > datetime('now', '-1 day')
                           GROUP BY server_instance
                           ''')
            server_stats = cursor.fetchall()

            # 상태 코드별 통계
            cursor.execute('''
                           SELECT status_code, COUNT(*)
                           FROM access_logs
                           WHERE timestamp > datetime('now', '-1 day')
                           GROUP BY status_code
                           ''')
            status_stats = cursor.fetchall()

            # 가장 활발한 사용자들
            cursor.execute('''
                           SELECT u.username, COUNT(al.id) as request_count
                           FROM users u
                                    JOIN access_logs al ON u.id = al.user_id
                           WHERE al.timestamp > datetime('now', '-1 day')
                           GROUP BY u.id, u.username
                           ORDER BY request_count DESC LIMIT 10
                           ''')
            active_users = cursor.fetchall()

            conn.close()

            return {
                'overview': {
                    'total_users': total_users,
                    'total_requests': total_requests,
                    'avg_response_time': round(avg_response_time, 3),
                    'recent_requests': recent_requests
                },
                'server_breakdown': {
                    stat[0]: {
                        'requests': stat[1],
                        'avg_response_time': round(stat[2] or 0, 3)
                    } for stat in server_stats
                },
                'status_codes': {
                    str(stat[0]): stat[1] for stat in status_stats
                },
                'active_users': [
                    {'username': stat[0], 'requests': stat[1]}
                    for stat in active_users
                ],
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"통계 조회 오류: {e}")
            return {
                'overview': {
                    'total_users': 0,
                    'total_requests': 0,
                    'avg_response_time': 0,
                    'recent_requests': 0
                },
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def get_recent_logs(self, limit: int = 100, hours: int = 24) -> List[Dict]:
        """최근 접근 로그 조회"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT al.*, u.username
                FROM access_logs al
                LEFT JOIN users u ON al.user_id = u.id
                WHERE al.timestamp > datetime('now', '-{} hours')
                ORDER BY al.timestamp DESC
                LIMIT ?
            '''.format(hours), (limit,))

            columns = [desc[0] for desc in cursor.description]
            logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

            conn.close()
            return logs

        except Exception as e:
            self.logger.error(f"최근 로그 조회 오류: {e}")
            return []

    def cleanup_old_logs(self, days: int = 30):
        """오래된 로그 정리"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            # 오래된 접근 로그 삭제
            cursor.execute('''
                DELETE FROM access_logs 
                WHERE timestamp < datetime('now', '-{} days')
            '''.format(days))

            deleted_logs = cursor.rowcount

            # 오래된 메트릭 삭제
            cursor.execute('''
                DELETE FROM system_metrics 
                WHERE timestamp < datetime('now', '-{} days')
            '''.format(days))

            deleted_metrics = cursor.rowcount

            conn.commit()
            conn.close()

            self.logger.info(f"정리 완료: 로그 {deleted_logs}개, 메트릭 {deleted_metrics}개 삭제")

            return {
                'deleted_logs': deleted_logs,
                'deleted_metrics': deleted_metrics
            }

        except Exception as e:
            self.logger.error(f"로그 정리 오류: {e}")
            return {'error': str(e)}

    def health_check(self) -> Dict:
        """데이터베이스 헬스 체크"""
        try:
            conn = sqlite3.connect(self.db_file, timeout=5)
            cursor = conn.cursor()

            # 간단한 쿼리 실행
            cursor.execute('SELECT COUNT(*) FROM users')
            user_count = cursor.fetchone()[0]

            conn.close()

            return {
                'status': 'healthy',
                'user_count': user_count,
                'db_file': self.db_file,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"데이터베이스 헬스 체크 실패: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'db_file': self.db_file,
                'timestamp': datetime.now().isoformat()
            }


# 전역 데이터베이스 서비스 인스턴스
db_service = DatabaseService()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('DatabaseServiceTest')

    logger.info("🗄️ 데이터베이스 서비스 테스트")

    # 헬스 체크
    health = db_service.health_check()
    logger.info(f"헬스 체크: {health}")

    # 사용자 조회 테스트
    user = db_service.get_user('admin')
    logger.info(f"관리자 사용자: {user}")

    # 접근 로그 기록 테스트
    db_service.log_access(user['id'] if user else None, '/test', 'GET', 200, 150.5, 'test-server')
    logger.info("테스트 접근 로그가 기록되었습니다.")

    # 통계 조회 테스트
    stats = db_service.get_statistics()

    logger.info(f"통계 조회 완료. 총 사용자: {stats.get('overview', {}).get('total_users')}")