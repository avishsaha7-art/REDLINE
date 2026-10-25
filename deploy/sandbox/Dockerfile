# REDLINE Hardened Sandbox Runner
# Version: 1.0.0
# Base image: Official Python 3.11 slim bookworm pinned by OCI image index SHA-256 digest
# Upstream verification: docker-library/repo-info (remote/3.11-slim-bookworm.md)
FROM python:3.11-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf

LABEL org.opencontainers.image.title="REDLINE Sandbox Runner" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.description="Minimal hardened runner for isolated adversarial benchmark execution" \
      org.opencontainers.image.vendor="REDLINE Project" \
      org.opencontainers.image.licenses="Apache-2.0"

# Enforce clean environment and disable bytecode caching
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime test dependencies pinned strictly to exact versions
# Avoid any extra packages; clean apt caches and temporary files immediately
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
        iniconfig==2.0.0 \
        packaging==24.1 \
        pluggy==1.5.0 \
        pytest==8.3.3 \
        pytest-json-report==1.5.0 \
        coverage==7.6.1 \
    && find /usr/local -name "*.pyc" -delete

# Create non-root runner group and user (UID 1000 / GID 1000)
RUN groupadd -g 1000 redline && \
    useradd -u 1000 -g redline -m -s /bin/bash redline

# Prepare isolated workspace mount directory with non-root ownership
RUN mkdir -p /workspace && chown -R 1000:1000 /workspace

# Remove setuid and setgid bits across system binaries to prevent privilege escalation
RUN find / -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true

# Switch permanently to non-root execution context
USER 1000:1000
WORKDIR /workspace

# Safe default entrypoint: exits cleanly if executed without arguments
CMD ["python3", "-c", "import sys; sys.exit(0)"]
