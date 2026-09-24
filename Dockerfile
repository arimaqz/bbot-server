FROM ghcr.io/astral-sh/uv:python3.11-trixie
RUN apt-get -y update && apt-get -y install curl jq p7zip-full
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN cp bbot_server/defaults_docker.yml bbot_server/defaults.yml
RUN uv sync --frozen
RUN useradd -u 1000 -m bbot \
    && mkdir -p /home/bbot/.config/bbot \
    && chown -R bbot:bbot /home/bbot /app
USER bbot
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8807
CMD ["uv", "run", "bbctl", "server", "start", "--api-only"]
