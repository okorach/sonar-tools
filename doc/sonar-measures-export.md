# <a name="sonar-measures-export"></a>sonar-measures-export

Exports one or all projects with all (or some selected) measures in a CSV file.
The CSV is sent to standard output.
Plenty of issue filters can be specified from the command line, type `sonar-measures-export -h` for details

Basic Usage: `sonar-measures-export -m _main [-f <file>] [--format csv|json] [-b] [-r] [-p] [-d] [-d] [-n] [-a] [--withURL]`
- `-m | --metricKeys`: comma separated list of metrics to export
  - `-m _main` is a shortcut to list all main metrics. It's the recommended option
  - `-m _all` is a shortcut to list all metrics, including the most obscure ones
- `-f`: Define file for output (default stdout). File extension is used to deduct expected format (json if file.json, csv otherwise)
- `--format`: Choose export format between csv (default) and json
- `-b | --withBranches`: Exports measures for all project branches (by default only export measures of the main branch)
- `-r | --ratingsAsNumbers`: Converts ratings as numbers (by default ratings are exported as letters between A and E)
- `-p | --percentsAsString`: Converts percentages as strings "xy.z%" (by default percentages are exported as floats between 0 and 1)
- `-d | --datesWithoutTime`: Outputs dates without time
- `-n | --withName`: Outputs the project or portfolio name in addition to the key
- `-a | --withLastAnalysis`: Output the last analysis date (all branches and PR taken into account) in addition to the LOCs
- `--withURL`: Outputs the URL of the project or portfolio for each record
- `--history`: Export measures history instead of only the last value
- `-h`, `-u`, `-t`, `-o`, `-v`, `-l`, `--httpTimeout`, `--threads`, `--clientCert`: See **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)


## Required Permissions

`sonar-measures-export` needs `Browse` permission on all projects of the SonarQube Server or Cloud instance

## Requirements and Installation

`sonar-measures-export` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-measures-export` accepts all the **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)


## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Exports LoCs, nbr of bugs and number of vulnerabilities of all projects main branch
sonar-measures-export -m ncloc,bugs,vulnerabilities >measures.csv

# Exports main metrics of all projects and all their branches
sonar-measures-export -m _main -b -f measures.json

# Exports all metrics of projects myProjectKey1 and myOtherProjectKey main branch. Convert ratings to letters
sonar-measures-export -k myProjectKey1,myOtherProjectKey -m _all -r -f all_measures.csv
```
