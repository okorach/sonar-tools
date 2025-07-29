# sonar-tools
Command line tools to help in SonarQube administration tasks. Available as a **pypi.org** package or a **docker** image.

`sonar-tools` is compatible with SonarQube versions 9.9.x, LTA (2025.1.x as of June 2025), latest 2025.x (2025.3.x as of June 2025). It may work with older 9.x versions or intermediate 10.x versions but this is not guaranteed.
`sonar-tools` is also compatible with the **latest** SonarQube Community Build (25.6 as of June 2025).


![Downloads](https://img.shields.io/pypi/dm/sonar-tools?color=informational)
![Python-Versions](https://img.shields.io/pypi/pyversions/sonar-tools)
![License](https://img.shields.io/pypi/l/sonar-tools?color=informational)
![Issues](https://img.shields.io/github/issues/okorach/sonar-tools)
![Stars](https://img.shields.io/github/stars/okorach/sonar-tools?style=social)

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=okorach_sonar-tools)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=vulnerabilities)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=bugs)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=ncloc)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)

**DISCLAIMER**: This software is community software. None of the tools it contains are neither supported nor endorsed by SonarSource S.A. Switzerland, the company publishing the [SonarQube Server](https://www.sonarsource.com/products/sonarqube/), [SonarQube Cloud](https://sonarcloud.io) and [SonarQube for IDE (ex- SonarLint](https://www.sonarsource.com/products/sonarlint/) products

The following utilities are available:
- [sonar-audit](#sonar-audit): Audits a SonarQube Server or Cloud instance, and reports all the problems
- [sonar-housekeeper](#sonar-housekeeper): Deletes projects, branches, PR  that have not been analyzed since a certain number of days, or
deletes tokens created since more than a certain number of days
- [sonar-loc](#sonar-loc): Computes lines of code per project and in total, as they would be computed by SonarQube (and the licensing system on commercial editions)
- [sonar-measures-export](#sonar-measures-export): Exports measures/metrics of one, several or all projects of the instance in CSV
- [sonar-findings-export](#sonar-findings-export) (Also available as **sonar-issues-export** (deprecated) for backward compatibility): Exports issues and hotspots (potentially filtered) from the instance in CSV
- [sonar-findings-sync](#sonar-findings-sync): Synchronizes issues and hotspots changelog between branches, projects or even SonarQube instances (formerly **sonar-issues-sync**, now deprecated)
- [sonar-projects](#sonar-projects): Exports or imports projects from/to a SonarQube Server instance (EE and higher required for import)
- [sonar-config](#sonar-config): Exports or Imports a SonarQube Server or Cloud platform configuration to/from configuration as code file (JSON file).
- [sonar-rules](#sonar-rules): Exports SonarQube Server or Cloud rules.

:information_source: Although they are likely to work with many versions, the offered tools are **only tested against SonarQube Server LTA (Long Term Active, 2025.1.x as of June 2025), LATEST (2025.3.x as of June 2025), Community Build (25.6.x as of June 2025) and 9.9.9 versions**

:warning: **sonar-tools** 2.7 or higher is required for compatibility with SonarQube Server 10

# What's New - Release notes
- [What's new](https://github.com/okorach/sonar-tools/blob/master/doc/what-is-new.md)
- [Release notes](https://github.com/okorach/sonar-tools/releases)

# Requirements and Installation
- `sonar-tools` requires python 3.8 or higher
- Installation is based on [pip](https://pypi.org/project/pip/).
- Online installation.
  - Run: `python3 -m pip install sonar-tools` (or `python3 -m pip upgrade sonar-tools`)
  If install does not behave as expected you can try the **pip** `--force-reinstall` option (see **pip** documentation)
- Offline installation: If you have no access to the internet on the install machine, you can:
  - Download the `.whl` file from https://pypi.org/project/sonar-tools or attached to the release at https://github.com/okorach/sonar-tools/releases. The file should be something like. **sonar_tools-\<VERSION\>-py3-none-any.whl**
  - Copy the downloaded file on the install machine
  - On the install machine, run `python3 -m pip install sonar_tools-<VERSION>-py3-none-any.whl`
  - Note: The package is dependent upon `argparse`, `datetime`, `python-dateutil`, `requests` and `jprops` python packages that are automatically installed when installing `sonar-tools`
- `sonar-tools` is now also available as a docker image. See [Using sonar-tools in Docker](#docker)

# Docker install
See [Docker section](#docker) at the end of this read me

# Common command line parameters

All tools accept the following common parameters:
- `-h` : Displays a help and exits
- `-u` : URL of the SonarQube Server or Cloud. The default is environment variable `$SONAR_HOST_URL`
or `http://localhost:9000` by default if the environment variable is not set
- `-t` : User token to invoke the Server or Cloud APIs, like `squ_83356c9b2db891d45da2a119a29cdc4d03fe654e`.
The default is environment variable `$SONAR_TOKEN`.
Using login/password is not possible.
The user corresponding to the token must have enough permissions to achieve the tool tasks
- `-o` : Organization, for SonarQube Cloud - Ignored if running against a SonarQube Server
- `-v` : Logging verbosity level (`WARN`, `ÌNFO` or `DEBUG`). The default is `INFO`.
`ERROR` and above is always active.
- `-c` or `--clientCert` : Allows to specify an optional client certificate file (as .pem file)
- `--httpTimeout` : Sets the timeout for HTTP(S) requests to the SonarQube Server or Cloud platform, in seconds
- `--skipVersionCheck` : Starting with **sonar-tools** 2.11, by default all sonar tools occasionnally check on pypi.org if there is a new version of **sonar-tools** available, and output a warning log if that is the case. You can skip this check with this option.
- `-l <logFile>` : Send logs to **<logFile>**, stdout by default
- `--threads <nbThreads>`: Allows to define number of threads for projects auditing (default 1). More threads
  will stress SonarQube APIs more but will be much faster on large platforms with many projects


See common [error exit codes](#exit-codes) at the bottom of this page

# <a name="sonar-audit"></a>sonar-audit

`sonar-audit` allows to audit a SonarQube Server or Cloud instance and output warning logs for all anomalies found.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-audit.md) for details

# <a name="sonar-findings-sync"></a>sonar-findings-sync

`sonar-findings-sync` allows to synchronizes issues and hotspots changelog (false positives, won't fix, issue severity or type change, review status, tags and comments) between branches, projects or SonarQube Server or Cloud instances.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-findings-sync.md) for details

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

:warning: **sonar-tools** 2.7 or higher is required for `sonar-housekeeper` compatibility with SonarQube Server 10

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
sonar-housekeeper -u https://sonar.acme-corp.com -t 15ee09df11fb9b8234b7a1f1ac5fce2e4e93d75d
```

# <a name="sonar-loc"></a>sonar-loc

Exports all projects lines of code as they would be counted by the commercial licences.
See `sonar-loc -h` for details

Basic Usage: `sonar-loc [-f <file>] [--format csv|json] [-a] [-n] [--withTags] [--withURL] [--apps] [--portfolios] [--topLevelOnly]`
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
- `-b`: Export LoCs for each branches of targeted objects (projects or applications)

## Required Permissions

`sonar-loc` needs `Browse` permission on all projects of the Server or Cloud instance

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


## Required Permissions

`sonar-measures-export` needs `Browse` permission on all projects of the SonarQube Server or Cloud instance

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

# <a name="sonar-findings-export"></a>sonar-findings-export
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

`sonar-findings-export` needs `Browse` permission on all projects for which findings are exported

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

# <a name="sonar-projects"></a>sonar-projects (export/import)

Exports (or imports) projects of a given Server instance to / from zip files (This is NOT possible with SonarQube Cloud)

- When exporting, the tool generates a JSON with the list of project keys, the export result (`SUCCESS` or `FAIL`), and:
  - If the export was successful, the generated zip file
  - If the export was failed, the failure reason

- When importing, a JSON file (result of export) must be provided

`sonar-projects` replaces the deprecated `sonar-projects-export` and `sonar-projects-import` commands

Basic Usage:
`sonar-projects -e [--exportTimeout <timeout>] [--skipZeroLoC] -f exported_projects.json`
- `--exportTimeout`: Defines timeout to export a single project in seconds,
                     by default 180 s (large projects can take time to export)
- `--skipZeroLoc`    Skips export of projects with zero lines of code
- `-f`: Defines the file for JSON output (default stdout)

`sonar-projects -i [--importTimeout <timeout>] -f exported_projects.json`
- `--importTimeout`: Defines timeout to import a single project in seconds,
                     by default 180 s (large projects can take time to import)
- `--skipZeroLoc`    Skips import of projects with zero lines of code (if they were exported in the first place)

:information_source: All zip files are generated in the SonarQube Server instance standard location (under `data/governance/project_dumps/export`). On a DCE, the export may be distributed over all the Application Nodes
:warning: **sonar-tools** 2.7 or higher is required for compatibility with SonarQube Server 10

To import, the zip file smust be first copied under (under `data/governance/project_dumps/import`) of the target platform

## Required Permissions

`sonar-projects -e` requires `Administer project` permission on all projects to be exported
`sonar-projects -i` requires `Administer project` and `Project  creation` permission

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e
# Exports all projects, with results of export in CSV file exported_projects.json
sonar-projects -e >exported_projects.json
# Exports 2 projects with keys myProjectKey1 and myOtherProjectKey, with results of export in JSON file exports.json
sonar-projects -e -k myProjectKey1,myOtherProjectKey -f exports.json
# Exports all projects, with results of export in JSON file exported_projects.json
sonar-projects-export -f exported_projects.json

# Import all projects with the JSON information file generated by `sonar-projects-export`
sonar-projects-import -f exported_projects.json
```

# <a name="sonar-config"></a>sonar-config

Exports or imports all or part of a SonarQube Server or Cloud platform configuration.
`sonar-config` is expected to export/import everything that is configurable in a SonarQube Server or Cloud platform, except secrets

Basic Usage: `sonar-config --export -f <file.json>`
- `-f`: Define the output file, if not specified `stdout` is used
- `-e` or `--export`: Specify the export operation
- `-w` or `--what`: Specify what to export (everything by default)
- `-k "<key1>,<key2>,...,<keyn>"`: Will only import/export projects, apps or portfolios with matching keys
- `--fullExport`: Will also export object properties that are not used for an import by may be of interest anyway
See [sonar-config complete doc](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md)

:warning: **sonar-tools** 2.7 or higher is required for compatibility with SonarQube Server 10

## Required Permissions

To export and import configuration, `sonar-config` needs elevated permissions.
See [sonar-config complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md) for details

# <a name="sonar-rules"></a>sonar-rules

Exports rules from a SonarQube Server or Cloud platform configuration.

Basic Usage: `sonar-rules -e -f <file>`
- `-f`: Define the output file, if not specified `stdout` is used
- `-e` or `--export`: Specify the export operation
- `-l` or `--languages`: Export only rules of given languages (comma separated, defined by they Sonar key, not its name)
- `--qualityProfiles`: Export rules defined in a given quality profile. In this case the `--languages` option is mandatory and should specify a single language
- `-h`: Display help with the full list of options

## Required Permissions

`sonar-rules` needs simple browse permissions

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Exports all rules from https://sonar.acme-corp.com, in CSV or in JSON
sonar-rules -f rules.csv
sonar-rules -f rules.json
# Exports rules for languages Java, C# and C++
sonar-rules -l "java, cs, cpp" -f rules.csv
# Exports rules of quality profile "Sonar way" of language Java 
sonar-rules -l java --qualityProfile "Sonar way" >rules.csv
```

# <a name="docker"></a>Using sonar-tools in Docker

Starting from version 3.4 `sonar-tools` is available as a docker image. Here is how to use the docker version:
```
docker pull olivierkorach/sonar-tools:latest
# Run `docker run --rm olivierkorach/sonar-tools` followed by your usual sonar-tools command with its parameters, and example below for sonar-loc
docker run --rm olivierkorach/sonar-tools sonar-loc -u <YOUR_SONAR_URL> -t <YOUR_SONAR_TOKEN> <parameters>

# Alternatively you can pass the Sonar(Qube/Cloud) URL and token as environment variables
docker run --rm -e SONAR_TOKEN=<YOUR_SONAR_TOKEN> -e SONAR_HOST_URL=<YOUR_SONAR_URL> olivierkorach/sonar-tools sonar-loc <parameters>

# Trick if your SonarQube Server is on http://localhost, the URL to pass to docker is http://host.docker.internal, for instance:
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=http://host.docker.internal:9000  olivierkorach/sonar-tools

# The docker image contains all the sonar-tools. Here are other invocation examples
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-measures-export -k <projectKey> -m _all
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-findings-export -h
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-housekeeper -P 90 --mode dry-run --threads 4
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-projects-export
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-config -e --what projects
```

Be aware that by default, files generated in the container are not available from the host. For files generated by sonar-tools you can either use stdout or volumes
```
# The below works, the file config.json is generated on the host
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-config -e > config.json

# The below doesn't work, the file config.json is generated in the container and, by default, not accessible from the host
docker run --rm -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-config -e -f config.json

# If you want the 2nd form above to work you must use volumes, for instance:
docker run --rm -w `pwd` -v `pwd`:`pwd` -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=https://sonar.acme.com olivierkorach/sonar-tools sonar-config -e -f config.json
# After the command the file config.json should be in the local (pwd) directory
```

# <a name="exit-codes"></a>Exit codes

When tools complete successfully they return exit code 0. En case of fatal error the following exit codes may be returned:
- Code 1: Authentication error (Incorrect token provided)
- Code 2: Authorization error (provided token has insufficient permissions)
- Code 3: Other general Sonar API HTTP error
- Code 4: No token provided
- Code 5: Non existing project key provided
- Code 6: Incorrect finding search criteria provided
- Code 7: Unsupported operation requested (because of SonarQube Server edition or configuration)
- Code 8: Audit rule loading failed (at startup)
- Code 9: SIF audit error (file not found, can't open file, not a legit JSON file, ...)
- Code 10: Incorrect command line arguments
- Code 11: Global analysis or project analysis token provided (user token needed for sonar-tools)
- Code 12: HTTP request time-out using the SonarQube API
- Code 13: Some operation attempted to create a Sonar object that already exists
- Code 14: Sonar connection error
- Code 15: Miscellaneous OS errors

# License

Copyright (C) 2019-2025 Olivier Korach
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
