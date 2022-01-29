# <a name="sonar-issues-sync"></a>sonar-issues-sync

`sonar-issues-sync` synchronizes issues changelog between branches, projects within a same SonarQube instance or
across different SonarQube instances

## Requirements and Installation

`sonar-issues-sync` is installed through the **sonar-tools** [general installation](README.md#install)

## Common command line parameters

`sonar-issues-sync` accepts all the **sonar-tools** [common parameters](README.md#common-params)

## Usage

`sonar-issues-sync --login <user> -k <projectKey> [-b <sourceBranch>] [-B <targetBranch>] [-K <targetProjectKey>] [-B <targetBranch>] [-U <targetUrl> [-T <targetToken>] [-f <file>] [--nolink] [--nocomment] [-h] [-u <sqUrl>] [-t <token>] [-v <debugLevel>]`

- `--login`: Login of the dedicated (technical service) user dedicated to the issue synchronization. Using a dedicated user allow to detect past synchronization when issue sync is performed repeatedly.
- `-k <projectKey>`: Key of the source project
- `-K <projectKey>`: Optional. Key of the target project. Assumed to the the same as source project key if not specified
- `-b <sourceBranch>`: Optional. Name of the source branch. Only required when doing synchronization between 2 branches of a same project of a same instance
- `-B <targetBranch>`: Optional. Name of the target branch. Only required when doing synchronization between 2 branches of a same project of a same instance
- `-U <targetUrl>`: Optional. URL of the target SonarQube instance, when synchronizing between 2 different instances
- `-T <targetToken>`: Optional. Token if the synchronization service account on the target SonarQube instance, when sync'ing between 2 instances
- `-f <file>`: Sends a summary report of synchronization to `<file>`, `stdout` is the default. The output format is JSON
- `-u`, `-t`, `-h`, `-v`: See **sonar-tools** [common parameters](README.md#common-params)

:warning: Note about `--login` and `-t` and `-T`: It is strongly recommended to run `sonar-issues-sync` with the credentials of a specific service account dedicated to issues synchronization. This will allow to recognize automatic synchronization changes by the author of those changes. So `--login` must correspond to the same user as the token used in the target SonarQube instance (the one that will be written). This token is either the one provided with `-t`when the synchronization is within a same SonarQube instance (for instance 2 branches of a same project), or `-T` when synchronizing between 2 different SonarQube instances (the `--login <user>` and the `-T <token>` corresponding to a user on the **target** SonarQube instance in that case)


## Example

:warning: The `sonar-issue-sync` tool MUST be run with a specific service account (to be named on the command line) so that `sonar-issue-sync` can recognize past synchronizations and complement them if some updates happened on an issue that has already been synchronized before with the same service account.
`sonar-issues-sync --login <serviceAccount> -t <tokenOfThatServiceAccount> ...` when syncing within a same instance
`sonar-issues-sync --login <targetInstanceServiceAccount> -T <tokenOfThatServiceAccount> ...` when syncing between 2 instances

Synchronizes issues changelog between:
- All branches of a same project:
  `sonar-issue-sync --login issue-syncer -u https://sonar.acme.com -t abcdefghij -k <projectKey>`
- 2 different branches of a same project
   (URL is read from `$SONAR_HOST_URL` and `http://localhost:9000` otherwise, token is read from `$SONAR_TOKEN`)
  `sonar-issue-sync --login issue-syncer -k <projectKey> -b <sourceBranch> -B <targetBranch>`
- All branches with same name between 2 different projects of a same SonarQube instance:
  `sonar-issue-sync --login issue-syncer -k <sourceProjectKey> -K <targetProject>`
- 2 branches of 2 different projects of a same SonarQube instance:
  `sonar-issue-sync --login issue-syncer -k <sourceProjectKey> -b <sourceBranch> -K <targetProject> -B <targetBranch>`
- All branches with same name between 2 projects from different SonarQube instances:
  `sonar-issue-sync --login issue-syncer -k <sourceProjectKey> -u <sourceUrl> -t <sourceToken> -K <targetProjectKey> -U <targetUrl> -T <targetToken>`
  There is no requirements on the 2 SonarQube instances: They do not need to be of same edition, version or have the same list of plugins

Issues changelog synchronization includes:
- Change of issue type
- Change of issue severity
- Issue marked as Won't fix or False positive
- Issue re-opened
- Issue assignments
- Custom tags added to the issue

## Limitations

`sonar-issues-sync` has a couple of limitations:
- Issue comments are not (yet) synchronized
- The source and target issues are synchronized only:
  - When there is a 100% certainty that the issues are the same. In some rare corner cases it can be impossible to be certain that 2 issues are the same.
  - When the target issue currently has no changelog (except from the synchronization service account). If a issue
  has been manually modified both on the source and target issue, the synchronization can't happen anymore

When an issue could not be synchronized for one of the above reasons, this is reported in the `sonar-issues-sync` report.
Whenever a close enough issue was found it is provided in the report to complete synchronization manually if desired.

## Configurable behaviors

When an issue is synchronized, a special comment is added on the target issue with a link to the source one, for cross checking purposes. This comment can be disabled by using the `--nolink` option

On all changes of an issue that is synchronized, a special comment is added on the target issue the original login of the user that made the change, for information. Indeed, all issues automatically synchronized will be reported as modified by the same service account. It's possible to disable these comments by using the `--nocomment` option

## Output report

The tool sends to standard output a JSON file with, for each issue on the target branch or project:
- If the issue was synchonized
- If synchronized, the reference of the source and target issue
- If not synchronized, the reason for that. The reasons can be:
  - No match was found for the source issue on the target (target project or target branch)
  - A match was found but the target issue already has a manual changelog
  - Multiple matches were found. The list of all matches are given in the JSON
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
