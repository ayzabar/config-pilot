# using a slim python image to keep it light
from python:3.11-slim

# setting the working directory inside the container
workdir /app

# copying requirements first to leverage docker cache
copy requirements.txt .
run pip install --no-cache-dir -r requirements.txt

# copying the rest of the code
copy . .

# firing up the service
cmd ["python", "main.py"]
