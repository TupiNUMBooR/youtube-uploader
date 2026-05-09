FROM python:3.11-slim
ARG VERSION
ENV VERSION=${VERSION}
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    coreutils \
    curl \
    sed \
    grep \
    findutils \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x /app/scripts/*
ENV PATH="/app/scripts:${PATH}"

CMD ["bash", "/app/scripts/entrypoint.sh"]
