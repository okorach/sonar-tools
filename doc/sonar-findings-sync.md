# <a name="sonar-findings-sync"></a>sonar-findings-sync
Note: Replaces `sonar-issues-sync`, which deprecated

`sonar-findings-sync` synchronizes issues and hotspots changelog between branches, projects within a same SonarQube instance or across different SonarQube instances

## Requirements and Installation

`sonar-findings-sync` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-findings-sync` accepts all the **sonar-tools** [common parameters](../README.md#common-params)

## Usage

`sonar-findings-sync --login <user> -k <projectKey> [-b <sourceBranch>] [-B <targetBranch>] [-K <targetProjectKey>] [-B <targetBranch>] [-U <targetUrl> [-T <targetToken>] [-f <file>] [--nolink] [--nocomment] [--since <YYYY-MM-DD>] [-h] [-u <sqUrl>] [-t <token>] [-v <debugLevel>]`

- `--login`: **DEPRECATED**. Login of the dedicated technical account used for syncing. This parameter is now automatically deducted from the target token. Using a dedicated account for sync'ing is recommended to detect previous synchronization when issue sync is performed repeatedly.
- `-k <projectKey>`: Key of the source project.
- `-K <projectKey>`: Optional. Key of the target project. If not specified, the same project key as the source is assumed
- `-b <sourceBranch>`: Optional. Name of the source branch. Only required when doing synchronization between 2 branches of a same project of a same instance.
- `-o <sourceOrganization>`: Optional. If source project is on SonarCloud.
- `-B <targetBranch>`: Optional. Name of the target branch. Only required when doing synchronization between 2 branches of a same project of a same instance.
- `-U <targetUrl>`: Optional. URL of the target SonarQube instance or SonarCloud, when synchronizing between 2 different instances. If not specified, the same URL as the source is assumed.
- `-T <targetToken>`: Optional. Token if the synchronization service account on the target SonarQube instance, when sync'ing between 2 instances. If not specified, the same token as the source is assumed.
- `-O <targetOrganization>`: Optional. If target project is on SonarCloud, and if organization is different than the source project or if the source project is not on SonarCloud. If not specified, the same organization as the source is assumed.
- `--since <YYYY-MM-DD>`: Only sync issues modified since a give date in the source project/branch. This generally allows to significantly reduce the number of issues involved in the sync, and therefore to significantly accelerate the sync process
- `-f <file>`: Sends a summary report of synchronization to `<file>`, `stdout` is the default. The output format is JSON
the target token.
- `-u`, `-t`, `-h`, `-v`: See **sonar-tools** [common parameters](../README.md#common-params)

:warning: Note about `--login` and `-t` and `-T`: It is **strongly recommended** to run `sonar-findings-sync` with the credentials of a specific service account dedicated to issues synchronization. This will allow to recognize automatic synchronization changes by the author of those changes. This token is either the one provided with `-t`when the synchronization is within a same SonarQube instance/SonarCloud (for instance 2 branches of a same project), or `-T` when synchronizing between 2 different SonarQube instances (The `-T <token>` corresponding to a user on the **target** SonarQube instance in that case)

## Required Permissions

To be able to perform the sync, the token provided to `sonar-findings-sync` should have:
- `Browse` permission on the source project
- `Browse` and `Administer Issues` permission on the target project. When hotspots will also be synchronized,
  `Administer Hotspots` permission will also be needed

## Example

:warning: The `sonar-issue-sync` tool MUST be run with a specific service account (to be named on the command line) so that `sonar-issue-sync` can recognize past synchronizations and complement them if some updates happened on an issue that has already been synchronized before with the same service account.
`sonar-findings-sync --login <serviceAccount> -t <tokenOfThatServiceAccount> ...` when syncing within a same instance
`sonar-findings-sync --login <targetInstanceServiceAccount> -T <tokenOfThatServiceAccount> ...` when syncing between 2 instances

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
- **main** branch of a source project key **myProject** in a SonarQube instance and **master** branch of the same project in SonarCloud:
  `sonar-issue-sync --login myuser@github -k myProject -u https://sonar.acme.com -t <sourceToken> -K myProject -U https://sonarcloud.io -T <targetToken> -O myOrganization`


Issues changelog synchronization includes:
- Change of issue type
- Change of issue severity
- Issue marked as Won't fix or False positive
- Issue re-opened
- Issue assignments
- Custom tags added to the issue

## Limitations

`sonar-findings-sync` has a couple of limitations:
- Security Hotspots are not (yet) synchronized
- The source and target issues are synchronized only:
  - When there is a 100% certainty that the issues are the same. In some rare corner cases it can be impossible to be certain that 2 issues are the same.
  - When the target issue has currently no changelog (except from the synchronization service account changes). If a issue
  has been manually modified by another user on the target issue, the synchronization can't happen anymore

When an issue could not be synchronized because of one of the above reasons, this is reported in the `sonar-findings-sync` report.
Whenever a close enough issue was found but not sync'ed (because not 100% certain to be identical), the close issue is provided in the report to complete synchronization manually if desired.

## Required Permissions

`sonar-findings-sync` needs the global `Create Projects` permission

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
export SONAR_TOKEN=squ_83356c9b2db891d45da2a119a29cdc4d03fe654e

# Syncs issues from branch develop to branch master of project myProjKey
sonar-findings-sync -k myProjKey -b develop -B master >sync_2_branches.json

# Syncs issues from projectKey1 main branch to projectKey2 main branch
sonar-findings-sync -k projectKey1 -K projectKey2 >sync_2_projects.json

# Syncs issues from projectKey1 main branch to projectKey2 main branch
sonar-findings-sync -k myPorjectKey -U https://anothersonar.acme-corp.com -t d04d671eaec0272b6c83c056ac363f9b78919b06 -K otherInstanceProjKey >sync_2_instances.json
```

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
