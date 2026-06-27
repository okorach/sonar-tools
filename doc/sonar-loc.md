# sonar-loc

Exports all projects lines of code as they would be counted by the commercial licences.
See `sonar-loc -h` for details

Basic Usage: `sonar-loc [-f <file>] [--format csv|json] [-a] [-n] [-b <branchRegexp>] [-p] [--withTags] [--withURL] [--apps] [--portfolios] [--topLevelOnly] [--sortby <order>]`
- `-f`: Define file for output (default stdout). File extension is used to deduct expected format (json if file.json, csv otherwise)
- `--format`: Choose export format between csv (default) and json
- `--projects`: Output the LOC of projects (this is the default if nothing specified)
- `--apps`: Output the LOC of applications (Developer and higher editions)
- `--portfolios`: Output the LOC of portfolios (Enterprise and higher editions)
- `--topLevelOnly`: For portfolios, only output LoCs for top level portfolios (Enterprise Edition only)
- `-n | --withName`: Outputs the project or portfolio name in addition to the key
- `-a | --withLastAnalysis`: Output the last analysis date (all branches and PR taken into account) in addition to the LOCs
- `--withTags`: Outputs the tags of the project, app or portfolio
- `--withURL`: Outputs the URL of the project, app or portfolio for each record
- `-b` | `--branches`: On top of the projects or apps, export LoCs for each branches of targeted objects
- `-p` | `--pullRequests`: On top of the projects, export LoCs for each pull request
- `--sortby`: Sort order of the output, one of `key+`, `key-`, `ncloc+`, `ncloc-`, `lastAnalysis+`, `lastAnalysis-` (default `key+`). The `+`/`-` suffix selects ascending/descending order, sorting respectively by project key, lines of code, or last analysis date. When branches or pull requests are exported, `ncloc` sorts by the largest LoC across all branches/PRs of a project and `lastAnalysis` by the most recent analysis of any branch/PR
- `-h`, `-u`, `-t`, `-o`, `-v`, `-l`, `--httpTimeout`, `--threads`, `--clientCert`, `--skipCertVerify`: See **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

## Required Permissions

`sonar-loc` needs `Browse` permission on all projects of the Server or Cloud instance

## Requirements and Installation

`sonar-loc` is installed through the **sonar-tools** [general installation](https://github.com/okorach/sonar-tools/blob/master/README.md#install)

## Common command line parameters

`sonar-loc` accepts all the **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

## <a name="docker"></a>Using with Docker

See the [general Docker documentation](docker.md) for installation and background. Below are `sonar-loc`-specific examples.

```sh
# Export LoC for all projects to stdout
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-loc

# Redirect stdout to a local file (works on Linux, macOS and Windows PowerShell)
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-loc > loc.csv

# Write to a file using -f: mount the current directory so the file appears on the host
# Linux / macOS:
docker run --rm -v "$(pwd):/output" -w /output \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-loc -f loc.csv
# Windows (PowerShell):
docker run --rm -v "${PWD}:/output" -w /output `
  -e SONAR_TOKEN=$SONAR_TOKEN `
  -e SONAR_HOST_URL=https://sonar.acme.com `
  olivierkorach/sonar-tools sonar-loc -f loc.csv

# If SonarQube Server runs on localhost:
# Linux:
docker run --rm --network host \
  -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=http://localhost:9000 \
  olivierkorach/sonar-tools sonar-loc
# macOS / Windows:
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=http://host.docker.internal:9000 \
  olivierkorach/sonar-tools sonar-loc
```
