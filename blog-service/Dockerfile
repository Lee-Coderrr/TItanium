FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# templates와 static 디렉터리를 이미지 안으로 복사합니다.
COPY templates ./templates
COPY static ./static
COPY blog_service.py .

EXPOSE 8005

CMD ["python", "blog_service.py"]