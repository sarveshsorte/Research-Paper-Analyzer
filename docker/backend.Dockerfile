FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY document_pipeline/requirements.txt /tmp/document-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/document-requirements.txt
COPY . .
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
