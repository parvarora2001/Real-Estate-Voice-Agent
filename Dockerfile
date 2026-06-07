# Hugging Face Spaces serves Docker apps on port 7860.
FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal — no audio/ML libraries needed anymore.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Lead reports are written here at runtime.
RUN mkdir -p leads && chmod -R 777 leads

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
