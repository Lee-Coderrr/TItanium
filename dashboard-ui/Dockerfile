# 공식 Nginx 이미지를 사용합니다.
FROM nginx:1.27-alpine

# [수정] HTML과 JavaScript 파일을 모두 Nginx 웹 서버의 기본 폴더로 복사합니다.
COPY ./index.html /usr/share/nginx/html/index.html
COPY ./script.js /usr/share/nginx/html/script.js
