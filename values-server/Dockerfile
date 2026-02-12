FROM python:3.11-slim

WORKDIR /app

COPY app.py .

EXPOSE 5002

ENTRYPOINT ["python", "app.py"]
CMD ["--schema-dir", "/data/values", "--listen", "0.0.0.0:5002"]
