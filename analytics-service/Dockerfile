# 1. 베이스 이미지 선택 (안정적인 파이썬 3.11 슬림 버전)
FROM python:3.11-slim

# 2. 작업 디렉터리 설정
WORKDIR /app

# 3. 의존성 파일 먼저 복사 및 설치 (캐싱 효율성 증대)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 나머지 소스 코드 복사
COPY . .

# 5. 서비스가 사용하는 포트 노출
EXPOSE 8004

# 6. 컨테이너가 시작될 때 실행할 명령어
CMD ["python", "service.py"]