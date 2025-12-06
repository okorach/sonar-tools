# sonar-tools
Command line tools to help in SonarQube administration tasks. Available as a **pypi.org** package or a **docker** image.

`sonar-tools` is compatible with:
- SonarQube Server versions 9.9.x, January LTA (2025.1.x), July LTA (2025.4.x), latest 2025.x (2025.5 as of Oct 2025). It may work with older 9.x versions or intermediate 10.x versions but this is not guaranteed.
- The **latest** SonarQube Community Build (25.10 as of Oct 2025).


![Downloads](https://img.shields.io/pypi/dm/sonar-tools?color=informational)
![Python-Versions](https://img.shields.io/pypi/pyversions/sonar-tools)
![License](https://img.shields.io/pypi/l/sonar-tools?color=informational)
![Issues](https://img.shields.io/github/issues/okorach/sonar-tools)
![Stars](https://img.shields.io/github/stars/okorach/sonar-tools?style=social)

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=okorach_sonar-tools)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=vulnerabilities)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=bugs)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=ncloc)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)

**DISCLAIMER**: This software is community software. None of the tools it contains are neither supported nor endorsed by SonarSource Sarl, the company publishing the [SonarQube Server](https://www.sonarsource.com/products/sonarqube/), [SonarQube Cloud](https://sonarcloud.io) and [SonarQube for IDE (ex- SonarLint)](https://www.sonarsource.com/products/sonarlint/) products

The following utilities are available:
- [sonar-audit](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-audit.md): Audits a SonarQube Server or Cloud instance, and reports all the problems
- [sonar-housekeeper](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-housekeeper.md): Deletes projects, branches, PR  that have not been analyzed since a certain number of days, or
deletes tokens created since more than a certain number of days
- [sonar-loc](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-loc.md): Computes lines of code per project and in total, as they would be computed by SonarQube (and the licensing system on commercial editions)
- [sonar-measures-export](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-measures-export.md): Exports measures/metrics of one, several or all projects of the instance in CSV
- [sonar-findings-export](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-findings-export.md) (Also available as **sonar-issues-export** (deprecated) for backward compatibility): Exports issues and hotspots (potentially filtered) from the instance in CSV
- [sonar-findings-sync](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-findings-sync.md): Synchronizes issues and hotspots changelog between branches, projects or even SonarQube instances (formerly **sonar-issues-sync**, now deprecated)
- [sonar-projects](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-projects.md): Exports or imports projects from/to a SonarQube Server instance (EE and higher required for import)
- [sonar-config](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md): Exports or Imports a SonarQube Server or Cloud platform configuration to/from configuration as code file (JSON file).
- [sonar-rules](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-rules.md): Exports SonarQube Server or Cloud rules.

:information_source: Although they are likely to work with many versions, the offered tools are **only tested against SonarQube Server Jan LTA (Long Term Active, 2025.1.x as of Oct 2025), July LTA (2025.4.x as of Oct 2025), LATEST (2025.5.x as of Oct 2025), Community Build (25.9.x as of Oct 2025) and 9.9.9 versions, and SonarQube Clou**

:warning: **sonar-tools** 2.7 or higher is required for compatibility with SonarQube Cloud or SonarQube Server 10 and higher

# What's New - Release notes
- [What's new](https://github.com/okorach/sonar-tools/blob/master/doc/what-is-new.md)
- [Release notes](https://github.com/okorach/sonar-tools/releases)

# Requirements and Installation
- `sonar-tools` requires python 3.9 or higher
- Installation is based on [pip](https://pypi.org/project/pip/).

## Online installation.
  - Run: `python3 -m pip install sonar-tools` (or `python3 -m pip upgrade sonar-tools`)
  If install does not behave as expected you can try the **pip** `--force-reinstall` option (see **pip** documentation)

## Offline installation: If you have no access to the internet on the install machine, you can:
  - Download the `.whl` file from https://pypi.org/project/sonar-tools or attached to the release at https://github.com/okorach/sonar-tools/releases. The file should be something like. **sonar_tools-\<VERSION\>-py3-none-any.whl**
  - Copy the downloaded file on the install machine
  - On the install machine, run `python3 -m pip install sonar_tools-<VERSION>-py3-none-any.whl`
  - Note: The package is dependent upon `argparse`, `datetime`, `python-dateutil`, `requests` and `jprops` python packages that are automatically installed when installing `sonar-tools`

## Docker installation

  - `sonar-tools` is now also available as a docker image.
  - Run: `docker pull olivierkorach/sonar-tools:latest` to install

 Then see [Using sonar-tools in Docker](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-loc.md) for details

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

# sonar-audit

`sonar-audit` allows to audit a SonarQube Server or Cloud instance and output warning logs for all anomalies found.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-audit.md) for details

# sonar-findings-sync

`sonar-findings-sync` allows to synchronizes issues and hotspots changelog (false positives, won't fix, issue severity or type change, review status, tags and comments) between branches, projects or SonarQube Server or Cloud instances.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-findings-sync.md) for details

# sonar-housekeeper

Deletes obsolete/outdated data from SonarQube
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-housekeeper.md) for details

# sonar-loc

Exports all projects lines of code as they would be counted by the commercial licences.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-loc.md) for details

# sonar-measures-export

Exports one or all projects with all (or some selected) measures in a CSV or JSON file.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-measures-export.md) for details

# sonar-findings-export
(Also available as `sonar-issues-export` for backward compatibility, but **deprecated**)

Exports a list of issues as CSV, JSON or SARIF format. The export is sent to standard output or into a file
Plenty of issue filters can be specified from the command line, type `sonar-findings-export -h` for details.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-findings-export.md) for details

# sonar-projects (export/import)

Exports (or imports) projects of a given Server instance to / from zip files (This is NOT possible with SonarQube Cloud)
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-projects.md) for details

# sonar-config

Exports or imports all or part of a SonarQube Server or Cloud platform configuration.
See [complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md) for details

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
- Code 16: Object not found during a search
- Code 17: Sonar Server internal error

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
