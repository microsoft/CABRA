FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        coreutils \
        curl \
        diffutils \
        file \
        findutils \
        gawk \
        grep \
        jq \
        less \
        patch \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        sed \
        tree \
        wget \
    && npm install --global "@github/copilot@1.0.81" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent

USER 10001:10001
WORKDIR /workspace

RUN copilot --version