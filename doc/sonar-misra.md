# sonar-misra

Exports a MISRA C++:2023 report (All issues in violation of MISRA C++:2023 rules).

Basic Usage: `sonar-misra [--tags <tag>,<tag>,...] -f <file>`
- `-f`: Define the output file, if not specified `stdout` is used
- `--tags`: Defines the MISRA tags to export. By default this is `misra-c++2023` and that is the only tag that will output a strict and exhaustive MISRA report.
  Other tags that may be used are:
  - `misra-c++2008`: Incomplete list of MISRA C++2008 violations (report is not exhaustive, not all rules are covered)
  - `misra-c2004`, `misra-c2012`: : Incomplete list of MISRA C2004 or C2012 rules (report is not exhaustive, not all rules are covered)
  - `misra-mandatory`, `misra-required`, `misra-advisory`, `misra-directive`: Subset of MISRA C++2023 violation of mandatory, required, advisory and directive rules
- `-h`, `-u`, `-t`, `-o`, `-v`, `-l`, `--httpTimeout`, `--threads`, `--clientCert`: See **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)


## Required Permissions

`sonar-misra` needs `Browse` permission on all projects, applications or portfolios for which MISRA violations are exported

## Requirements and Installation

`sonar-misra` is installed through the **sonar-tools** [general installation](https://github.com/okorach/sonar-tools/blob/master/README.md#install)

## Common command line parameters

`sonar-misra` accepts all the **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Exports all MISRA C++2023 violations from https://sonar.acme-corp.com, in CSV or in JSON
sonar-misra -f misra-report.csv
sonar-rules -f misra-report.json

# Exports MISRA C++2023 violations for project key <projectKey>
sonar-misra -k <projectKey> -f misra-report.csv
# Exports MISRA C++2023 violations for project key <projectKey> sorted by issue id (send to stdout and redirected in a file after sorting)
sonar-misra -k <projectKey> | sort > misra-report.csv

# MISRA report of only MISRA C++2023 mandatory and required rules violations
sonar-misra -k <projectKey> --tags misra-mandatory,misra-required -f misra-report.csv

# MISRA report of MISRA C2012 rules violations (ruleset is not entirely covered, the report will be incompleted)
sonar-misra -k <projectKey> --tags misra-c2012 -f misra-report.csv
```
