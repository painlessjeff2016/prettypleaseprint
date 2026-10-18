FROM python:3.12-slim
WORKDIR /app
COPY services/3mf-converter/convert.py /app/convert.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TMPDIR=/tmp
USER 1000:1000
ENTRYPOINT ["python3", "/app/convert.py"]
