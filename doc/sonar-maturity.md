# sonar-maturity

Computes metrics related to the maturity of SonarQube usage. Can be use to implement changes that would improve the maturity and the value received from the product.

Basic Usage: `sonar-maturity [-k <projectKeyRegexp>] [-f <file>]`
- `-f`: Define the output file, if not specified `stdout` is used
- `-k`: Computes maturity metrics solely for the projects that match the regexp
- `-h`, `-u`, `-t`, `-o`, `-v`, `-l`, `--httpTimeout`, `--threads`, `--clientCert`: See **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)


## Required Permissions

`sonar-maturity` needs `Admin` permission on all projects

## Requirements and Installation

`sonar-maturity` is installed through the **sonar-tools** [general installation](https://github.com/okorach/sonar-tools/blob/master/README.md#install)

## Common command line parameters

`sonar-maturity` accepts all the **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Export maturity metrics for the entire platform
sonar-maturity -f maturity-report.json
```
