FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir jsonschema

COPY app.py .

EXPOSE 5003

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "app.py"]
CMD ["--listen", "0.0.0.0:5003"]
