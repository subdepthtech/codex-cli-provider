FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

ARG TARGETARCH

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
      bubblewrap \
      ca-certificates \
      curl \
      git \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
      amd64) \
        codex_arch="x86_64-unknown-linux-musl"; \
        codex_sha="f1e2bf9fa0ba6eb82119d621b6b71bc38edd33c06dc2867b31a027052358957d"; \
        ;; \
      arm64) \
        codex_arch="aarch64-unknown-linux-musl"; \
        codex_sha="8c9f31811d659fcc17c5f1a21bc0971984469c9e3a63c2b39b61cc7694f3a101"; \
        ;; \
      *) \
        echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; \
        exit 1; \
        ;; \
    esac; \
    codex_url="https://github.com/openai/codex/releases/download/rust-v0.141.0/codex-${codex_arch}.tar.gz"; \
    curl -fsSL "${codex_url}" -o /tmp/codex.tar.gz; \
    echo "${codex_sha}  /tmp/codex.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/codex-bin; \
    tar -xzf /tmp/codex.tar.gz -C /tmp/codex-bin; \
    codex_bin="$(find /tmp/codex-bin -type f | head -n 1)"; \
    test -n "${codex_bin}"; \
    install -m 0755 "${codex_bin}" /usr/local/bin/codex; \
    rm -rf /tmp/codex.tar.gz /tmp/codex-bin; \
    codex --version

WORKDIR /app

COPY --chmod=0644 requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --requirement /app/requirements.txt

COPY src /app/src
RUN find /app/src -type d -exec chmod 0755 {} + \
    && find /app/src -type f -exec chmod 0644 {} +

EXPOSE 8320

CMD ["uvicorn", "src.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8320", "--no-access-log"]
