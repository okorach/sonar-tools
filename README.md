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
- **sonar-audit**: Audits a SonarQube instance
- **sonar-housekeeper**: Deletes projects that have not been analyzed since a certain number of days, or
deletes tokens created since more than a certain number of days
- **sonar-measures-export**: Exports measures/metrics of one, several or all projects of the instance in CSV
- **sonar-issues-export**: Exports issues (potentially filtered) from the instance in CSV
- **sonar-issues-sync**: Synchronizes issue changelog between branches, projects or even SonarQube instances
- **sonar-projects-export**: Exports all projects from a SonarQube instance (EE and higher)
- **sonar-projects-import**: Imports a list of projects into a SonarQube instance (EE and higher)

:information_source: Although they are likely to work with many versions, the offered tools are **only tested against SonarQube LTS (Long Term Support, currently 8.9.x) and LATEST versions**

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
or `http://localhost:9000` if not env variable is not set
- `-t` : User token to invoke the SonarQube APIs, like `d04d671eaec0272b6c83c056ac363f9b78919b06`.
The default is environment variable `$SONAR_TOKEN`.
Using login/password is not possible.
The user corresponding to the token must have enough permissions to achieve the tool tasks
- `-v` : Logging verbosity level (`WARN`, `ÌNFO` or `DEBUG`). The default is `INFO`.
`ERROR` and above is always active.

# sonar-audit

Audits the SonarQube instance and output warning logs whenever a suspicious or incorrect setting/situation is found.
The detail of what is audited is listed at the bottom of this (long) page

Usage: `sonar-audit [-u <url>] [-t <token>] [--what [settings|projects|qg|qp|users]] [-h]`

`--what` can be followed by a list of comma separated items
When `--what` is not specified, everything is audited

- `--what settings`: Audits global settings and general system data (system info in particular)
- `--what qp`: Audits quality profiles
- `--what qg`: Audits quality gates
- `--what projects`: Audits all projects. This can be a fairly long operation
- `--what users`: Audits users and their tokens

### Example
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Audits everything
sonar-audit

# Audits global settings, quality profiles and quality gates
sonar-audit --what settings,qg,qp
```

<details>
  <summary>Click to see details of what is audited</summary>

- General checks:
  - Verifies that your SonarQube instance is an official distribution
  - Verifies that the `admin` user password is not the default value `admin`
  - DCE: Verifies that same plugins are installed on all app nodes
  - DCE: Verifies that all app nodes run the same version of SonarQube
  - DCE: Verifies that all nodes are in GREEN status
- General global settings:
  - `sonar.forceAuthentication` is `true`
  - `sonar.cpd.cross_project` is `false`
  - `sonar.core.serverBaseURL` is set
  - `sonar.global.exclusions` is empty
  - Project default visibility is `private`
- Global permissions:
  - Max 3 users with global admin, admin quality gates, admin quality profiles or create project permission
  - Max 10 users with global permissions
  - Group `Anyone` should have no global permissions
  - Group `sonar-users` should not have `Admin`, `Admin QG`, `Admin QP` or `Create Projects` permissions
  - Max 2 groups with global `admin`, `admin quality gates`, `admin quality profiles` permissions
  - Max 3 groups with `create project` permission
  - Max 10 groups with global permissions
- DB Cleaner:
  - Delay to delete inactive short lived branches (7.9) or branches (8.0+) between 10 and 60 days
  - Delay to delete closed issues between 10 and 60 days
  - `sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay` is between 12 and 240 hours (0.5 to 10 days)
  - `sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek` is between 2 and 12 weeks (0.5 to 3 months)
  - `sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth` is between 26 and 104 weeks (0.5 year to 2 years)
  - `sonar.dbcleaner.weeksBeforeDeletingAllSnapshots` is between 104 and 260 weeks (2 to 5 years)
- Maintainability rating grid:
  - A maintainability rating threshold is between 3% and 5%
  - B maintainability rating threshold is between 7% and 10%
  - C maintainability rating threshold is between 15% and 20%
  - D maintainability rating threshold is between 40% and 50%
- Environment
  - Web heap (`-Xmx`) is between 1 GB and 2 GB
  - CE heap (`-Xmx`) is between 512 MB per worker and 2 GB per worker
  - Maximum CE 4 workers
  - CE background tasks failure rate is less than 1%
  - Background tasks are not piling up: Less than 100 pending CE background tasks or more than 20 or 10 x Nbr workers
  - ES heap (`-Xmx`) is more than twice the ES index size (small indexes) or more than ES index size + 1 GB (large indexes)
- Quality Gates:
  - Unused QG
  - QG with 0 conditions or more than 7 conditions
  - QG not using the recommended metrics: `reliability`, `security`, `maintainibility`, `coverage`, `duplication`,
    `security review rating on new code`, `new bugs`, `new vulnerabilities`, `new hotspots`, `new blocker issues`, `new critical issues`, `new major issues`
    and `reliability rating on overall code` and `security rating on overall code`
  - Thresholds for the above metrics not consistent (non `A` for ratings on new code, non `0` for numeric count of issues,
    coverage not between 20% and 90%, duplication not between 1% and 3%, security and reliability on overall code lower than D)
  - More than 5 quality gates
- Quality Profiles:
  - QP not modified in 6 months
  - QP with less than 50% of all the available rules activated
  - QP not used by any projects
  - QP not used since more than 6 months
  - QP using deprecated rules
  - More than 5 QP for a given language
- Projects:
  - Projects provisioned but never analyzed
  - Projects not analyzed since 6 months (on any branch)
  - Projects with `public` visibility
  - Large projects with too much XML: Projects with more than 200K LoC and XML representing more than 50% of it
  - Permissions:
    - More than 5 different users with direct permissions (use groups)
    - More than 3 users with Project admin permission
    - More than 5 different groups with permissions on project
    - More than 1 group with execute analysis permission
    - More than 2 groups with issue admin permission
    - More than 2 groups with hotspot admin permission
    - More than 2 groups with project admin permission
- Users:
    - Tokens older than 90 days, or `audit.tokens.maxAge`
</details>

# sonar-housekeeper

Deletes all projects whose last analysis date (on any branch) is older than a given number of days.
Deletes user tokens older than a given number of days

Usage: `sonar-housekeeper [-u <url>] [-t <token>] -o days [-P] [-T] [--mode delete] [-h]`

- `-o <days>`: Minimum number of days since project last analysis (or token creation date).
To avoid deleting too recent projects it is denied to specify less than 90 days
- `-P`: Will search for projects not analyzed since more than so many days
- `-T`: Will search for tokens created since more than so many days
- `--mode delete`: If not specified, `sonar-housekeeper` will only perform a dry run and list projects
and tokens that would be deleted.
If specified projects and tokens are actually deleted

### :information_source: Limitations
To avoid bad mistakes (mistakenly deleting too many projects), the tools will refuse to delete projects analyzed in the last 90 days.

### :warning: Database backup
**A database backup should always be taken before executing this script. There is no recovery.**

### Example
```
sonar-housekeeper -o 120 -u https://sonar.acme-corp.com -t 15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d
```

# sonar-measures-export

Exports one or all projects with all (or some selected) measures in a CSV file.  
The CSV is sent to standard output.  
Plenty of issue filters can be specified from the command line, type `sonar-measures-export -h` for details

Basic Usage: `sonar-measures-export [-u <url>] [-t <token>] -m _main [-b] [-r] >measures.csv`  
- `-m`: comma separated list of metrics to export
  - `-m _main` is a shortcut to list all main metrics. It's the recommended option  
  - `-m _all` is a shortcut to list all metrics, including the most obscure ones
- `-b`: Exports measures for all project branches (by default only export measures of the main branch)
- `-r`: Converts ratings as letters (by default ratings are exported as numbers between 1 and 5)

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Exports LoCs, nbr of bugs and number of vulnerabilities of all projects main branch
sonar-measures-export -m ncloc,bugs,vulnerabilities >measures.csv

# Exports main metrics of all projects and all their branches
sonar-measures-export -m _main -b >main_measures.csv

# Exports all metrics of projects myProjectKey1 and myOtherProjectKey main branch. Convert ratings to letters
sonar-measures-export -k myProjectKey1,myOtherProjectKey -m _all -r >all_measures.csv
```

# sonar-issues-export

Exports a list of issues as CSV (sent to standard output)  
Plenty of issue filters can be specified from the command line, type `sonar-issues-export -h` for details.  
:warning: On large SonarQube instances with a lot of issues, it can be stressful for the instance (many API calls) and very long to export all issues. It's recommended to define filters that will only export a subset of all issues (see examples below).

## Limitations
`sonar-issue-export` does not export issues on branches (see [Issue #166](https://github.com/okorach/sonarqube-tools/issues/166)

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Exports all issues (main branch). This can be very long and stressful for SonarQube APIs
sonar-issues-export >all_issues.csv

# Exports all issues of project myProjectKey
sonar-issues-export -k myProjectKey >project_issues.csv

# Exports all false positive and won't fix issues across all projects
sonar-issues-export -r FALSE-POSITIVE,WONTFIX >fp_wf.csv

# Exports all issues created in 2020
sonar-issues-export -a 2020-01-01 -b 2020-12-31 >issues_created_in_2020.csv

# Exports all vulnerabilities and bugs
sonar-issues-export -types VULNERABILITY,BUG >bugs_and_vulnerabilities.csv
```

# sonar-issues-sync

Synchronizes issues changelog between:
- 2 branches of a same project
- The main branch of 2 different projects of a same SonarQube instance
- The main branch of 2 projects from different SonarQube instance

Issues changelog synchronization includes:
- Change of issue type
- Change of issue severity
- Issue marked as Won't fix or False positive
- Issue re-opened
- Custom tags added to the issue
- Issue comments

The source and target issues are synchronized ony when there is a 100% certainty that the issues are the same, and that the target issue currently has no changelog.
When a issue is synchronized, a special comment is added on the target issue with a link to the source one, for cross checking purposes
The tool sends to standard output a JSON file with, for each issue on the target branch or project:
- If the issue was synchonized
- If synchronized, the reference to the source issue
- If not synchronized, the reason for that. The reasons can be:
  - No match was found in the source branch/project
  - A match was found but the target issue already has a changelog
  - Multiple matches were found (list of all matches are given in the JSON)
  - A match was found but it is only approximate (ie not 100% certain match). The approximate match is provided in the JSON

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d

# Syncs issues from branch develop to branch master of project myProjKey
sonar-issues-sync -k myProjKey -b develop -B master >sync_2_branches.json

# Syncs issues from projectKey1 main branch to projectKey2 main branch
sonar-issues-sync -k projectKey1 -K projectKey2 >sync_2_projects.json

# Syncs issues from projectKey1 main branch to projectKey2 main branch
sonar-issues-sync -k myPorjectKey -U https://anothersonar.acme-corp.com -t d04d671eaec0272b6c83c056ac363f9b78919b06 -K otherInstanceProjKey >sync_2_instances.json
```

## :information_source: Limitations
- The sync is not 100% deterministic. In some rare corner cases (typically less than 5%) it is not possible to determine that an issue is the same between 2 branches or 2 SQ instances,in which case the issue is not sync'ed. The script will log those cases
- When sync'ing an issue, all changes of the target issue are applied with the user whose token is provided to the script (it cannot be applied with the user of the original issue). Some comments are added to mention who was the original user that made the change
- To be modified (sync'ed from a source issue), the target issue must has zero manual changes ie it must be has created originally by SonarQube
- `sonar-issues-sync` can't sync all branches of 2 different projects (of a same instance or different instances). See [Issue #162](https://github.com/okorach/sonarqube-tools/issues/162)

# sonar-projects-export

Exports all projects of a given SonarQube instance.  
:warning: This requires a SonarQube Enterprise or Data Center Edition.  
It sends to the output a CSV with the list of project keys, the export result (`SUCCESS` or `FAIL`), and:
- If the export was successful, the generated zip file
- If the export was failed, the failure reason

:information_source: All zip files are generated in the SonarQube instance standard location (under `data/governance/project_dumps/export`). On a DCE, the export may be distributed over all the Application Nodes

The CSV file generated is to be used by the `sonar-projects-import` tool

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d
sonar-projects-export >exported_projects.csv
```

# sonar-projects-import

Imports a list of projects previously exported with `sonar-projects-export`.  
:warning: This requires a SonarQube Enterprise or Data Center Edition.  
It takes as input a CSV file produced by `sonar-projects-export`

:information_source: All exported zip files must be first copied to the right location on the target SonarQube instance for the import to be successful (In `data/governance/project_dumps/import`)

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

Copyright (C) 2019-2021 Olivier Korach
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
