# sonarqube-tools
Additional command line based tools to help in SonarQube administration tasks

All script accept the following common parameters:
- `-h` : Displays a help and exits
- `-u` : URL of the SonarQube server, for instance `http://localhost:9000`
- `-t` : token of the user to invoke the SonarQube APIs, like `d04d671eaec0272b6c83c056ac363f9b78919b06`
- `-g` : Debug level (from `1` to `5`)
- `-m` : Mode when performing API calls:
  - `batch`: All API calls are performed without any confirmation
  - `confirm`: All API calls that change the SonarQube internal state (POST and DELETE) are asking for a confirmation before execution
  - `dryrun`: All API calls are just output in logging but not actually performed

# issues_export.py

This script exports a list of issues as CSV.
Plenty of issue filters can be specified from the command line, type `issues_export.py -h` for details

## Examples
```
issues_export.py -u <url> -t <token> >all_issues.csv
issues_export.py -u <url> -t <token> -k <projectKey> >project_issues.csv
issues_export.py -u <url> -t <token> -r FALSE-POSITIVE,WONTFIX >fp_wf.csv
issues_export.py -u <url> -t <token> -a 2020-01-01 >issues_created_in_2020.csv
issues_export.py -u <url> -t <token> -types VULNERABILITY,BUG >bugs_and_vulnerabilities.csv
```

# issues_recover.py

This script tries to recover issues that were mistakenly closed following a scan with incorrect parameters

Issue recovery means:
- Reapplying all transitions to the issue to reach its final state before close (Usually *False positive* or *Won't Fix*)
- Reapplying all manual comments
- Reapplying all severity or issue type change

## :information_source: Limitations
- The script has to be run before the closed issue purge period (SonarQube parameter `sonar.dbcleaner.daysBeforeDeletingClosedIssues` whose default value is **30 days**)
- The recovery is not 100% deterministic. In some rare corner cases (typically less than 5%) it is not possible to determine that an issue was closed unexpectedly, in which case the issue is not recovered. The script will log those cases
- When recovering an issue all state change of the issue are applied with the user whose token is provided to the script (it cannot be applied with the original user). Some comments are added to mention who was the original user that made the change

## Examples
```
issues_recover.py -u <url> -t <token> -k <projectKey>
```

# issues_sync.py

This script tries to sync issues manual changes (FP, WF, Comments, Change of Severity or of issue type) between:
- 2 different branches of a same project
- A same project on 2 different SonarQube platforms

Issue sync means:
- Applying all transitions of the source issue to the target issue
- Applying all manual comments
- Applying all severity or issue type change

## Examples
```
issues_sync.py -u <src_url> -t <src_token> -k <projectKey> -U <target_url> -T <target_token>
```

## :information_source: Limitations
- The sync is not 100% deterministic. In some rare corner cases (typically less than 5%) it is not possible to determine that an issue is the same between 2 branches or 2 platforms,in which case the issue is not sync'ed. The script will log those cases
- When sync'ing an issue, all changes of the target issue are applied with the user whose token is provided to the script (it cannot be applied with the user of the original issue). Some comments are added to mention who was the original user that made the change
- To be modified (sync'ed from a source issue), the target issue must has zero manual changes ie it must be has created originally by SonarQube

# measures_export.py

This script exports a projects will all (or some selected) measures.
Plenty of issue filters can be specified from the command line, type `measures_export.py -h` for details

## Examples
```
measures_export.py -u <url> -t <token> -m ncloc,bugs,vulnerabilities >measures.csv
measures_export.py -u <url> -t <token> -m _main >main_measures.csv
measures_export.py -u <url> -t <token> -m _all >all_measures.csv
```
# projects_export.py

This script exports all projects of a given SonarQube instance.
It sends to the output a CSV with the list of project keys, the export result (`SUCCESS` or `FAIL`), and:
- If the export was successful, the generated zip file
- If the export was failed, the failure reason

:information_source: All zip files are generated in the platform standard location(under `data/governance/project_dumps/export`)

## Examples
```
projects_export.py -u <url> -t <token> >exported_projects.csv
```

# projects_import.py

This script imports all previously exported projects.
It takes as input a CSV file produced by `export_all_projects.py`

:information_source: All exported zip files must be copied to the right location on the target platform for the import to be successful (In `data/governance/project_dumps/import`)

## Examples
```
projects_import.py -u <url> -t <token> -f <export_csv_file>
```

# project_history.py
TBD

# project_housekeeper.py
This script deletes all projects whose last analysis date (on any branch) is older than a given number of days.

## :information_source: Limitations
To avoid bad mistakes (mistakenly deleting too many projects), the tools will refuse to delete projects analyzed in the last 90 days.

## :warning: Database backup
**A database backup should always be taken before executing this script. There is no recovery.**

## Example
```
project_housekeeper.py -u <url> -t <token> -o <days>
```

# sonar_audit.py
Audits the SonarQube platform and output warning logs whenever a suspicious or incorrect setting/situation is found.
What is audited:
- General global settings:
  - sonar.forceAuthentication is true
  - sonar.cpd.cross_project is false
  - sonar.core.serverBaseURL is set
  - sonar.global.exclusions is empty
  - Project default visbility is Private
- Global permissions:
  - TODO
- DB Cleaner:
  - Delay to delete inactive SLB (7.9) or branches (8.x) between 10 and 60 days
  - Delay to delete closed issues between 10 and 60 days
  - sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay between 12 and 240 hours (0.5 to 10 days)
  - sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek between 2 and 12 weeks (0.5 to 3 months)
  - sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth between 26 and 104 weeks (0.5 year to 2 years)
  - sonar.dbcleaner.weeksBeforeDeletingAllSnapshots between 104 and 260 weeks (2 to 5 years)
- Maintainability rating grid:
  - A maintainability rating threshold between 3% and 5%
  - B maintainability rating threshold between 7% and 10%
  - C maintainability rating threshold between 15% and 20%
  - D maintainability rating threshold between 40% and 50%
- Environment
  - Web heap (-Xmx) between 1 GB and 2 GB
  - CE heap (-Xmx) between 512 MB per worker and 2 GB per worker
  - Maximum CE 4 workers
  - CE background tasks failure rate of more than 1%
  - Excessive nbr of background tasks: More than 100 pending CE background tasks or more than 20 or 10 x Nbr workers
  - ES heap (-Xmx) is less than half the ES index (small indexes) or less than ES index + 1 GB (large indexes)
- Quality Gates:
  - Unused QG
  - QG with 0 conditions or more than 7 conditions
  - QG not using the recommended metrics: reliability, security, maintainibility, coverage, duplication,
    security review rating on new code, new bugs, new vulnerabilities, new hotspots, new blocker, new critical, new major
    and reliability rating and security rating on overall code
  - Thresholds for the above metrics not consistent (non A for ratings on new code, non 0 for numeric count of issues,
    coverage not between 20% and 90%, duplication not between 1% and 3%, secuirty and relibility on overall code lower than D)
  - More than 5 quality gates
- Quality Profiles:
  - QP not modified in 6 months
  - QP with less than 50% of all the available rules activated
  - QP not used by any projects
  - QP not used since more than 6 months
  - QP using deprecated rules
- Projects:
  - Projects provisioned but never analyzed
  - Projects not analyzed since 6 months (on any branch)
  - Projects with Public visbility
  - Large projects with too much XML: Projects with more than 200K LoC and XML representing more than 50% of it
  - Permissions:
    - More than 5 different users with direct permissions (use groups)
    - More than 3 users with Project admin permission
    - More than 5 different groups with permissions on project
    - More than 1 group with execute analysis permission
    - More than 2 groups with issue admin permission
    - More than 2 groups with hotspot admin permission
    - More than 2 groups with project admin permission
