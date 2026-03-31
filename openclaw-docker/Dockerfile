FROM node:22-slim

# Install curl for healthchecks + dependencies
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install modern Docker CLI (static binary) to avoid API version mismatch
# Host requires API 1.44+, Debian docker.io is often < 1.44
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-26.1.4.tgz | tar -xz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker

# Install OpenClaw globally from npm (official package)
RUN npm install -g openclaw@latest

# Create OpenClaw home directory
RUN mkdir -p /root/.openclaw/state

WORKDIR /root

# Expose gateway port
EXPOSE 18789

# Run the OpenClaw gateway
CMD ["openclaw", "gateway", "--port", "18789", "--bind", "lan", "--allow-unconfigured"]
