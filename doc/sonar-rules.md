# sonar-rules

Exports rules from a SonarQube Server or Cloud platform configuration.

Basic Usage: `sonar-rules -e -f <file>`
- `-f`: Define the output file, if not specified `stdout` is used
- `-e` or `--export`: Specify the export operation
- `-l` or `--languages`: Export only rules of given languages (comma separated, defined by they Sonar key, not its name)
- `--qualityProfiles`: Export rules defined in a given quality profile. In this case the `--languages` option is mandatory and should specify a single language
- `-h`, `-u`, `-t`, `-o`, `-v`, `-l`, `--httpTimeout`, `--threads`, `--clientCert`, `--skipCertVerify`: See **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)


## Required Permissions

`sonar-rules` needs simple browse permissions

## Requirements and Installation

`sonar-projects` is installed through the **sonar-tools** [general installation](https://github.com/okorach/sonar-tools/blob/master/README.md#install)

## Common command line parameters

`sonar-projects` accepts all the **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Exports all rules from https://sonar.acme-corp.com, in CSV or in JSON
sonar-rules -f rules.csv
sonar-rules -f rules.json
# Exports rules for languages Java, C# and C++
sonar-rules --languages "java, cs, cpp" -f rules.csv
# Exports rules of quality profile "Sonar way" of language Java 
sonar-rules -u https://sonarqube.mycompany.com -t <myToken> --languages java --qualityProfile "Sonar way" >rules.csv
```

## <a name="docker"></a>Using with Docker

See the [general Docker documentation](docker.md) for installation and background. Below are `sonar-rules`-specific examples.

```sh
# Export rules to stdout
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-rules -e

# Redirect stdout to a local file (works on Linux, macOS and Windows PowerShell)
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-rules -e > rules.csv

# Write to a file using -f: mount the current directory so the file appears on the host
# Linux / macOS:
docker run --rm -v "$(pwd):/output" -w /output \
  -e SONAR_TOKEN=$SONAR_TOKEN \
  -e SONAR_HOST_URL=https://sonar.acme.com \
  olivierkorach/sonar-tools sonar-rules -e -f rules.csv
# Windows (PowerShell):
docker run --rm -v "${PWD}:/output" -w /output `
  -e SONAR_TOKEN=$SONAR_TOKEN `
  -e SONAR_HOST_URL=https://sonar.acme.com `
  olivierkorach/sonar-tools sonar-rules -e -f rules.csv

# If SonarQube Server runs on localhost:
# Linux:
docker run --rm --network host \
  -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=http://localhost:9000 \
  olivierkorach/sonar-tools sonar-rules -e
# macOS / Windows:
docker run --rm \
  -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=http://host.docker.internal:9000 \
  olivierkorach/sonar-tools sonar-rules -e
```
