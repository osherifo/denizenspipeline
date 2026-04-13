# ── Stage 1: Build frontend ──────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build
# Output lands in /build/fmriflow/server/static/


# ── Stage 2: Python runtime ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# System deps needed by numpy/scipy wheels and OpenMP
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -s /bin/bash fmriflow
WORKDIR /app

# Install Python package — copy only pyproject.toml first for layer caching
COPY --chown=fmriflow pyproject.toml ./
# Minimal install that pulls core + frontend + common analysis deps.
# Exclude cloud, flatten, audio, video, nlp to keep image small — users
# can install extras at runtime if needed.
RUN pip install --no-cache-dir ".[frontend,bids,viz,ml,himalaya]"

# Copy source
COPY --chown=fmriflow fmriflow/ fmriflow/

# Copy built frontend from Stage 1
COPY --from=frontend-build --chown=fmriflow \
     /build/fmriflow/server/static/ fmriflow/server/static/

# Install the package itself (editable so entry points work)
RUN pip install --no-cache-dir --no-deps -e .

# Switch to non-root
USER fmriflow

# Create conventional mount points
RUN mkdir -p /data/experiments /data/results /data/derivatives

ENV PATH="/home/fmriflow/.local/bin:$PATH"

EXPOSE 8421

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8421/api/plugins')" || exit 1

ENTRYPOINT ["fmriflow"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8421", \
     "--configs-dir", "/data/experiments", \
     "--results-dir", "/data/results", \
     "--derivatives-dir", "/data/derivatives"]


# ── Stage 3: Full image (optional target) ────────────────────────────────
FROM runtime AS full

USER root

# dcm2niix for DICOM conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
        dcm2niix \
    && rm -rf /var/lib/apt/lists/*

# Extra Python deps: autoflatten (JAX), cloud storage
RUN pip install --no-cache-dir "autoflatten>=0.1.0" "cottoncandy>=0.2" "boto3>=1.26"

USER fmriflow
