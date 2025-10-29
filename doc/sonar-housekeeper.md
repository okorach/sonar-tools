# sonar-housekeeper

Deletes obsolete/outdated data from SonarQube:
- Projects whose last analysis date (on any branch) is older than a given number of days.
- User tokens older than a given number of days
- Inactive branches (Branches not analyzed for a given number of days), excepted branches marked as "keep when inactive"
  There is a possibility to override the "keep when inactive" regexp if the original SonarQube one was wrong and caused many branches to be kepf
- Inactive pull requests (PRs not analyzed for a given number of days)

Usage: `sonar-housekeeper [-P <days>] [-B <days>] [-R <days>] [-T <days>] [--keepWhenInactive <regexp] [--mode delete]`

- `-P <days>`: Will search for projects not analyzed since more than `<days>` days.
To avoid deleting too recent projects it is denied to specify less than 90 days
- `-B <days>`: Will search for projects branches not analyzed since more than `<days>` days.
Branches marked as "keep when inactive" are excluded from housekeeping
- `-R <days>`: Will search for pull requests not analyzed since more than `<days>` days
- `-T <days>`: Will search for tokens created since more than `<days>` days
- `--keepWhenInactive <regexp>`: Overrides the SonarQube `sonar.dbcleaner.branchesToKeepWhenInactive` to with another regexp to consider branches to delete
- `--mode delete`: If not specified, `sonar-housekeeper` will only perform a dry run and list projects
branches, pull requests and tokens that would be deleted.
If `--mode delete` is specified objects are actually deleted
- `-h`, `-u`, `-t`, `-o`, `-v`, `-l`, `--httpTimeout`, `--threads`, `--clientCert`: See **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

## Examples

```
export SONAR_HOST_URL=https://sonar.acme-corp.com
export SONAR_TOKEN=squ_XXXXXXYYYYYZZZAAAABBBBCCCDDDEEEFFFGGGGGG

# Deletes all branches that have not been analyzed for 90 days and where the branch name does not match '(main|master|release|develop).*'
sonar-housekeeper -B 90 --keepWhenInactive '(main|master|release|develop).*' --mode delete

# Lists projects that have not been analyzed on any branch or PR in the last 365 days, on SonarQube Cloud
sonar-housekeeper -P 365 -u https://sonarcloud.io -t <token> -o <organization>

# Deletes projects that have not been analyzed on any branch or PR in the last 365 days
sonar-housekeeper -P 365 --mode delete

# Deletes tokens created more than 365 days ago
sonar-housekeeper -T 365 --mode delete
```

## Required Permissions

To be able to delete anything, the token provided to `sonar-housekeeper` should have:
- The global `Administer System` permission to delete tokens
- Plus `Browse` and `Administer` permission on all projects to delete (or with branches or PR to delete)

## Requirements and Installation

`sonar-housekeeper` is installed through the **sonar-tools** [general installation](https://github.com/okorach/sonar-tools/blob/master/README.md#install)

## Common command line parameters

`sonar-housekeeper` accepts all the **sonar-tools** [common parameters](https://github.com/okorach/sonar-tools/blob/master/README.md)

### :information_source: Limitations
To avoid bad mistakes (mistakenly deleting too many projects), the tools will refuse to delete projects analyzed in the last 90 days.

### :warning: Database backup
**A database backup should always be taken before executing this script. There is no recovery.**
