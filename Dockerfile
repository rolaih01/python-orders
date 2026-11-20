# Imagen normal de python-orders, para desplegarla en cualquier máquina. Crixol no la usa:
# para los sandboxes está el `Dockerfile.crixol`.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Proyecto/ .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
