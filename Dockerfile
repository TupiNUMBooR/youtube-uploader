FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt


FROM base AS test

ENV VERSION=test
WORKDIR /project

COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt

COPY app/ app/
COPY tests/ tests/

RUN python -m compileall -q app tests
RUN coverage run -m pytest -q && coverage report


FROM base AS runtime

ARG VERSION=dev
ENV VERSION=${VERSION?}
WORKDIR /app

COPY --from=test /project/app/ /app/
COPY Dockerfile compose.yml .dockerignore README.md requirements*.txt /app/meta/
COPY deploy/ /app/meta/deploy/

EXPOSE 8080
CMD ["python3", "/app/main.py"]
