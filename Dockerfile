FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SABZ_STATE_PATH=/data/edge.sqlite3
WORKDIR /app
RUN mkdir /data && chown 10001:10001 /data
COPY sabz_edge/ /app/sabz_edge/
COPY config/ /app/config/
USER 10001:10001
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD python -c "import socket; s=socket.create_connection(('127.0.0.1',8099),2); s.close()" || exit 1
CMD ["python", "-m", "sabz_edge.server"]
