FROM ghcr.io/astral-sh/uv:python3.11-trixie
RUN apt-get -y update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y install --no-install-recommends \
        curl jq p7zip-full git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN cp bbot_server/defaults_docker.yml bbot_server/defaults.yml
RUN uv sync --frozen
RUN sed -i 's/\r$//' bbot_server/*.sh
RUN useradd -u 1000 -m bbot \
    && mkdir -p /home/bbot/.config/bbot \
    && HOME=/home/bbot /app/.venv/bin/bbot --install-all-deps -y \
    && chown -R bbot:bbot /home/bbot /app
USER bbot
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8807
CMD ["uv", "run", "bbctl", "server", "start", "--api-only"]
