FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 로드 밸런서는 7100번 포트를 사용합니다.

EXPOSE 7100
CMD ["python", "load_balancer.py"]