FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git tini \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

WORKDIR /app

COPY pyproject.toml poetry.lock* README.md ./
RUN poetry install --no-interaction --no-ansi --only main --no-root

COPY src/ ./src/
COPY assets/ ./assets/
COPY scripts/ ./scripts/
COPY /entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8501
ENV PYTHONPATH=/app/src
VOLUME ["/app/data"]

ENV STREAMLIT_SERVER_PORT=8501

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/entrypoint.sh"]
