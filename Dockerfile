FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y tzdata

ENV TZ=America/Sao_Paulo


COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo "{}" > status_incidentes.json && \
    echo "[]" > historico_logs.json && \
    echo "{}" > controle_prox_envio.json

EXPOSE 5000


CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--log-level", "info", "app:app"]