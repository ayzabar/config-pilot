FROM python:3.11-slim

WORKDIR /app

COPY app.py .

EXPOSE 5001

ENTRYPOINT ["python", "app.py"]
CMD ["--schema-dir", "/data/schemas", "--listen", "0.0.0.0:5001"]
