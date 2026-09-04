FROM node:20-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/
COPY backend/ ./backend/
RUN pip install --no-cache-dir .
COPY --from=frontend-build /src/frontend/dist ./frontend-dist
COPY docker-entrypoint.sh /usr/local/bin/lorex-entrypoint
RUN chmod +x /usr/local/bin/lorex-entrypoint && mkdir -p /config /downloads /library
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/lorex-entrypoint"]
CMD ["uvicorn", "lorex.main:app", "--host", "0.0.0.0", "--port", "8000"]
