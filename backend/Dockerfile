FROM ghcr.io/astral-sh/uv:0.12.6 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /srv/opsflow/backend
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN useradd --uid 10001 --create-home appuser
ENV PATH="/srv/opsflow/backend/.venv/bin:$PATH"
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
