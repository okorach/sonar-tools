# sonar-audit

Command line tool to audit a SonarQube instance and output warning logs whenever a suspicious or incorrect setting/situation is found.
The detail of what is audited is listed at the bottom of this page

## Requirements and Installation

`sonar-audit` is installed through the **sonar-tools** [general installation](../README.md#install)

:warning: **sonar-tools** 2.7 or higher is required for `sonar-audit` compatibility with SonarQube 10

## Common command line parameters

`sonar-audit` accepts all the **sonar-tools** [common parameters](../README.md#common-params)

## Usage

`sonar-audit [-u <url>] [-t <token>] [--what <auditSelection>] [--sif <SIF>] [-f <file>] [--format [json|csv]] [-h] [-v <debugLevel>]`

`--what` can be followed by a list of comma separated items to audit.
When `--what` is not specified, everything is audited

- `--what settings`: Audits global settings and general system data (system info in particular)
- `--what qp`: Audits quality profiles
- `--what qg`: Audits quality gates
- `--what projects`: Audits all projects. This can be a fairly long operation
- `--what users`: Audits users and their tokens
- `--what groups`: Audits groups
- `--what portfolios`: Audits portfolios
- `--what apps`: Audits applications
- `-f <file>`: Sends audit output to `<file>`, `stdout` is the default. The output format is deducted from
  the file extension (JSON or CSV), except if `--format` is specified
- `--sif <SystemInfoFile>`: Will audit the input SIF file, instead of connecting to a SonarQube platform.
  In that case:
  - URL and token are not needed
  - Much less is audited (because SIF does not provide as much information as a live platform)
- `--format [json|csv]`: Generates output in JSON or CSV format (CSV is the default)
- `--csvSeparator <separator>`: Allows to select the separator character for CSV, `,` is the default
- `--threads <nbThreads>`: Allows to define number of threads for projects auditing (default 1). More threads
  will stress SonarQube APIs more but will be much faster on large platforms with many projects
- `-h`: Displays help and exits
- `-u`, `-t`, `-h`, `-v`: See **sonar-tools** [common parameters](../README.md#common-params)

## Required Permissions

To be able to audit everything, the token provided to `sonar-audit` should have the global `Administer System` permission and `Browse`and `Administer` permission on all projects.

## Configuration file

`sonar-audit` can be configured with a configuration file to select what to audit and some different
other audit parameters.
You can create a default config file in the home directory by running `sonar-audit --config`

See [sonar-audit configuration](https://github.com/okorach/sonar-tools/blob/master/doc/audit-settings.md) for the details of parameters

## Example
```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Audits everything, send results to stdout in CSV format
sonar-audit

# Audits everything, send results to fullAudit.json in JSON format
sonar-audit -f fullAudit.json

# Audits global settings, quality profiles and quality gates
sonar-audit --what settings,qg,qp

# Audits SIF, send results to stdout in CSV format
sonar-audit --sif systemInfoFile.json

# Audits projects, send results to projectsAudit.csv in CSV format with ; as separator
sonar-audit --what projects -f projectsAudit.csv --csvSeparator ';'
```

## List of audited stuff

- General checks: (if `audit.globalSettings = yes`, default `yes`)
  - The `admin` user password is the default value `admin`
  - The platform is of version lower than LTA (ex-LTS)
  - The platform is not on most recent LTA (ex-LTS) patch level
  - The instance is not an official distribution
  - The log4shell fix is has not been implemented (either with recent enough SonarQube patch level or the `-Dlog4j2.formatMsgNoLookups=true` option)
  - Commercial edition but not using branch analysis
  - Projects with undetected SCM
  - 3rd party plugins installed and not listed in a whitelist (`audit.plugins.whitelist`)
  - Available disk space is at least 4 x search store size and at least 10 GB
  - DCE: Different plugins are installed on different app nodes
  - DCE: Different version of SonarQube running on different app nodes
  - DCE: Some nodes are not in GREEN status
  - DCE: App Cluster no longer HA (only 1 node up left)
  - DCE: Search cluster no longer HA (only 2 nodes up left)
  - DCE: Search cluster with more than 3 search nodes
  - DCE: Search cluster with even number of nodes (unsafe configuration)
  - DCE: Very unbalanced search nodes index sizes
- General global settings: (if `audit.globalSettings = yes`, default `yes`)
  - `sonar.forceAuthentication` is `false`
  - `sonar.cpd.cross_project` is `true`
  - `sonar.core.serverBaseURL` is not set
  - `sonar.global.exclusions` is not empty
  - Project default visibility is `public`
  - SonarQube uses the built-in H2 database
  - SonarQube uses an external database on same host as SonarQube itself
- Global permissions: (if `audit.globalSettings.permission = yes`, default `yes`)
  - More than 3 users with global `admin`, `admin quality gates`, `admin quality profiles` or `create project` permission
  - More than 10 users with any global permissions (excluding groups)
  - Group `Anyone` has some global permissions
  - Group `sonar-users` has `Admin`, `Admin QG`, `Admin QP` or `Create Projects` permissions
  - More than 2 groups with global `admin`, `admin quality gates`, `admin quality profiles` permissions
  - More than 3 groups with `create project` permission
  - More than 10 groups with any global permissions
- Permission Templates: (if `audit.projects.permissions = yes`, default `yes`)
    - Permissions Templates with no permissions granted
    - More than `audit.projects.permissions.maxUsers` different users with direct permissions (default 5)
    - More than `audit.projects.permissions.maxAdminUsers` users with Project admin permission (default 2)
    - More than `audit.projects.permissions.maxGroups` different groups with permissions on project (default 5)
    - More than `audit.projects.permissions.maxScanGroups` group with execute analysis permission (default 1)
    - More than `audit.projects.permissions.maxIssueAdminGroups` groups with issue admin permission (default 2)
    - More than `audit.projects.permissions.maxHotspotAdminGroups` groups with hotspot admin permission (default 2)
    - More than `audit.projects.permissions.maxAdminGroups` groups with project admin permission (default 2)
    - `sonar-users` group with elevated project permissions
    - `Anyone` group with any project permissions
    - No projectKeyPattern for a template that is not a default
    - Suspicious projectKeyPattern (a pattern that is likely to not select more than 1 key) for instance:
      - `my_favorite_project` (no `.` in pattern)
      - `BUXXXX-*` (Likely confusion between wildcards and regexp)
- DB Cleaner: (if `audit.globalSettings = yes`, default `yes`)
  - Delay to delete inactive short lived branches (7.9) or branches (8.0+) not between 10 and 60 days
  - Delay to delete closed issues not between 10 and 60 days
  - `sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay` is not between 12 and 240 hours (0.5 to 10 days)
  - `sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek` is not between 2 and 12 weeks (0.5 to 3 months)
  - `sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth` is not between 26 and 104 weeks (0.5 year to 2 years)
  - `sonar.dbcleaner.weeksBeforeDeletingAllSnapshots` is not between 104 and 260 weeks (2 to 5 years)
- Maintainability rating grid: (if `audit.globalSettings = yes`, default `yes`)
  - A maintainability rating threshold is not between 3% and 5%
  - B maintainability rating threshold is not between 7% and 10%
  - C maintainability rating threshold is not between 15% and 20%
  - D maintainability rating threshold is not between 40% and 50%
- Environment: (if `audit.globalSettings = yes`, default `yes`)
  - Web process heap (`-Xmx`) is not between 1 GB and 2 GB for CE, DE and EE, between 2 and 4 GB for DCE
  - CE process heap (`-Xmx`) is not between 512 MB per worker and 2 GB per worker
  - More than 4 CE workers
  - CE background tasks failure rate is more than 1%
  - Background tasks are piling up: More than 100 pending CE background tasks or more than 20 or 10 x Nbr workers
  - Search process heap (`-Xmx`) is less than twice the ES index size (small indexes) or less than ES index size + 1 GB (large indexes)
  - Web, CE or ES heap (`-Xmx`) not specified
- Logs: (if `audit.logs = yes`, default `yes`)
  - Errors or Warnings in logs (sonar.log, web.log, ce.log, deprecation.log)
- Quality Gates: (if `audit.qualityGates = yes`, default `yes`)
  - Unused QG
  - QG with 0 conditions or more than 7 conditions
  - QG not using the recommended metrics: `reliability`, `security`, `maintainibility`, `coverage`, `duplication`,
    `security review rating on new code`, `new bugs`, `new vulnerabilities`, `new hotspots`, `new blocker issues`, `new critical issues`, `new major issues`
    and `reliability rating on overall code` and `security rating on overall code`
  - QG thresholds for the above metrics not consistent (non `A` for ratings on new code, non `0` for numeric count of issues,
    coverage not between 20% and 90%, duplication not between 1% and 3%, security and reliability on overall code lower than D)
  - More than 5 quality gates
- Quality Profiles: (if `audit.qualityProfiles = yes`, default `yes`)
  - Non built-in QP not modified in 6 months
  - QP with less than 50% of all the available rules activated
  - QP not used by any projects
  - QP not used since more than 6 months
  - QP using deprecated rules
  - More than 5 QP for a given language
- Projects: (if `audit.projects = yes`, default `yes`)
  - Projects provisioned but never analyzed
  - Projects not analyzed since `audit.projects.maxLastAnalysisAge` days (on any branch) (default 180 days)
  - Project branches not kept permanently and not analyzed since `audit.projects.branches.maxLastAnalysisAge` (default 30 days)
  - Pull requests not analyzed since `audit.projects.pullRequests.maxLastAnalysisAge`(default 30 days)
  - Projects with `public` visibility
  - Permissions: (if `audit.projects.permissions = yes`, default `yes`)
    - More than `audit.projects.permissions.maxUsers` different users with direct permissions (default 5)
    - More than `audit.projects.permissions.maxAdminUsers` users with Project admin permission (default 2)
    - More than `audit.projects.permissions.maxGroups` different groups with permissions on project (default 5)
    - More than `audit.projects.permissions.maxScanGroups` group with execute analysis permission (default 1)
    - More than `audit.projects.permissions.maxIssueAdminGroups` groups with issue admin permission (default 2)
    - More than `audit.projects.permissions.maxHotspotAdminGroups` groups with hotspot admin permission (default 2)
    - More than `audit.projects.permissions.maxAdminGroups` groups with project admin permission (default 2)
    - `sonar-users` group with elevated project permissions
    - `Anyone` group with any project permissions
  - Project bindings (if `audit.projects.bindings = yes`, default `yes`)
    - 2 projects (not part of same monorepo) bound to the same DevOps platform repository
    - Invalid project binding (if `audit.projects.bindings = yes`, default `false`).
      This audit is turned off by default because it takes 1 to 3 seconds to validate a binding which can be too time consuming for platforms with large number of bound projects
  - Suspicious exclusions: (if `audit.projects.exclusions = yes`, default `yes`)
    - Usage of `**/<directory>/**/*`, `**`, `**/*`, `**/*.<extension>` pattern
      (Exceptions: `__pycache__`, `node_modules`, `vendor`, `lib`, `libs` directories)
    - Above patterns and exceptions are configurable
  - Projects with `sonar.scm.disabled` set to `true`
  - Projects with both a `main` and a `master` branch
  - Analysis warnings on all branches analysis
  - Last background task with failed SCM detection
  - Last background task on main branch `FAILED`
  - Last analysis with an obsolete scanner version (by default more than 2 years old)
  - Projects analyzed with apparently a wrong scanner (Can't be certain in all cases)
  - Projects with too many analysis history data points (due to wrong housekeeping settings
    or wrong usage of `sonar.projectVersion`)
  - Projects with too many accepted or false positive issues (Projects > 10K LoC and more than 1 accepted/FP issue
    per 1000 LoC)
- Branches: (if `audit.project.branches = yes`, default `yes`)
  - Branches never analyzed but marked as "keep when inactive"
- Portfolios: (if `audit.applications = yes`, default `yes`)
  - Empty portfolios (with no projects) if `audit.portfolios.empty` is `yes`
  - Portfolios composed of a single project if `audit.portfolios.singleton` is `yes`
  - Last recomputation `FAILED`
  - Portfolios with no permissions
- Applications: (if `audit.applications = yes`, default `yes`)
  - Empty applications (with no projects) if `audit.applications.empty` is `yes`
  - Applications composed of a single project if `audit.applications.singleton` is `yes`
  - Last recomputation `FAILED`
  - Applications with no permissions
- Users: (if `audit.users = yes`, default `yes`)
  - Users that did not login on the platform since `audit.users.maxLoginAge` days (default 180 days)
  - Tokens older than `audit.tokens.maxAge` days (default 90 days)
  - Tokens created but never used after `audit.tokens.maxUnusedAge` days (default 30 days)
  - Tokens not used for `audit.tokens.maxUnusedAge` days (default 30 days)
  - Tokens without expiration date
- Groups: (if `audit.groups = yes`, default `yes`)
  - Empty groups
- WebHooks:
  - Failed webhooks deliveries
</details>

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
