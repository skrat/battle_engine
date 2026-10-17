FROM python:3.14-alpine AS build

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# Copy code to container
COPY . /app
# Install dependencies
RUN apk update && apk add build-base
WORKDIR /app
RUN uv sync --locked --no-cache

# Copy to runtime container
FROM python:3.14-alpine
COPY --from=build /app /app
WORKDIR /app

CMD [ "/app/.venv/bin/fastapi", "run", "--port", "8000" ]
