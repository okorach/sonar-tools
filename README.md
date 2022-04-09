# sonar-tools
Command line tools to help in SonarQube administration tasks.

![Downloads](https://img.shields.io/pypi/dm/sonar-tools?color=informational)
![Python-Versions](https://img.shields.io/pypi/pyversions/sonar-tools)
![License](https://img.shields.io/pypi/l/sonar-tools?color=informational)
![Issues](https://img.shields.io/github/issues/okorach/sonarqube-tools)
![Stars](https://img.shields.io/github/stars/okorach/sonarqube-tools?style=social)

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=okorach_sonarqube-tools)](https://sonarcloud.io/dashboard?id=okorach_sonarqube-tools)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonarqube-tools&metric=vulnerabilities)](https://sonarcloud.io/dashboard?id=okorach_sonarqube-tools)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonarqube-tools&metric=bugs)](https://sonarcloud.io/dashboard?id=okorach_sonarqube-tools)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonarqube-tools&metric=ncloc)](https://sonarcloud.io/dashboard?id=okorach_sonarqube-tools)

**DISCLAIMER**: This software is community software. None of the tools it contains are neither supported nor endorsed by SonarSource S.A. Switzerland, the company editing the [SonarQube](https://www.sonarqube.org/), [SonarCloud](https://sonarcloud.io) and [SonarLint](https://sonarlint.org) products

The following utilities are available:
- [sonar-audit](#sonar-audit): Audits a SonarQube instance, and reports all the problems
- [sonar-housekeeper](#sonar-housekeeper): Deletes projects, branches, PR  that have not been analyzed since a certain number of days, or
deletes tokens created since more than a certain number of days
- [sonar-loc](#sonar-loc): Computes lines of code per project and in total, as they would be coputed by the license
- [sonar-measures-export](#sonar-measures-export): Exports measures/metrics of one, several or all projects of the instance in CSV
- [sonar-findings-export](#sonar-findings-export) (Also available as **sonar-issues-export** (deprecated) for backward compatibility): Exports issues and hotspots (potentially filtered) from the instance in CSV
- [sonar-issues-sync](#sonar-issues-sync): Synchronizes issue changelog between branches, projects or even SonarQube instances
- [sonar-projects-export](#sonar-projects-export): Exports all projects from a SonarQube instance (EE and higher)
- [sonar-projects-import](#sonar-projects-import): Imports a list of projects into a SonarQube instance (EE and higher)

:information_source: Although they are likely to work with many versions, the offered tools are **only tested against SonarQube LTS (Long Term Support, currently 8.9.x) and LATEST versions**

# Release notes
See: https://github.com/okorach/sonarqube-tools/releases

# Requirements and Installation
- `sonar-tools` requires python 3.6 or higher
- Installation is based on [pip](/https://pypi.org/project/pip/).
- Online installation.
  - Run: `python3 -m pip install sonar-tools`
- Offline installation: If you have no access to the internet on the install machine, you can:
  - Download the `.whl` file from https://pypi.org/project/sonar-tools or attached to the release at https://github.com/okorach/sonarqube-tools/releases. The file should be something like. **sonar_tools-\<VERSION\>-py3-none-any.whl**
  - Copy the downloaded file on the install machine
  - On the install machine, run `python3 -m pip install sonar_tools-<VERSION>-py3-none-any.whl`
  - Note: The package is dependent upon `pytz`, `argparse`, `datetime`, `requests` and `jprops` python packages. If they are not already installed, you would need to install those packages before installing `sonar-tools`

# Common command line parameters

All tools accept the following common parameters:
- `-h` : Displays a help and exits
- `-u` : URL of the SonarQube server. The default is environment variable `$SONAR_HOST_URL`
or `http://localhost:9000` by default if the environment variable is not set
- `-t` : User token to invoke the SonarQube APIs, like `d04d671eaec0272b6c83c056ac363f9b78919b06`.
The default is environment variable `$SONAR_TOKEN`.
Using login/password is not possible.
The user corresponding to the token must have enough permissions to achieve the tool tasks
- `-v` : Logging verbosity level (`WARN`, `ÌNFO` or `DEBUG`). The default is `INFO`.
`ERROR` and above is always active.

# <a name="sonar-audit"></a>sonar-audit

`sonar-audit` allows to audit a SonarQube instance and output warning logs for all anomalies found.
See [complete documentation](https://github.com/okorach/sonarqube-tools/blob/master/sonar-audit.md) for details

# <a name="sonar-issues-sync"></a>sonar-issues-sync

`sonar-issues-sync` allows to synchronizes issue changelog (false positives, won't fix, issue severity or type change, tags and comments) between branches, projects or SonarQube instances.
See [complete documentation](https://github.com/okorach/sonarqube-tools/blob/master/sonar-issues-sync.md) for details

# <a name="sonar-housekeeper"></a>sonar-housekeeper

Deletes obsolete/outdated data from SonarQube:
- Projects whose last analysis date (on any branch) is older than a given number of days.
- User tokens older than a given number of days
- Inactive branches (Branches not analyzed for a given number of days), excepted branches marked as "keep when inactive"
- Inactive pull requests (PRs not analyzed for a given number of days)

Usage: `sonar-housekeeper [-u <url>] [-t <token>] [-P <days>] [-B <days>] [-R <days>] [-T <days>] [--mode delete] [-h]`

- `-P <days>`: Will search for projects not analyzed since more than `<days>` days.
To avoid deleting too recent projects it is denied to specify less than 90 days
- `-B <days>`: Will search for projects branches not analyzed since more than `<days>` days.
Branches marked as "keep when inactive" are excluded from housekeeping
- `-R <days>`: Will search for pull requests not analyzed since more than `<days>` days
- `-T <days>`: Will search for tokens created since more than `<days>` days
- `--mode delete`: If not specified, `sonar-housekeeper` will only perform a dry run and list projects
branches, pull requests and tokens that would be deleted.
If `--mode delete` is specified objects are actually deleted

## Required Permissions

To be able to delete anything, the token provided to `sonar-housekeeper` should have:
- The global `Administer System` permission to delete tokens
- Plus `Browse` and `Administer` permission on all projects to delete (or with branches or PR to delete)

### :information_source: Limitations
To avoid bad mistakes (mistakenly deleting too many projects), the tools will refuse to delete projects analyzed in the last 90 days.

### :warning: Database backup
**A database backup should always be taken before executing this script. There is no recovery.**

### Example
```
sonar-housekeeper -o 120 -u https://sonar.acme-corp.com -t 15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d
```

# <a name="sonar-loc"></a>sonar-loc

Exports all projects lines of code as they would be counted by the commercial licences.  
See `sonar-loc -h` for details

Basic Usage: `sonar-loc [-u <url>] [-t <token>] [-a] [-n] [--withURL] >locs.csv`  
- `--portfolios`: Output the LOC of portfolios instead of projects (Enterprise Edition only)
- `--topLevelOnly`: For portfolios, only output LoCs for top level portfolios (Enterprise Edition only)
- `-n | --withName`: Outputs the project or portfolio name in addition to the key
- `-a | --withLastAnalysis`: Output the last analysis date (all branches and PR taken into account) in addition to the LOCs
- `--withURL`: Outputs the URL of the project or portfolio for each record

## Required Permissions

`sonar-loc` needs `Browse` permission on all projects of the SonarQube instance

# <a name="sonar-measures-export"></a>sonar-measures-export

Exports one or all projects with all (or some selected) measures in a CSV file.  
The CSV is sent to standard output.  
Plenty of issue filters can be specified from the command line, type `sonar-measures-export -h` for details

Basic Usage: `sonar-measures-export [-u <url>] [-t <token>] -m _main [-b] [-r] [-p] [-d] [-f json|csv] [--includeURLs] [-o <outputFile>]`  
- `-m | --metricKeys`: comma separated list of metrics to export
  - `-m _main` is a shortcut to list all main metrics. It's the recommended option  
  - `-m _all` is a shortcut to list all metrics, including the most obscure ones
- `-b | --withBranches`: Exports measures for all project branches (by default only export measures of the main branch)
- `-r | --ratingsAsNumbers`: Converts ratings as numbers (by default ratings are exported as letters between A and E)
- `-p | --percentsAsString`: Converts percentages as strings "xy.z%" (by default percentages are exported as floats between 0 and 1)
- `-d | --datesWithoutTime`: Outputs dates without time
- `-f`: Choose export format between csv (default) and json
- `-o`: Define file for output (default stdout). File extension is used to deduct expected format (json if file.json, csv otherwise)
- `-n | --withName`: Outputs the project or portfolio name in addition to the key
- `-a | --withLastAnalysis`: Output the last analysis date (all branches and PR taken into account) in addition to the LOCs
- `--withURL`: Outputs the URL of the project or portfolio for each record

## Required Permissions

`sonar-measures-export` needs `Browse` permission on all projects of the SonarQube instance

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Exports LoCs, nbr of bugs and number of vulnerabilities of all projects main branch
sonar-measures-export -m ncloc,bugs,vulnerabilities >measures.csv

# Exports main metrics of all projects and all their branches
sonar-measures-export -m _main -b -o measures.json

# Exports all metrics of projects myProjectKey1 and myOtherProjectKey main branch. Convert ratings to letters
sonar-measures-export -k myProjectKey1,myOtherProjectKey -m _all -r -o all_measures.csv
```

# <a name="sonar-findings-export"></a>sonar-findings-export
(Also available as `sonar-issues-export` for backward compatibility, but **deprecated**)

Exports a list of issues as CSV  or JSON. The export is sent to standard output or into a file
Plenty of issue filters can be specified from the command line, type `sonar-findings-export -h` for details.  
:warning: On large SonarQube instances with a lot of issues, it can be stressful for the instance (many API calls) and very long to export all issues. It's recommended to define filters that will only export a subset of all issues (see examples below).

## Required Permissions

`sonar-findings-export` needs `Browse` permission on all projects for which findings are exported

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Exports all issues (main branch). This can be very long and stressful for SonarQube APIs
sonar-findings-export >all_issues.csv

# Exports all issues of project myProjectKey
sonar-findings-export -k myProjectKey -o project_issues.csv

# Exports all false positive and won't fix issues across all projects
sonar-findings-export -r FALSE-POSITIVE,WONTFIX -o fp_wf.json

# Exports all issues created in 2020
sonar-findings-export -a 2020-01-01 -b 2020-12-31 -o issues_created_in_2020.csv

# Exports all vulnerabilities and bugs
sonar-findings-export -types VULNERABILITY,BUG -f json >bugs_and_vulnerabilities.json
```

# <a name="sonar-projects-export"></a>sonar-projects-export

Exports all projects of a given SonarQube instance.  
:warning: This requires a SonarQube Enterprise or Data Center Edition.  
It sends to the output a CSV with the list of project keys, the export result (`SUCCESS` or `FAIL`), and:
- If the export was successful, the generated zip file
- If the export was failed, the failure reason

:information_source: All zip files are generated in the SonarQube instance standard location (under `data/governance/project_dumps/export`). On a DCE, the export may be distributed over all the Application Nodes

The CSV file generated is to be used by the `sonar-projects-import` tool

## Required Permissions

`sonar-projects-export` requires `Administer project` permission on all projects to be exported

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d
sonar-projects-export >exported_projects.csv
```

# <a name="sonar-projects-import"></a>sonar-projects-import

Imports a list of projects previously exported with `sonar-projects-export`.  
:warning: This requires a SonarQube Enterprise or Data Center Edition.  
It takes as input a CSV file produced by `sonar-projects-export`

:information_source: All exported zip files must be first copied to the right location on the target SonarQube instance for the import to be successful (In `data/governance/project_dumps/import`)

## Required Permissions

`sonar-projects-import` needs the global `Create Projects` permission

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Import all projects with the CSV information file generated by "sonar-projects-export"
sonar-projects-import -f exported_projects.csv
```

# Tools coming soon

## sonar-issues-recover

Tries to recover issues that were mistakenly closed following a scan with incorrect parameters. This tool is only useful for SonarQube instances in version 7.9.x and lower since this feature is built-in with SonarQube 8.x and higher

Issue recovery means:
- Reapplying all transitions to the issue to reach its final state before close (Usually *False positive* or *Won't Fix*)
- Reapplying all manual comments
- Reapplying all severity or issue type change

### :information_source: Limitations
- The script has to be run before the closed issue purge period (SonarQube parameter `sonar.dbcleaner.daysBeforeDeletingClosedIssues` whose default value is **30 days**)
- The recovery is not 100% deterministic. In some rare corner cases (typically less than 5%) it is not possible to determine that an issue was closed unexpectedly, in which case the issue is not recovered. The script will log those cases
- When recovering an issue all state change of the issue are applied with the user whose token is provided to the script (it cannot be applied with the original user). Some comments are added to mention who was the original user that made the change

### Examples
```
issues_recover.py -u <url> -t <token> -k <projectKey>
```

## sonar-project-history
Extracts the history of some given metrics for a given project

# License

Copyright (C) 2019-2022 Olivier Korach
mailto:olivier.korach AT gmail DOT com

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; if not, write to the Free Software Foundation,
Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
