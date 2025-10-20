# sonar-findings-export
(Also available as `sonar-issues-export` for backward compatibility, but **deprecated**)

Exports a list of issues as CSV, JSON or SARIF format. The export is sent to standard output or into a file
Plenty of issue filters can be specified from the command line, type `sonar-findings-export -h` for details.
:warning: On large SonarQube Server or Cloud instances with a lot of issues, it can be stressful for the instance (many API calls) and very long to export all issues. It's recommended to define filters that will only export a subset of all issues (see examples below).

Basic Usage: `sonar-findings-export [--format csv|json|sarif] [--sarifNoCustomProperties] [-k <keyList>] ...`
- `--format csv|json|sarif`: Choose export format. Default is based on output file extension, and csv in last - `--sarifNoCustomProperties`: For SARIF export. By default all Sonar custom properties are exported which makes the SARIF export quite verbose. Use this option to not export the Sonar custom properties (only the SARIF standard ones)
- `--statuses <statusList>`: Only export findings with given statuses, comma separated among OPEN,CONFIRMED,REOPENED,RESOLVED,CLOSED,TO_REVIEW,REVIEWED
- `--resolutions <resolutionList>`: Only export findings with given resolution, comma separated among FALSE-POSITIVE,WONTFIX,FIXED,REMOVED,ACCEPTED,SAFE,ACKNOWLEDGED,FIXED
- `--severities <severityList>`: Only export findings with given resolution, comma separated among BLOCKER,CRITICAL,MAJOR,MINOR,INFO
- `--types <typeList>`: Only export findings with given type, comma separated among BUG,VULNERABILITY,CODE_SMELL,SECURITY_HOTSPOT
- `--createdAfter <YYYY-MM-DD>`: Only export findings created after a given date
- `--createdBefore <YYYY-MM-DD>`: Only export findings created before a given date
- `--tags <tagList>`: Comma separated list of tags corresponding to issues
- `--languages <languageList>`: Comma separated list of languages from whom findings should be exported
- `--useFindings`: Use SonarQube Server `api/projects/export_findings` whenever possible, No effect with SonarQube Cloud
- `-k <keyList>`: Comma separated list of keys of objects to export (all objects if not specified)
- `-b <branchList>`: For projects and apps, comma separated list of branches to export (Use * for all branches)
- `--datesWithoutTime`: Reports timestamps only with date, not time
resort

## Required Permissions

`sonar-findings-export` needs `Browse` permission on all projects, applications or portfolios for which findings are exported

## Requirements and Installation

`sonar-findings-export` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-findings-export` accepts all the **sonar-tools** [common parameters](../README.md#common-params)

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Exports all issues (main branch). This can be very long and stressful for SonarQube APIs
sonar-findings-export >all_issues.csv

# Exports all issues of project myProjectKey
sonar-findings-export -k myProjectKey -f project_issues.csv

# Exports all false positive and won't fix issues across all projects
sonar-findings-export -r FALSE-POSITIVE,WONTFIX -f fp_wf.json

# Exports all issues created in 2020
sonar-findings-export -a 2020-01-01 -b 2020-12-31 -f issues_created_in_2020.csv

# Exports all vulnerabilities and bugs
sonar-findings-export -types VULNERABILITY,BUG --format json >bugs_and_vulnerabilities.json

# Exports all vulnerabilities and bugs in SARIF format
sonar-findings-export -types VULNERABILITY,BUG --format sarif >bugs_and_vulnerabilities.sarif.json

# Export all findings of project myProjectKey in SARIF format without the custom Sonar properties
sonar-findings-export -k myProjectKey ----sarifNoCustomProperties -f myProjectKey.sarif
```
