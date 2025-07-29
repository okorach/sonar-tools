# sonar-migration
Command line tool to collect SonarQube data to prepare eventual migration to SonarQube Cloud.

![Downloads](https://img.shields.io/pypi/dm/sonar-migration?color=informational)
![Python-Versions](https://img.shields.io/pypi/pyversions/sonar-migration)
![License](https://img.shields.io/pypi/l/sonar-migration?color=informational)
![Issues](https://img.shields.io/github/issues/okorach/sonar-tools)
![Stars](https://img.shields.io/github/stars/okorach/sonar-tools?style=social)

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=okorach_sonar-tools)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=vulnerabilities)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=bugs)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=okorach_sonar-tools&metric=ncloc)](https://sonarcloud.io/dashboard?id=okorach_sonar-tools)

[What's new](https://github.com/okorach/sonar-tools/blob/master/migration/what-is-new.md)

**DISCLAIMER**: This software is community software.


# Requirements and Installation
- `sonar-migration` requires python 3.8 or higher
- Installation is based on [pip](https://pypi.org/project/pip/).
- Online installation.
  - Run: `python3 -m pip install sonar-migration` (or `python3 -m pip upgrade sonar-migration`)
  If install does not behave as expected you can try the **pip** `--force-reinstall` option (see **pip** documentation)
- `sonar-migration` is also available as a docker image. See [Using sonar-migration in Docker](#docker)


# Common command line parameters

All tools accept the following common parameters:
- `-h` : Displays a help and exits
- `-u` : URL of the SonarQube server. The default is environment variable `$SONAR_HOST_URL`
or `http://localhost:9000` by default if the environment variable is not set
- `-t` : Admin user token to invoke the SonarQube APIs, like `squ_83356c9b2db891d45da2a119a29cdc4d03fe654e`.
The default is environment variable `$SONAR_TOKEN`.
Using login/password is not possible.
The user corresponding to the token must have sufficiently elevated permissions to achieve the tool tasks
- `-f`: Define the output file, if not specified, `migration.<SERVER_ID>.json` is generated
- `-o` : Organization, for SonarQube Cloud - Ignored if running against a SonarQube instance
- `-v` : Logging verbosity level (`WARN`, `ÌNFO` or `DEBUG`). The default is `INFO`.
`ERROR` and above is always active.
- `-c` or `--clientCert` : Allows to specify an optional client certificate file (as .pem file)
- `--httpTimeout` : Sets the timeout for HTTP(S) requests to the SonarQube platform, in seconds
- `--skipIssues` : Skips the "expensive" issue count extract from the migration. This reduces by a factor of 2 to 3 the extract duration and the number of API calls
- `--skipVersionCheck` : `sonar-migration` occasionnally checks on pypi.org if there is a new version of **sonar-migration** available, and output a warning log if that is the case. You can skip this check with this option.
- `-l <logFile>` : Send logs to **<logFile>**, stdout by default

See common [error exit codes](#exit-codes) at the bottom of this page

## Required Permissions

To export data, `sonar-migration` needs elevated permissions

## Examples
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Exports all platform migration data from https://sonar.acme-corp.com in default output file migration.<SERVER_ID>.json
sonar-migration

# Exports all platform migration data from https://sonar.acme-corp.com in file data.json
sonar-migration -f data.json


```

For more about what is exported and imported by `sonar-config` please see the [sonar-config complete documentation](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-config.md)

# <a name="docker"></a>Using sonar-migration in Docker

`sonar-migration` is available as a docker image. Here is how to use the docker version:
```
docker pull olivierkorach/sonar-migration:latest

docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-migration -t $SONAR_TOKEN -u https://sonar.acme.com 
# After the command the file migratiob.<SERVER_ID>.json should be in the local (pwd) directory

# Alternatively you can pass the SonarQube URL and token as environment variables
docker run --rm -w `pwd` -v `pwd`:`pwd` -e SONAR_TOKEN=<YOUR_SONAR_TOKEN> -e SONAR_HOST_URL=<YOUR_SONAR_URL> sonar-migration

# If you run sonar-migration on same machine as SonarQube, to help, the URL fragment http://localhost is automatically transformed in http://host.docker.internal, 
# For instance the 2 commands below have same outcome
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-migration -t $SONAR_TOKEN -u http://host.docker.internal:9000
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-migration -t $SONAR_TOKEN -u http://localhost:9000
```

# <a name="exit-codes"></a>Exit codes

When sonar-migration complete successfully they return exit code 0. En case of fatal error the following exit codes may be returned:
- Code 1: Authentication error (Incorrect token provided)
- Code 2: Authorization error (provided token has insufficient permissions)
- Code 3: Other general Sonar API HTTP error
- Code 4: No token provided
- Code 5: Non existing project key provided
- Code 6: -
- Code 7: Unsupported operation requested (because of SonarQube edition or configuration)
- Code 8: -
- Code 9: -
- Code 10: Incorrect command line arguments
- Code 11: Global analysis or project analysis token provided (user token needed for sonar-tools)
- Code 12: HTTP request time-out using the SonarQube API
- Code 13: -
- Code 14: Sonar connection error
- Code 15: Miscellaneous OS errors


# What's New - Release notes

## Version 0.4

- Robustness: Handle all types of HTTP errors including SSL errors, which were causing freezes
- Added export of flat list of projects in each portfolio
- Fix regression: Export of `platform` section is back
- Added export of portfolios by reference

## Version 0.3

- Robustness: Handle `connectionError` errors in project extract threads
- Added option `--skipIssues` to skip expensive issue count extraction task from the extract (To speed up extract on very large platforms)
- Added export of analysis history of each branch
- Support of incremental dump of projects extracts
- Display of HTTP requests duration in DEBUG logs
- Fixes in documentation
- Trimmed background task data to keep only what is need (to reduce memory and output JSON size)

## Version 0.2

- Added export of:
  - Users email and SCM accounts when available
  - Users last SonarQube and SonarLint login date
  - Per project:
    - Issues coming from instantiated rules (e.g. custom secrets)
    - Hotspots which have been reviewed as SAFE or FIXED
- sonar-migration has its own user agent to be recognized in SonarQube access.log
- Added check whether the running version is the last released
- Fixed crash when accessing a portfolio with not enough permissions
- `sonar-migration` now has its own doc pages (readme and what's new)

## Version 0.1

- First alpha release
- On top of the regular `sonar-config` export of the following is added
  - Global:
    - List of 3rd party plugins installed
  - Per project
    - Last analysis date
    - Ncloc w/ breakdown by language
    - Detected CI
    - Main branch revision
    - Last background task scanner context and warnings
    - Background Task history
    - Issues:
      - Nbr of issue False positive
      - Nbr of issues Won’t fix
      - Nbr of issues Accepted
      - Nbr of issues generated by 3rd party rules (with breakdown per rule)
    - For each branch:
    - Last analysis date
    - Ncloc w/ breakdown by language
    - Issues
      - Nbr of issue False positive
      - Nbr of issues Won’t fix
      - Nbr of issues Accepted
      - Nbr of issues generated by 3rd party rules (with breakdown per rule)

# License

Copyright (C) 2024-2025 Olivier Korach
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
