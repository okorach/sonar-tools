# Using sonar-tools in Docker

Starting from version 3.4 `sonar-tools` is available as a docker image.

## Installation

```sh
docker pull olivierkorach/sonar-tools:latest
```

## Basic usage

Pass your SonarQube URL and token as environment variables (recommended over `-u`/`-t` flags so they don't appear in the process list):

```sh
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-loc
```

## Capturing output

Most tools write to **stdout** by default. Redirect to a local file using your shell's `>` operator — this works on Linux, macOS and Windows PowerShell:

```sh
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-loc > loc.csv
```

If you prefer the `-f <file>` flag instead of redirection, the file is written **inside** the container and is not available on the host unless you mount a volume.

Mount the current directory so the output file appears on the host after the command completes:

```sh
# Linux / macOS
docker run --rm -v "$(pwd):/output" -w /output \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-loc -f loc.csv

# Windows (PowerShell)
docker run --rm -v "${PWD}:/output" -w /output `
  -e SONAR_TOKEN=$SONAR_TOKEN `
  -e SONAR_HOST_URL=https://sonar.acme.com `
  olivierkorach/sonar-tools sonar-loc -f loc.csv
```

## Providing input files

For tools that read a local file (e.g. `sonar-config -i -f config.json`), mount the directory containing that file:

```sh
# Linux / macOS
docker run --rm -v "$(pwd):/data" -w /data \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-config -i -f config.json

# Windows (PowerShell)
docker run --rm -v "${PWD}:/data" -w /data `
  -e SONAR_TOKEN=$SONAR_TOKEN `
  -e SONAR_HOST_URL=https://sonar.acme.com `
  olivierkorach/sonar-tools sonar-config -i -f config.json
```

## SonarQube Server on localhost

Containers cannot reach `localhost` on the host by default.

```sh
# Linux — use --network host so localhost resolves to the host
docker run --rm --network host \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=http://localhost:9000 \
  olivierkorach/sonar-tools sonar-loc

# macOS / Windows — Docker Desktop maps host.docker.internal to the host
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=http://host.docker.internal:9000 \
  olivierkorach/sonar-tools sonar-loc
```

## Per-tool examples

Each tool's documentation includes its own Docker usage section with copy-paste examples specific to that tool:

- [sonar-audit](sonar-audit.md#docker)
- [sonar-config](sonar-config.md#docker)
- [sonar-findings-export](sonar-findings-export.md#docker)
- [sonar-findings-sync](sonar-findings-sync.md#docker)
- [sonar-housekeeper](sonar-housekeeper.md#docker)
- [sonar-loc](sonar-loc.md#docker)
- [sonar-maturity](sonar-maturity.md#docker)
- [sonar-measures-export](sonar-measures-export.md#docker)
- [sonar-misra](sonar-misra.md#docker)
- [sonar-projects](sonar-projects.md#docker)
- [sonar-rules](sonar-rules.md#docker)
