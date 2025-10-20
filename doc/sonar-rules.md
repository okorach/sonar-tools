# sonar-rules

Exports rules from a SonarQube Server or Cloud platform configuration.

Basic Usage: `sonar-rules -e -f <file>`
- `-f`: Define the output file, if not specified `stdout` is used
- `-e` or `--export`: Specify the export operation
- `-l` or `--languages`: Export only rules of given languages (comma separated, defined by they Sonar key, not its name)
- `--qualityProfiles`: Export rules defined in a given quality profile. In this case the `--languages` option is mandatory and should specify a single language
- `-u`, `-t`, `-h`, `-v`, `-l`, `--httpTimeout`, `--threads`: See **sonar-tools** [common parameters](../README.md#common-params)


## Required Permissions

`sonar-rules` needs simple browse permissions

## Requirements and Installation

`sonar-projects` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-projects` accepts all the **sonar-tools** [common parameters](../README.md#common-params)

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
