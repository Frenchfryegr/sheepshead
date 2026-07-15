FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fsSL https://github.com/supabase/cli/releases/download/v2.109.1/supabase_linux_amd64.tar.gz \
       | tar xz -C /usr/local/bin supabase \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

RUN groupadd --system app && useradd --system --create-home --home-dir /home/app --gid app app && chown -R app:app /app /home/app
USER app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
