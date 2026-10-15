FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 marketstream \
    && mkdir -p /app/outputs \
    && chown -R marketstream:marketstream /app/outputs
COPY configs ./configs
USER marketstream
ENTRYPOINT ["marketstream"]
CMD ["run", "--format", "parquet"]
