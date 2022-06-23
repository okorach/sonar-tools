# sonar-tools
Command line tools to help in SonarQube administration tasks.

![Downloads](https://img.shields.io/pypi/dm/sonar-tools?color=informational)
![Python-Versions](https://img.shields.io/pypi/pyversions/sonar-tools)
![License](https://img.shields.io/pypi/l/sonar-tools?color=informational)
![Issues](https://img.shields.io/github/issues/okorach/sonar-tools)
![Stars](https://img.shields.io/github/stars/okorach/sonar-tools?style=social)

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=okorach_sonar-tools)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=vulnerabilities)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=bugs)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=ncloc)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)

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
- [sonar-config](#sonar-config): Exports a SonarQube platform as configuration as code (JSON file). Will soon allow to import the JSON to reconfigure a platform

:information_source: Although they are likely to work with many versions, the offered tools are **only tested against SonarQube LTS (Long Term Support, currently 8.9.x) and LATEST versions**

# Release notes
See: https://github.com/okorach/sonar-tools/releases

# Requirements and Installation
- `sonar-tools` requires python 3.6 or higher
- Installation is based on [pip](/https://pypi.org/project/pip/).
- Online installation.
  - Run: `python3 -m pip install sonar-tools`
- Offline installation: If you have no access to the internet on the install machine, you can:
  - Download the `.whl` file from https://pypi.org/project/sonar-tools or attached to the release at https://github.com/okorach/sonar-tools/releases. The file should be something like. **sonar_tools-\<VERSION\>-py3-none-any.whl**
  - Copy the downloaded file on the install machine
  - On the install machine, run `python3 -m pip install sonar_tools-<VERSION>-py3-none-any.whl`
  - Note: The package is dependent upon `pytz`, `argparse`, `datetime`, `python-dateutil`, `requests` and `jprops` python packages that are automatically installed when installing `sonar-tools`

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

See common [error exit codes](#exit-codes) at the bottom of this page

# <a name="sonar-audit"></a>sonar-audit

`sonar-audit` allows to audit a SonarQube instance and output warning logs for all anomalies found.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-audit.md) for details

# <a name="sonar-issues-sync"></a>sonar-issues-sync

`sonar-issues-sync` allows to synchronizes issue changelog (false positives, won't fix, issue severity or type change, tags and comments) between branches, projects or SonarQube instances.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-issues-sync.md) for details

# <a name="sonar-housekeeper"></a>sonar-housekeeper

Deletes obsolete/outdated data from SonarQube:
- Projects whose last analysis date (on any branch) is older than a given number of days.
- User tokens older than a given number of days
- Inactive branches (Branches not analyzed for a given number of days), excepted branches marked as "keep when inactive"
- Inactive pull requests (PRs not analyzed for a given number of days)

Usage: `sonar-housekeeper [-P <days>] [-B <days>] [-R <days>] [-T <days>] [--mode delete] [-h]`

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

Basic Usage: `sonar-loc [-f <file>] [--format json|csv] [-a] [-n] [--withURL] [--portfolios] [--topLevelOnly]`  
- `-f`: Define file for output (default stdout). File extension is used to deduct expected format (json if file.json, csv otherwise)
- `--format`: Choose export format between csv (default) and json
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

Basic Usage: `sonar-measures-export -m _main [-f <file>] [--format json|csv] [-b] [-r] [-p] [-d] [-d] [-n] [-a] [--withURL]`  
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

Basic Usage: `sonar-projects-export [--exportTimeout <timeout>] >exported_projects.csv`  
- `--exportTimeout`: Defines timeout to export a single project in seconds,
                     by default 180 s (large projects can take time to export)
- `-f`: Define file for output (default stdout). File extension is used to deduct expected format (json if file.json, csv otherwise)

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

Basic Usage: `sonar-projects-import -f <file.csv>`  
- `-f`: Define input file for project import, result of a `sonar-projects-export` command

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

# <a name="sonar-config"></a>sonar-config

Exports or imports all or part of a SonarQube platform configuration.
`sonar-config` is expected to export/import everything that is configurable in a SonarQube platform, except secrets

Basic Usage: `sonar-config --export -f <file.json>`  
- `-f`: Define the output file, if not specified `stdout` is used
- `-e` or `--export`: Specify the export operation
- `-w` or `--what`: Specify what to export (everything by default)
- `k "<key1>,<key2>,...,<keyn>"`: Will only import/export projects, apps or portfolios with matching keys
See [sonar-config complete doc](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md)

## Required Permissions

To export and import configuration, `sonar-config` needs elevated permissions.
See [sonar-config complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md) for details

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Exports all platform configuration from https://sonar.acme-corp.com
sonar-config -e >config.json
# Exports QG, portfolios, users and groups from platform configuration https://sonar.foobar-corp.com
sonar-config -u https://sonar.foobar-corp.com -t 15ee09df11fb9b8237b7a13333c5fce2e4e93d999 --export --what "qualitygates,portfolios,users,groups" -f partial_export.json

# Imports customized rules and quality profiles found in config.json (using $SONAR_HOST_URL as target)
sonar-config --import --what "rules,qualityprofiles" -f config.json
```

For more about what is exported and imported by `sonar-config` please see the [sonar-config complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md)


# <a name="exit-codes"></a>Exit codes

When tools complete successfully they return exit code 0. En case of fatal error the following exit codes may be returned:
- Code 1: Authentication error (Incorrect token provided)
- Code 2: Authorization error (provided token has insufficient permissions)
- Code 3: Other general Sonar API HTTP error
- Code 4: No token provided
- Code 5: Non existing project key provided
- Code 6: Incorrect finding search criteria provided
- Code 7: Unsupported operation requested (because of SonarQube edition or configuration)
- Code 8: Audit rule loading failed (at startup)
- Code 9: SIF audit error (file not found, can't open file, not a legit JSON file, ...)
- Code 10: Incorrect command line arguments

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
