FROM node:22-slim

# Install curl for healthchecks + dependencies + docker CLI
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install OpenClaw globally from npm (official package)
RUN npm install -g openclaw@latest

# Create OpenClaw home directory
RUN mkdir -p /root/.openclaw/state

WORKDIR /root

# Expose gateway port
EXPOSE 18789

# Run the OpenClaw gateway — allow-unconfigured lets it start without crashing
# if the config file isn't detected (logs error but keeps running)
CMD ["openclaw", "gateway", "--port", "18789", "--bind", "lan", "--allow-unconfigured"]
