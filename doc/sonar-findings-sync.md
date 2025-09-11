# <a name="sonar-findings-sync"></a>sonar-findings-sync
Note: Replaces `sonar-issues-sync`, which deprecated

`sonar-findings-sync` synchronizes issues and hotspots changelog between branches, projects within a same SonarQube instance or across different SonarQube instances (Server or Cloud).
Sync works both with Commercial Editions (Developer, Enterprise, Data Center) and Community Edition/Community Build.
When the source or target is a Community Edition/Build then only the main branch is synchronized.

## Requirements and Installation

`sonar-findings-sync` is installed through the **sonar-tools** [general installation](../README.md#install)

## Common command line parameters

`sonar-findings-sync` accepts all the **sonar-tools** [common parameters](../README.md#common-params)

## Usage

`sonar-findings-sync -k <projectKeyPattern> [-b <sourceBranch>] [-B <targetBranch>] [-K <targetProjectKey>] [-B <targetBranch>] [-U <targetUrl> [-T <targetToken>] [-f <file>] [--nolink] [--since <YYYY-MM-DD>] [-h] [-u <sqUrl>] [-t <token>] [-v <debugLevel>]`

- `-k <projectKeyPattern>`: Project key regexp pattern of the source projects to sync. If the pattern selects more than 1 project then the `-K` option shall not be speciified and the sync happens 1-to-1 for all project keys matching the pattern in the source platform. A same project key must exist on the target.
- `-K <projectKey>`: Optional. Key of the target project. If not specified, the same project key as the source is assumed
- `-b <sourceBranch>`: Optional. Name of the source branch. Only required when doing synchronization between 2 branches of a same project of a same instance.
- `-o <sourceOrganization>`: Optional. If source is SonarQube Cloud.
- `-B <targetBranch>`: Optional. Name of the target branch. Only required when doing synchronization between 2 branches of a same project of a same instance.
- `-U <targetUrl>`: Optional. URL of the target SonarQube Server or SonarQube Cloud, when synchronizing between 2 different instances. If not specified, the same URL as the source is assumed.
- `-T <targetToken>`: Optional. Token if the synchronization service account on the target SonarQube Server or Cloud, when sync'ing between 2 instances. If not specified, the same token as the source is assumed.
- `-O <targetOrganization>`: Optional. If target project is on SonarQube Cloud, and if organization is different than the source project or if the source project is not on SonarQube Cloud. If not specified, the same organization as the source is assumed.
- `--since <YYYY-MM-DD>`: Only sync issues modified since a give date in the source project/branch. This generally allows to significantly reduce the number of issues involved in the sync, and therefore to significantly accelerate the sync process
- `-f <file>`: Sends a summary report of synchronization to `<file>`, `stdout` is the default. The output format is JSON
the target token.
- `--nolink`: Do not add a HTTP link comment in the source and target findings (that point at each other)
- `-u`, `-t`, `-h`, `-v`: See **sonar-tools** [common parameters](../README.md#common-params)

:warning: Note about `-t` and `-T`: It is **strongly recommended** to run `sonar-findings-sync` with the credentials of a specific service account dedicated to issues synchronization on the target. This will allow to recognize automatic synchronization changes by the author of those changes. This token is either the one provided with `-t` when the synchronization is within the same SonarQube Server or Cloud (for instance 2 branches of a same project), or `-T` when synchronizing between 2 different SonarQube Server or Cloud instances (The `-T <token>` corresponding to a user on the **target** SonarQube Server or Cloud in that case)

## Required Permissions

To be able to perform the sync, the token provided to `sonar-findings-sync` should have:
- `Browse` permission on the source project
- `Browse` and `Administer Issues` permission on the target project. When hotspots will also be synchronized,
  `Administer Hotspots` permission will also be needed

## Example

:warning: The `sonar-findings-sync` tool MUST be run with a specific service account (to be named on the command line) so that `sonar-findings-sync` can recognize past synchronizations and complement them if some updates happened on an issue that has already been synchronized before with the same service account.
`sonar-findings-sync -t <tokenOfServiceAccount> ...` when syncing within a same instance
`sonar-findings-sync -T <tokenOfServiceAccount> ...` when syncing between 2 instances

Example of synchronization options
(There qre no requirements on the 2 SonarQube Server or Cloud instances: They do not need to be of same edition, version or have the same list of plugins)
- Synchronize all branches of a same project with key `myproject`:
  `sonar-findings-sync -u https://sonar.acme.com -t squ_xxxx -k myproject`
- Synchronize branch `develop` into branch `main` of project `myproject`
   (URL is read from `$SONAR_HOST_URL` and `http://localhost:9000` otherwise, token is read from `$SONAR_TOKEN`)
  `sonar-findings-sync -k myproject -b develop -B main`
- Synchronize 2 branches of 2 different projects of a same SonarQube Server or Cloud instance:
  `sonar-findings-sync -k <sourceProjectKey> -b <sourceBranch> -K <targetProject> -B <targetBranch>`
- All branches with same name between 2 projects from different SonarQube Server or Cloud instances:
  `sonar-findings-sync -k <sourceProjectKey> -u <sourceUrl> -t <sourceToken> -K <targetProjectKey> -U <targetUrl> -T <targetToken>`
- Synchronize all branches with same name between 2 different projects of a same SonarQube Server or Cloud instance:
  `sonar-findings-sync -k <sourceProjectKey> -K <targetProject>`
- Synchronize all projects whose keys are matching regexp `demo:.*` from a different source and target platform:
  (Be conscious that if there are many projects selected by the regexp pattern, the synchronization may time quite some time)
  `sonar-findings-sync -u https://sonar1.acme.com -t squ_xxxx -U https://sonar2.acme.com -T squ_xxxx -k "demo:.*"`
- **main** branch of a source project key **myProject** in a SonarQube Server instance and **master** branch of the same project in SonarQube Cloud:
  `sonar-findings-sync -k myProject -u https://sonar.acme.com -t <sourceToken> -K myProject -U https://sonarcloud.io -T <targetToken> -O myOrganization`


# Selection of source findings for synchronization

## Source findings

In order to not uselessly consider to many issues for synchronization, the sync algorithm only selects, in the source project or branch, findings that:
- Have comments or
- Have a changelog 
  - Change of issue type, severity, marked as false positive, accepted or won't fix, confirmed or fixed, re-opened for issues
  - Change of status (Acknowledged, Safe or Fixed or back to To Review) for Hotspots

Findings that were only (re-)assigned or that were only added tags are not synchronized. (tagged issues may be synchronized in the future)

## Target findings

In the target, the synchronization algorithm with only select findings to sync if:
- They have not changelog or
- All changes and comments were performed with the account that is used for the sync (it is strongly recommended to use a specific service account with `sonar-findings-sync`)

Once the set of source and target findings is determined, the sync matching algorithm is applied, between the source and target set.
Note that there is a separate source and target set for issues and hotspots, because it cannot be that an issue matches a hotspot and vice versa.


## Matching algorithm

Matching algorithm to synchronize findings:
- Findings are considered a clean match when they have: Same rule, hash, message and file
  If there are several clean target match for a given source, the target whose line number is the closest to the source is considered the best match
- If there is a clean match, the findings are synchronized
- If there is no clean match, approximate matches are searched
- Findings are considered approximate match if they get a score of 8/9 on the below criteria:
  - Same message: 2 points, Different but very similar message (levenshtein distance) 1 poimnt
  - Same file: 1 point
  - Same line: 1 point
  - Same component: 1 point
  - Same author: 1 point
  - Same type: 1 point
  - Same severity: 1 point
  - Same hash: 1 point
- If there is more than 1 approximate match, the findings are not synchronized and the mutliple matches are reported in the issue sync report
- If there is a single approximate match, then the findings are synchronized

When an issue could not be synchronized because of one of the above reasons, this is reported in the `sonar-findings-sync` report.
Whenever a close enough issue was found but not sync'ed (because not 100% certain to be identical), the close issue is provided in the report to complete synchronization manually if desired.

# What is synchronized

When 2 findings match, depending on the source and target platform all or only some elemengts of the source finding will be synchronized:

Findings synchronization includes:
**Issues**
- Change of issue type, for standard experience. In MQR mode the change of issue type does not exist anymore
- Change of issue severity - both for standard experience and MQR mode - (except when target is SonarQube Cloud, issue severity can't be changed)
- Issue marked as False positive or Accepted (or Won't fix for older SonarQube Server instances)
- Issue re-opened
- Issue assignments (if the same user can be matched in source and target instance. To avoid the problem of different issue ids, the match is performed on the user name)
- Issue comments
- Issue custom tags
**Hotspots**
- Custom tags added to issues
- Hotspot marked as Safe, Acknowledged or Fixed
- Hotspots re-opened as To Review
- Hotspots assignments
- Hotspots comments

Synchronized target issues have the `synchronized` tag added (not hotspots since there are no tags on hotpots)

# What cannot always be synchronized

- On SonarQube Cloud, Hotspots can't be acknowledged. This hotspot status does not exists
- On SonarQube Cloud, issues severity can't be changed
- If the assignee does not exists on the target instance, Issue and hotspot assignment can't happen
- On SonarQube Server in MQR mode and on SonarQube Cloud, issues can't be changed of type (Vulnerability, Bug or Code Smell).
  This is only possible with SonarQube Server in standard experience. And this is however deprecated and may no longer be possible in the future.
- When multiple target findings approximately match the source finding, none are synchronized and the list of possible matches is listed so that humans can manually find and synchronized the finding (this is a rare corner case)
- If the code was not analyzed with the same environment or with the same exact code, some findings may be present in the source and not in the target in which case the source can't be synchronized

## Configurable behaviors

When an issue is synchronized, a special comment is added on the target issue with a link to the source one, for cross checking purposes. This comment can be disabled by using the `--nolink` option

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
sonar-findings-sync -k projectKey1 -K projectKey2 -f sync_2_projects.json

# Syncs issues from projectKey1 main branch to projectKey2 main branch
sonar-findings-sync -k myProjectKey -U https://anothersonar.acme-corp.com -t d04d671eaec0272b6c83c056ac363f9b78919b06 -K otherInstanceProjKey >sync_2_instances.json
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
