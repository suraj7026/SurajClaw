# Sandbox image used by tools.coding.gemini_cli.gemini_cli_run.
#
# Provides: git, gh CLI, Node 22, and the official @google/gemini-cli.
# Auth: reads GEMINI_API_KEY from env. (To use a subscription via OAuth,
# mount your gemini-cli auth dir onto /home/gemini/.gemini at run time.)
#
# Build once on the host:
#   docker build -t surajclaw-gemini-cli:latest surajclaw/docker/gemini-cli

FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl git openssh-client gnupg jq \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && chmod a+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gh \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @google/gemini-cli

# Non-root user so files created inside /work end up owned cleanly.
RUN useradd --create-home --shell /bin/bash gemini
USER gemini
WORKDIR /work

# Headless mode + auto-approve actions inside the sandbox. The host-side
# approval gate already paused before we got here.
ENV GEMINI_NONINTERACTIVE=1

ENTRYPOINT ["/bin/bash", "-lc"]
