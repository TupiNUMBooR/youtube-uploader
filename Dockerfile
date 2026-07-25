FROM python:3.11-slim

ARG VERSION=dev
ENV VERSION=${VERSION?}
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

RUN python -m compileall -q /app

EXPOSE 8080
CMD ["python3", "/app/main.py"]
