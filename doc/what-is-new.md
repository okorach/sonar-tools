# Next version

# Version 3.18.2

* Fix issue https://github.com/okorach/sonar-tools/issues/2262: `sonar-findings-export` failing on SonarQube cloud 

# Version 3.18.1

* Dropped compatibility with SonarQube versions older than 9.9.0
* Dropped `sonar-custom-measures` tool (Custom measures are no longer supported since SonarQube 9.0)
* Added `sonar-misra` to export a MISRA report. See [sonar-misra doc](https://github.com/okorach/sonar-tools/blob/master/doc/sonar-misra.md) for details
* Added `sonar-maturity` to compute metrics related to the maturity of SonarQube usage
* `sonar-measures-export`:
  - Allowed to filter export of objects (projects/portfolios/apps) by last analysis date. See `--analyzedAfter` option
  - Allowed to select measures by regexp
* `sonar-audit`: A couple of fixes on audit false positives and false negatives
* `sonar-loc`: Allow to export LoC on PRs (Credit @sylvain-combe-sonarsource)
* `sonar-config`: Allow to import config in YAML format + A couple of bug fixes

* Significant refactoring for easier maintainability

See: https://github.com/okorach/sonar-tools/issues?q=is%3Aissue%20state%3Aclosed%20milestone%3A3.18

# Version 3.17.1

* `sonar-config`:
  - The export/import format has been vastly redefined. Import with the previous format will be rejected
    but a format conversion tool is provided
  - A [JSON schema](https://github.com/okorach/sonar-tools/blob/master/sonar/cli/sonar-config.schema.json) is available that defines the export/import format
  - Several improvements in export/import: New config elements are exported and imported (webhooks, MQR qualities
    new settings, and more...)
* `sonar-housekeeper`:
  - Added the `--keepWhenInactive` parameter that overrides the SonarQube defined one to decide which branches
    should be kept and which branches should be deleted
  - Projects, Branches, PRs and tokens can be deleted separately

# Version 3.16

* `sonar-config`:
  - Several improvements in applications export/import
  - Rule export format is modified, for the best
  - Handle SCA criteria in QG exports
  - A couple of bug fixes:
    - Rule custom params are exported
    - Import of instantiated rules is now working fine
    - Applications imports with project branches non existing
* `sonar-finding-sync`:
  - Projects can be selected through regexp, allowing to sync multiple (or all) projects are once
  - Incremental sync: findings are synced starting from the most recent change on the target finding
  - Sync separates changelog sync and comment sync for more accuracy
  - A tag can be added to all issues that were synchronized (not on hotspots, hotspots can't be tagged)
  - `sonar-findings-sync` is now compatible with Community Edition (as a source or target platform)
  - Fixed bug when synchronizing issues with no line nbr (file based issues)
* `sonar-findings-export`:
  - A couple of bug fixes when using complex export filters (was not working before)
* `sonar-audit`:
  - SonarQube Cloud audit improvements. The `Members` group on cloud is handled like the `sonar-users` group on Server
  - Fix a crash when auditing organizations
  - Added auditing that projects keys follow a given naming convention (match a given regexp)



# Version 3.15

* General performance (speed) improvements
* Allow to run tools with non admin tokens when possible (`sonar-measures-export`, `sonar-findings-export`, `sonar-loc`)
* Misc hardening

* `sonar-findings-sync`:
  - Fix #1871 - Sync may not happen when an issue has old transition data generated before MQR mode
  - Added precise doc about what issues are sync'ed
  - Fail fast with clear message if organization and/or project does not exists

* `sonar-config`:
  - /!\ Modification of export/import format for Quality Profiles
  - Export of rules custom severities
  - Export of prioritized rules
  - Export quality profiles permissions on SonarQube Cloud
  - Performance improvements
  - Fix on import of project visibility

* `sonar-audit`:
  - Fix to allow audit report in JSON format
  - Raise issue when duplicate quality gates or profiles
  - Raise issue when the new code period is too long (more than 90 days, configurable)
  - Raise issue when the `sonar-users` group has admin permission on QP, QG, App or Portfolio
  - Raise issue when an app or portfolio is Public
  - Raise issue when too many groups or users have permissions on anything
  - Raise issue when permissions on permission templates granted to users (instead of groups)
  - Make the project key comparison for duplicate less aggressive (was creating to many false positives)

# Version 3.14.1

* `sonar-findings-sync`: Fix #1871 - Sync may not happen when an issue has old transition data generated before MQR mode

# Version 3.14

* Most tools (`sonar-loc`, `sonar-measures-export`, `sonar-findings-export`, `sonar-projects`, `sonar-config`, `sonar-audit`) now select project keys and/or branches with regexp instead of comma separated list. This is more flexible. Old "key1,key2,key3" equivalent is "(key1|key2|key3)" 

* `sonar-audit`: Added check that tokens max lifetime is bound (Add check on `sonar.auth.token.max.allowed.lifetime` is not confired as "no expiration")

* `sonar-measures-export`: Updated list of default "main" metrics in line with new SonarQube 2025.x release


* Hardening:
- Bug fixes (#1752 #1764 #1789 #1786 #1798)
- Improved tests: Verify that export output is as per expectations

See https://github.com/okorach/sonar-tools/milestone/48 for details

# Version 3.13

* `sonar-projects` improvements
  - Allow to export/import or not projects with 0 LoCs (projects that were only provisioned)
  - Detect conflicts in project keys that generate the same zip file
  - Add URL of source and target project in report
  - Mutithread `sonar-projects` import
  - Diagnose import error based on background tasks results rather than (impossible) pre-checks
    (eg version check for Commuity Builds vs Commercial Editions)
  - Overall much more robust detection and reporting of export/import errors

* `sonar-audit`
  - Fix bug on checking proper value of boolean settings such as `sonar.cpd.cross_project` and `sonar.forceAuthentication`
    Provide more synthetic result of the export or import result
  - Don't raise issue when plugins that are registered on the update center are installed

# Version 3.12

* `sonar-projects` improvements
  - Honor the `--threads` parameter
  - General Hardening
  - Provide more synthetic result of the export result

# Version 3.11

* `sonar-findings-sync`
  - Fixed major sync regression
  - Added sync multithreading to significantly accelerate sync of large projects with many findings to sync
  - Covered support for several additional corner cases to increase number of issues that can be matched, and sync them
* Several bug fixes and hardening across the board
  
# Version 3.10

* `sonar-findings-sync` hardening
  - Allow `-O` option for target organization
  - Compatibility with MQR mode (credit @lukas-frystak-sonarsource)
  - Misc bug fixes
* `sonar-config`:
  - Fix bug about not exporting all projects when more than 1000 projects
  - Fix bug about not exporting groups that have no description
* `sonar-audit`:
  - New audit check to avoid using Scanner for .Net 9.2 that has a vulnerability
  - Fix incorrect warning when running 2025.1 with JRE 21 (this is supported)
  - Fix incorrect warning when SQS is run with JRE 17 (this is supported)
* `sonar-rules`:
  - Allow to only export rules of a given quality profile
* `sonar-findings-sync` hardening

# Version 3.9

* Compatibility with SonarQube 2025.1 release
* Fixed sonar-projects import pre-check to be less strict (follow new SonarQube criterias for project import)
* A few new things audited by sonar-audit (Excessive project history data points and Excessive proportion of accepted or FP issues)
* Bug fixes
* More unit tests

# Version 3.8

* Bug fixes
* Better compatibility with SonarQube 9.9, SonarCloud
* Better compatibility with SonarQube Community Build and Developer Edition
* Adjustments for SonarQube 10.8 (AI related features)
* Partial migration to users and groups APIv2

# Version 3.7

* Numerous hardening, functional and performance improvements on `sonar-audit`, `sonar-measures-export`, `sonar-findings-export`
* `sonar-config`:
  * import of portfolios should be more stable
  * import of quality profiles should be much faster
* `sonar-audit`:
  * Fix several cases of crash
  * New check: Tokens with no expiration date
* `sonar-measures-export`:
  * Fixed export with `--ratingsAsNumbers` and `--percentsAsString`
  * Measures that are % are now exported as a float between 0 and 1 (instead of 0 and 100). When `--percentsAsString` it is exported as `0%` to `100%` with rounding to 0.1%
  * In CSV, added header with all field names
  * Additional measures are sorted to always come in same order
* `sonar-findings-export`:
  * Issue tags are sorted to 

# Version 3.6

* Numerous hardening and improvements on `sonar-audit`, `sonar-measures-export`, `sonar-findings-sync`, `sonar-config`
  See https://github.com/okorach/sonar-tools/milestone/40?closed=1
* Added documentation of `sonar-rules`

# Version 3.5

* Many performance and robustness improvements
* `sonar-audit` improvements
  * Output audit problems on the fly #1395
  * Several fixes:
     * #1417 
     * #1415 
     * #1411 
     * #1386
* `sonar-config` fix #1326
* Include **dart** and **ipython** as built-in languages since they were introduced in SonarQube 10.7
* Display HTTP requests durations in logs

# Version 3.4.2

- Hotfix: Fix crash `sonar-audit` when SonarQube version is neither LTA nor Latest: [Issue #1386](https://github.com/okorach/sonar-tools/issues/1386)

# Version 3.4.1

- Hotfix: Fix systematic crash on `sonar-findings-export`: [Issue #1358](https://github.com/okorach/sonar-tools/issues/1358)

# Version 3.4

- `sonar-tools` is now available as a docker image
- `sonar-config`
  - Export can now export configuration as a YAML file (Only JSON was available previously).
    Import of YAML is not yet available
  - Beta version of config import in SonarCloud
- `sonar-audit` a couple of new audit problems on permission templates (with no permissions, with no or wrong regexp)
- Removed calls to all APIs deprecated with 10.x, used their up-to-date replacement instead

# Version 3.3

- `sonar-config`: Improved / Hardened several elements for both import and export
  - Fixed portfolios import/export
  - Fixed permissions import (for projects, applications and portfolios)
  - Better compatibility with SonarCloud
  - Other misc bug fixes
- `sonar-audit`: Added verification that projects are analyzed with the right scanner (Maven, Gradle, .Net). This verification is not 100% reliable


# Version 3.2.2

- Fix regressions in `sonar-config -i`

# Version 3.2.1

- Patch release to fix all compatibility problems with
  - Lower editions: All editions (Community, Developer, Enterprise) have been tested
  - 9.9 LTS/LTA version: All editions (Community, Developer, Enterprise) in version 9.9 have been tested

# Version 3.2

- Refactoring on portfolios for hardening
- `sonar-findings-export` and `sonar-rules` now have a `--languages` option to filter findings/rules in a restrained list of languages
- `sonar-measures-export` can export measures for Applications and Portfolios. For this reason, a new column (col 2) has been added to the CSV output format which can be PROJECT, BRANCH, APPLICATION, APPLICATIONBRANCH or PORTFOLIO
- `sonar-findings-export`:
  - Ability export findings for Applications and Portfolios, Application and Project branches
  - Fixes in SARIF export format
  - Adjustments to new issues taxonomy
  - Added option to not export all Sonar findings custom properties in SARIF export for more compact output
  - Added finding author and language column in CSV export, in JSON and SARIF too
  - Updated SARIF format export to not export custom properties when already standard SARIF fields
  - Have a new field language for the issue language
- `sonar-config`:
  - Smart handling of properties that can be lists. If the list contains a comma, the property
  is exported as list, if no comma, as a more compact comma separated string
  - Settings that are the default are no longer exported unless `--exportDefaults` option is provided
  - Changed the key for default branch from `__default__` to `-DEFAULT_BRANCH-` to make sure that this cannot conflict with a real branch name (because git forbids branches starting by -)
  - Portfolio export format has been slightly changed for consistency


# Version 3.1
  - Several bug fixes, in particular Sonar Tools would hang if providing a token with insufficient permissions for projects (Browse is minimally needed)
  - Major `sonar-finding-sync` hardening
    - Significant performance improvement through multithreading
    - Addition of the `--since` option to only sync issues modified since a date (likely to significantly speed up the syncing process)
    - Deprecation of the `--login` parameter of ` sonar-finding-sync`
  - `sonar-findings-export` now exports more meaningful issue status (FP, ACCEPTED etc...) instead of simply RESOLVED
  - Small improvement: `sonar-measures-export --history` can export measures history as history table
  - Small improvement: `sonar-audit` now checks for SonarQube logs to detect any suspicious error or warning

# Version 3.0
  - Compatibility with SonarCloud of the following tools:
    - `sonar-loc`
    - `sonar-measures-export`
    - `sonar-findings-export`
    - `sonar-findings-sync`
    - `sonar-housekeeper`
  - Migration of wording from LTS to LTA, to align with Sonar
  - Couple of improvements on **sonar-audit**,  **sonar-housekeeper**, **sonar-measures-export** 
  - Fix crashes of **sonar-findings-sync**
  - **sonar-measures-export** can now export measures history instead on only last value
  - Updated recent versions of scanner to check of deprecated scanner version usage (in audits)

# Version 2.11 - April 29th, 2024

  - Adjusted sonar-config export to the new capabilities of SonarQube 10.x
    - Ability to disable rules from parent in a child profile
    - Several new config parameters for JC language and all the IaC/Secrets anayzers
  - Check (occasionally) if a new version is available when running a sonar tool, and display info messsage

# Version 2.10.1 - April 18th, 2024

  - Fixed critical bug: `sonar-findings-export` hanging when exporting to CSV file with **sonar-tools** 2.10

# Version 2.10 - April 2024

  - Further audit features (see changelog)
  - Fixes problem in `sonar-housekeeper` causing crashes
  - Added `--httpTimeout` to all tools to sets the HTTP(S) requests timeout (default 10s)
  - Added ability for `sonar-findings-export` to export findings in [SARIF](https://sarifweb.azurewebsites.net/) 2.1 format (basic SARIF fields are populated)
  - Added **Server Id** as first field in `sonar-audit` CSV report (under field key `server_id` in JSON report)

# Version 2.9 - March 2024

- Improvements:
  - Allow non admin tokens for sonar-tools not requiring them - #946 (Credit @raspy)
  - Many hardening / compatibility with SonarQube 9.9 and 10.x - including audit of recent SIF format

# Version 2.8.2 - Feb 2024

- Updated docs for several partly innacurate things (Credit @sylvain-combe-sonarsource)
- Fixes:
  - Crashes when SonarQube URL has a trailing "/" - #934
  - Wrong function entry point for sonar-projects-import - #942 (Credit @sylvain-combe-sonarsource)
  - Crash when doing sonar-config full import of a partial export - #940

# Version 2.8.1 - Jan 2024

- Fixed several problems on findings (issues) sync on Community Edition
- Fixed failure on **sonar-loc** and **sonar-measures-export** with recent versions of **sonar-tools**
  with SonarQube Developer Edition, Enterprise Edition and DataCenter edition, when exporting
  LoC (`ncloc`) or Last Analysis Date
- **sonar-issues-sync** is deprecated. Migrated doc of **sonar-issues-sync** to **sonar-findings-sync**
- Added Copyright (c) 2024

# Version 2.8

- Additional compatibility with SonarQube 10+
- Ability to export findings (issues) without Global Sys Admin permission (only Project Browse permission needed)
- More thread safety on metrics manipulation
- Hardening

# Version 2.7.1

- Hardening

# Version 2.7

- Compatibility with SonarQube 10+
- Support of project analyzed with recent scanner version
  - Scanner for CLI 4.8+
  - Scanner for Gradle 3.5+
  - Scanner for .Net 5.9+
  - Scanner for NPM 2.9+

# Version 2.6

- Compatibility with SonarQube 9.7+
- Support of UTF-8 in branch names

# Version 2.5

- Mostly hardening

# Version 2.4

## General
- All tools that connect to a SonarQube server can not specify a client certificate if needed
- Potentially long running tools displays in the logs the total execution time at end of execution
- Several optimizations (caching) have been implemented to reduce number of SonarQube API calls
- Multi-threading for `sonar-audit`, `sonar-findings-export` and `sonar-config --export` for important performance (speed) gains
- Several new `sonar-audit` audited items

## sonar-audit
- Tool is now multi-threaded, this can dramatically increase speed of audit on large platforms with a lot of projects (which is the object consuming most of the auditing time)
- Tool now uses live data for Sonar update center (instead of hardcoding versions) to determine what version are LTA (ex-LTS) and LATEST
- Tool now allows to audit a selection of project or portfolios (chosen by their key)
- Tool now gracefully fails when a non existing project key is specified
- Tool now allows to add a link to the concerned object in the audit report (makes it easy to navigate to the object to fix)
- New **audit**ed stuff
  - Audits the version of scanner used and raise a warning if too old
  - Audits for portfolios and application background tasks failures
  - Audits permission templates (with same rules as project permissions)
  - Audits for warnings in last project scan (on main branch)
  - Audits when proportion of JSON code in a project is too high (More than 50% of JSON LoC for projects bigger than 100K LoC total). The same check already existed for XML before
  - Audits for global webhook delivery failures
  - Audits when a project both have a `main` and a `master` branch. This is a sign of potential misconfiguration
- Fixes:
  - Fixes a crash when some projects have too many users with admin permissions
  - Fixes a duplicate warning when 2 projects has suspiciously similar keys (May be different branches of same project)

## sonar-config
- **export** is now multi-threaded, this can dramatically increase speed of export on large platforms with a lot of projects (which is the object consuming most of the auditing time)
- **export** now offers the option to export all object attributes, including thos that are useless for future import. Those attributes are prefixed by `_` (underscore)
- **import** now issues a warning when applying an unknown setting (typo in setting key?)
- Fixes:
  - Fix in **export** for permissions that could be incorrect in some cases
  - Fix in **export** of branch new code period definition export that was incorrect in some cases
  - Fix in **import** of project quality profiles that did not work when the quality profile had a spec in the name
  - Fix in **import** of applications: When the project main branch was used the application definition did not work
  - Fix v2.3 doc still stating that import was not available (it was already available in v2.3)

## sonar-findings-export
- Tool is now multi-threaded, this can dramatically increase speed of export on large platforms with a lot of projects and a lot of issues
- Tool gracefully fails when a non existing project key is specified

## sonar-findings-sync
- Fix regression. tool was broken in v2.3

# Version 2.3

## General changes
- Adjust logs to new SonarQube 9.5 token format
- `sonar-tools` now use a specific user agent for all SonarQube API invocations (to recognized `sonar-tools` activity the whole SonarQube HTTP Traffic)

## sonar-config
- **import** of previously exported configurations is now available
- **export** format has been slightly modified to be more compact:
  - Groups, subportfolios, Quality Profiles and Users SCM accounts export format has changed
  - Built-in Quality Profiles and Quality Gates are no longer exported
  - Default group membership to sonar-users group is ommited
- **export** added a few missing items
  - Project visibility
  - Project specific webhooks
  - Branches protected from purge when inactive
  - Project main branch
  - Projects and Applications tags
  - Rules with custom extended description or custom tags
  - Custom rules (rules instantiated from rule templates)
- **export**: A few optimizationson export format to avoid exporting useless or empty stuff (objects will all the default settings)
- Fixes:
  - Fixes on quality gates permissions export
  - Fix on export of portfolios definition based on tags (was erroneously exported as regexp)
  - Gracefully handle commas in object whose key or name can contain a comma
  - Export local users group membership
  - Export multiple DevOps platforms of each type if there is mor ethan one
  - Export fails on permission templates with no regexp

## sonar-audit
- Fixes
  - `sonar-audit --config` fails


