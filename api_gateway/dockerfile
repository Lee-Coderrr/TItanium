FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# API 게이트웨이는 8000번 포트를 사용합니다.
EXPOSE 8000
CMD ["python", "api_gateway.py"]