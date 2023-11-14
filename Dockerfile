FROM python:3.11-alpine3.18 as base
RUN apk update
RUN apk add openssl openssl-dev
RUN mkdir -p /app
WORKDIR /app

FROM base as build
RUN apk add build-base libffi-dev
RUN pip install poetry==1.6.1
RUN poetry config virtualenvs.in-project true
COPY poetry.lock pyproject.toml /app/
RUN poetry install --only main --no-interaction --no-root

FROM base as runtime
COPY --from=build /app/.venv /app/.venv
COPY ./eq /app
VOLUME /app/config
ENV PATH=/app/.venv/bin:$PATH
ENV ENVIRONMENT "production"
ENV CENTRAL_URL "https://app.eventqueue.io"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
