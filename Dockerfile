FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt


FROM base AS test

ENV VERSION=test
ENV PYTHONPATH=/app/src
WORKDIR /app

COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt

COPY src/ src/
COPY tests/ tests/

RUN python -m compileall -q src tests
RUN coverage run -m pytest -q && coverage report


FROM base AS runtime

ARG VERSION=dev
ENV VERSION=${VERSION?}
WORKDIR /app

COPY --from=test /app/src/ /app/
COPY --chmod=755 docker/bin/ /usr/local/bin/
COPY compose.yml Dockerfile README.md requirements.txt /app/meta/
COPY deploy/ /app/meta/deploy/
COPY docs/ /app/meta/docs/

EXPOSE 8080
CMD ["main"]
