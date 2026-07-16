ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim

RUN mkdir code
WORKDIR code/

COPY requirements.txt .

# Build args (populated by GitHub Actions)
ARG GCP_PROJECT_ID
ARG GCP_REGISTRY_REGION
ARG GAR_TOKEN

RUN PIP_INDEX_URL="https://oauth2accesstoken:${GAR_TOKEN}@${GCP_REGISTRY_REGION}-python.pkg.dev/${GCP_PROJECT_ID}/pywares/simple" \
 && echo "Using index: $PIP_INDEX_URL" \
 && pip config set global.index-url "$PIP_INDEX_URL"
 
RUN pip install --verbose --no-cache-dir -r requirements.txt

COPY logging-config.yaml .
COPY app ./app

EXPOSE 8000

CMD python -m uvicorn app.main:app --workers 5 --host 0.0.0.0 --port 8000 --log-config logging-config.yaml
