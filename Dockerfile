FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 bayesianqc

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=bayesianqc:bayesianqc alembic.ini ./
COPY --chown=bayesianqc:bayesianqc app ./app
COPY --chown=bayesianqc:bayesianqc migrations ./migrations

USER bayesianqc
EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
