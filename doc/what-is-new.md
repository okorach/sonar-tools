# Version 2.4

## general
- All tools that connect to a SonarQube server can not specify a client certificate if needed
- Potentially long running tools displays in the logs the total execution time at end of execution
- Several optimizations (caching) have been implemented to reduce number of SonarQube API calls

## sonar-audit
- `sonar-audit` is now multi-threaded, this can dramatically increase speed of audit on large platforms with a lot of projects (which is the object consuming most of the auditing time)
- `sonar-audit` now uses dynamic data for Sonar update center (instead of hardcoding versions) to check for LTS and LATEST
- `sonar-audit` now allows to audit a selection of project or portfolios (chosen by their key)
- `sonar-audit` now gracefully fails when a non existing project key is specified 
- `sonar-audit` now allows to add a link to the concerned object in the audit report (makes it easy to navigate to the object to fix)
- New audited stuff
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
- `sonar-config` export is now multi-threaded, this can dramatically increase speed of export on large platforms with a lot of projects (which is the object consuming most of the auditing time)
- `sonar-config` export now offers the option to export all object attributes, including thos that are useless for future import. Those attributes are prefixed by `_`
- `sonar-config` import now issues a warning when applying an unknown setting (typo in setting key?)
- Fixes:
  - Fix in export for permissions that could be incorrect in some cases
  - Fix in export of branch new code period definition export that was incorrect in some cases
  - Fix in import of project quality profiles that did not work when the quality profile had a spec in the name
  - Fix in import of applications: When the project main branch was used the application definition did not work
  - Fix v2.3 doc still stating that import was not availab le (it was already available in v2.3)

## sonar-findings-export
- `sonar-findings-export` is now multi-threaded, this can dramatically increase speed of export on large platforms with a lot of projects and a lot of issues
- `sonar-findings-export` gracefully fails when a non existing project key is specified 