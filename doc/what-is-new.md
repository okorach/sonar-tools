# Version 2.9 - March 2024

- Improvements:
  - Allow non admin tokens for sonar-tools not requiring them - #946 (Credit @raspy)

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
- Tool now uses live data for Sonar update center (instead of hardcoding versions) to determine what version re LTS and LATEST
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


