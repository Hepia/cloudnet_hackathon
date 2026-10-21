FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY 10-gen-files.sh /docker-entrypoint.d/10-gen-files.sh
RUN chmod +x /docker-entrypoint.d/10-gen-files.sh
