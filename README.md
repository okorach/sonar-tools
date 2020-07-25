# sonarqube-tools
Additional command line based tools to help in SonarQube administration tasks

All script accept the following common parameters:
- `-h` : Displays a help and exits
- `-u` : URL of the SonarQube server
- `-t` : token of the user to invoke the SonarQube APIs
- `-g` : Debug level (from 1 to 5)
- `-m` : Mode when performing API calls:
  - `batch`: All API calls are performed without any confirmation
  - `confirm`: All API calls that change the SonarQube internal state (POST and DELETE) are asking for a confirmation before execution
  - `dryrun`: All API calls are just output in logging but not actually performed

# issues_export.py

This script exports a list of issues as CSV.
Plenty of issue filters can be specified from the command line, type `issues_export.py -h` for details

## Examples
`issues_export.py -u <url> -t <token> >all_issues.csv`
`issues_export.py -u <url> -t <token> -k <projectKey> >project_issues.csv`

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
`issues_recover.py -u <url> -t <token> -k <projectKey>`

# issues_sync.py

This script tries to sync issues manual changes (FP, WF, Comments, Change of Severity or of issue type) between:
- 2 different branches of a same project
- A same project on 2 different SonarQube platforms

Issue sync means:
- Applying all transitions of the source issue to the target issue
- Applying all manual comments
- Applying all severity or issue type change

## Examples
`issues_sync.py -u <src_url> -t <src_token> -k <projectKey> -U <target_url> -T <target_token>`

## :information_source: Limitations
- The sync is not 100% deterministic. In some rare corner cases (typically less than 5%) it is not possible to determine that an issue is the same between 2 branches or 2 platforms,in which case the issue is not sync'ed. The script will log those cases
- When sync'ing an issue, all changes of the target issue are applied with the user whose token is provided to the script (it cannot be applied with the user of the original issue). Some comments are added to mention who was the original user that made the change
- To be modified (sync'ed from a source issue), the target issue must has zero manual changes ie it must be has created originally by SonarQube

# measures_export.py

This script exports a projects will all (or some selected) measures.
Plenty of issue filters can be specified from the command line, type `measures_export.py -h` for details

## Examples
`measures_export.py -u <url> -t <token> -m ncloc,bugs,vulnerabilities >measures.csv`
`measures_export.py -u <url> -t <token> -m _main >main_measures.csv`
`measures_export.py -u <url> -t <token> -m _all >all_measures.csv`

# projects_export.py

This script exports all projects of a given SonarQube instance.
It sends to the output a CSV with the list of project keys, the export result (`SUCCESS` or `FAIL`), and:
- If the export was successful, the generated zip file
- If the export was failed, the failure reason

:information_source: All zip files are generated in the platform standard location(under `data/governance/project_dumps/export`)

## Examples
`projects_export.py -u <url> -t <token> >exported_projects.csv`

# projects_import.py

This script imports all previously exported projects.
It takes as input a CSV file produced by `export_all_projects.py`

:information_source: All exported zip files must be copied to the right location on the target platform for the import to be successful (In `data/governance/project_dumps/import`)

## Examples
`projects_import.py -u <url> -t <token> -f <export_csv_file>`

# project_history.py
TBD

# project_housekeeper.py
This script deletes all projects whose last analysis date (on any branch) is older than a given number of days.

## :information_source: Limitations
To avoid bad mistakes (mistakenly deleting too many projects), the tools will refuse to delete projects analyzed in the last 90 days.

## :warning: Database backup
**A database backup should always be taken before executing this script. There is no recovery.**

## Example
`project_housekeeper.py -u <url> -t <token> -o <days>`