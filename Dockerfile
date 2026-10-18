FROM node:22.23.0-alpine@sha256:ab07539e0988b63558ff621f5fbe1077054c39d9809112974fb79993949d41cd AS frontend
WORKDIR /build
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS api
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY aftershock ./aftershock
COPY fixtures ./fixtures
COPY --from=frontend /build/dist ./web/dist
EXPOSE 8000
CMD ["uvicorn", "aftershock.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS sandbox
WORKDIR /app
COPY sandbox ./sandbox
ENV SANDBOX_DIR=/data SERVICE_BASE_PORT=9000 PYTHONUNBUFFERED=1
VOLUME /data
CMD ["python", "-m", "sandbox.supervisor"]
