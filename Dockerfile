# The environment ff check runs in, the same for CI and for anyone on Linux or WSL who prefers it to installing the
# tools: `ff docker check` builds this image locally (no registry) and runs `ff check` in it with the repository
# mounted. pjass is built from its pinned source; .NET 6 builds the runner and the balance tool.
FROM debian:bookworm-slim AS pjass
ARG PJASS_TAG=release-2026-06-15
ADD https://github.com/lep/pjass/archive/refs/tags/${PJASS_TAG}.tar.gz /pjass.tar.gz
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev make flex bison \
 && mkdir /pjass && tar -xzf /pjass.tar.gz -C /pjass --strip-components=1 \
 && make -C /pjass pjass VERSION=${PJASS_TAG} CFLAGS="-O2 -w -static"

# Debian bookworm: Python 3.11 (ff needs 3.10 or newer).
FROM mcr.microsoft.com/dotnet/sdk:6.0-bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-openpyxl lua5.3 git git-lfs \
 && rm -rf /var/lib/apt/lists/*
COPY --from=pjass /pjass/pjass /usr/local/bin/pjass
# CI runs its steps in this image: the checkout step is a JavaScript action and needs Node.js.
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
# NUGET_XMLDOC_MODE=none: the C#-to-Lua transpiler reads its templates from the packages' XML docs.
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 NUGET_XMLDOC_MODE=none HOME=/tmp
WORKDIR /repo
