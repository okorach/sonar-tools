# sonar-audit configuration file documentation

The `sonar-audit` tool accept a configuration where a certain number of auditing thresholds
can be configured. The following parameters can be customized. The value listed below is the
default value.
`sonar-audit` will:
- first check for a `sonar-audit.properties` file in the current directory
- second check for a `.sonar-audit.properties` file in the user home directory
- third will otherwise apply the default settings

You can create a default config file in the home directory by running `sonar-audit --config`

```
#======================== SELECT AUDIT SCOPE CONFIGURATION =======================

# yes/no
audit.globalSettings = yes
audit.projects = yes
audit.qualityGates = yes
audit.qualityProfiles = yes
audit.tokens = yes
audit.portfolios = yes
audit.applications = yes

#===================== GLOBAL SETTINGS AUDIT CONFIGURATION ====================

#----------------------- GLOBAL SETTINGS CONFIGURATION ------------------------

# Audit (and warn) for default project public visibility
audit.globalSettings.defaultProjectVisibility = private

# Below settings audit structure is:
# For allowed range settings:
# audit.globalSettings.range.<auditSequenceNbr> = <setting>, <minAllowedValue>, <maxAllowedValue>, <auditSeverity>, <impactedArea>
# For allowed value settings:
# audit.globalSetting.value.<auditSequenceNbr> = <setting>, <allowedValue>, <auditSeverity>, <impactedArea>
# To check if a setting is set:
# audit.globalSettings.isSet.<auditSequenceNbr> = <setting>, <auditSeverity>, <impactedArea>

# Audit (and warn) if cross project duplication is enabled
audit.globalSettings.value.1 = sonar.cpd.cross_project, false, HIGH, PERFORMANCE

# Audit (and warn) if force authentication is disabled
audit.globalSettings.value.2 = sonar.forceAuthentication, true, HIGH, SECURITY

# Audit (and warn) if server base URL is not set
audit.globalSettings.isSet.1 = sonar.core.serverBaseURL, HIGH, OPERATIONS

#----------------------- DB CLEANER AUDIT CONFIGURATION -----------------------

# Audit (and warn) for suspicious DB cleaner settings
audit.globalSettings.dbcleaner = yes

# Audit DB Cleaner min/max time before purging issues
audit.globalSettings.range.1 = sonar.dbcleaner.daysBeforeDeletingClosedIssues, 10, 60, MEDIUM, PERFORMANCE

# Audit DB Cleaner min/max time before only keeping one analysis snapshot per day
audit.globalSettings.range.2 = sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay, 12, 240, MEDIUM, PERFORMANCE

# Audit DB Cleaner min/max time before only keeping one analysis snapshot per week
audit.globalSettings.range.3 = sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek, 2, 12, MEDIUM, PERFORMANCE

# Audit DB Cleaner min/max time before only keeping one analysis snapshot per month
audit.globalSettings.range.4 = sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth, 26, 104, MEDIUM, PERFORMANCE

# Audit DB Cleaner min/max time before deleting all snapshots
audit.globalSettings.range.5 = sonar.dbcleaner.weeksBeforeDeletingAllSnapshots, 104, 260, MEDIUM, PERFORMANCE

# Audit DB Cleaner min/max time before deleting inactive branches
audit.globalSettings.range.6 = sonar.dbcleaner.daysBeforeDeletingInactiveBranches, 10, 60, MEDIUM, PERFORMANCE

#------------------- TECH DEBT SETTINGS AUDIT CONFIGURATION -------------------

# Audit for suspicious technical debt thresholds, listed further below
audit.globalSettings.technicalDebt = yes

# Audit if dev cost of 1 line is not within expected range (affects Tech Debt ratio and Maintainability rating metrics)
audit.globalSettings.range.7 = sonar.technicalDebt.developmentCost, 20, 30, MEDIUM, CONFIGURATION

# Audit if maintainaibility rating thresholds are not within normal ranges
audit.globalSettings.maintainabilityRating.A.range.1 = 0.03, 0.05, MEDIUM, CONFIGURATION
audit.globalSettings.maintainabilityRating.A.range.2 = 0.02, 0.07, HIGH, CONFIGURATION
audit.globalSettings.maintainabilityRating.B.range.1 = 0.07, 0.10, MEDIUM, CONFIGURATION
audit.globalSettings.maintainabilityRating.B.range.2 = 0.05, 0.15, HIGH, CONFIGURATION
audit.globalSettings.maintainabilityRating.C.range.1 = 0.15, 0.20, MEDIUM, CONFIGURATION
audit.globalSettings.maintainabilityRating.C.range.2 = 0.10, 0.25, HIGH, CONFIGURATION
audit.globalSettings.maintainabilityRating.D.range.1 = 0.40, 0.50, MEDIUM, CONFIGURATION
audit.globalSettings.maintainabilityRating.D.range.2 = 0.30, 0.60, HIGH, CONFIGURATION

#======================= PERMISSIONS AUDIT CONFIGURATION ======================

#----------------------------- GLOBAL PERMISSIONS -----------------------------
# Max allowed number of users/groups with global admin permission
audit.globalSettings.permissions.maxAdminUsers = 3
audit.globalSettings.permissions.maxAdminGroups = 2

# Max allowed number of users/groups with quality gate admin permission
audit.globalSettings.permissions.maxGateAdminUsers = 3
audit.globalSettings.permissions.maxGateAdminGroups = 2

# Max allowed number of users/groups with quality profile admin permission
audit.globalSettings.permissions.maxProfileAdminUsers = 3
audit.globalSettings.permissions.maxProfileAdminGroups = 2

# Max allowed number of users/groups with execute analysis permission
audit.globalSettings.permissions.maxScanUsers = 3
audit.globalSettings.permissions.maxScanGroups = 2

# Max allowed number of users/groups with create project permission
audit.globalSettings.permissions.maxCreateProjectUsers = 3
audit.globalSettings.permissions.maxCreateProjectGroups = 3

#----------------------------- PROJECT PERMISSIONS ----------------------------
# Project permission audit
# Max sure there are not too many users/groups with given project permissions
audit.projects.permissions.maxUsers = 5
audit.projects.permissions.maxAdminUsers = 2
audit.projects.permissions.maxGroups = 5
audit.projects.permissions.maxAdminGroups = 2
audit.projects.permissions.maxScanGroups = 1
audit.projects.permissions.maxIssueAdminGroups = 2
audit.projects.permissions.maxHotspotAdminGroups = 2
# audit.projects.permissions.anyone = yes

#========================= PROJECT AUDIT CONFIGURATION ========================

# Audit and warn) for projects likely to be duplicates
# Duplicate projects are detected from project keys that are similar
audit.projects.duplicates = yes

# Audit and warn) for projects that have been provisioned but never analyzed
audit.projects.neverAnalyzed = yes

# Audit (and warn) if project visibility is public
audit.projects.visibility = yes

# Audit (and warn) for suspicious projects permissions
audit.projects.permissions = yes

# Audit (and warn) for suspicious projects exclusions
audit.projects.exclusions = yes
audit.projects.suspiciousExclusionsPatterns = \*\*/[^\/]+/\*\*, \*\*\/\*\.\w+, **/*\.(java|jav|cs|csx|py|php|js|ts|sql|html|css|cpp|c|h|hpp)
audit.projects.suspiciousExclusionsExceptions = \*\*/(__pycache__|lib|lib|vendor|node_modules)\/\*\*


# Audit (and warn) for projects whose last analysis date is older than maxLastAnalysisAge
audit.projects.lastAnalysisDate = yes
audit.projects.maxLastAnalysisAge = 180

# Audit (and warn) for suspicious global permissions
audit.globalSettings.permissions = yes

#====================== QUALITY GATES AUDIT CONFIGURATION =====================

# Audit that there are not too many quality gates, this defeats company common governance
audit.qualitygates.maxNumber = 5

# Audit that quality gates don't have too many criterias, it's too complex and
# may prevent passing QG because of incorrect QG criteria
audit.qualitygates.maxConditions = 8

# Audits that QGs only use the meaningful metrics (those that make sense in a QG)
audit.qualitygates.allowedMetrics = new_reliability_rating, new_security_rating, new_maintainability_rating, new_bugs, new_vulnerabilities, new_security_hotspots, new_security_hotspots_reviewed, new_blocker_violations, new_critical_violations, new_major_violations, new_duplicated_lines_density, reliability_rating, security_rating

#------------------------ AUDIT OF METRICS ON NEW CODE ------------------------

# Audit that reliability, security, maintainability, hotspot review ratings, if used, are A
# if rating is used as a QG criteria
audit.qualitygates.new_reliability_rating.value = 1
audit.qualitygates.new_security_rating.value = 1
audit.qualitygates.new_hotspot_rating.value = 1
audit.qualitygates.new_maintainability_rating.value = 1

# Audit that coverage on new code, if used, is between 20% and 90%
audit.qualitygates.new_coverage.range = 20,90

# Audit that new bugs, vulnerabilities, unreviewed hotspots metric, if used, is 0
audit.qualitygates.new_bugs.value = 0
audit.qualitygates.new_vulnerabilities.value = 0
audit.qualitygates.new_security_hotspots.value = 0

# Audit that % of hotspots review on new code, if used, is 100%
audit.qualitygates.new_security_hotspots_reviewed.value = 100

# Audit that new blockers/critical/major issues metric, if used, is 0
audit.qualitygates.new_blocker_violations.value = 0
audit.qualitygates.new_critical_violations.value = 0
audit.qualitygates.new_major_violations.value = 0

# Audit that duplication on new code, if used, is between 1% and 5%
audit.qualitygates.new_duplicated_lines_density.range = 1, 5

#---------------------- AUDIT OF METRICS ON OVERALL CODE ----------------------

# Audit that reliability/security/hotspot rating on overall code, if used, is not too strict
audit.qualitygates.reliability_rating.range = 4, 4
audit.qualitygates.security_rating.range = 3, 4
audit.qualitygates.hotspot_rating.range = 4, 4

#========================= USERS AND TOKENS AUDIT CONFIGURATION =========================

# Audit (and warn) for empty portfolios
audit.groups.empty = yes

# Audit for users that have not logged in for a given number of days
audit.users.maxLoginAge = 180

# Comma separated list of SonarQube users whose tokens are not considered for expiration
audit.tokens.neverExpire =

# Audit today for days after which a token should be revoked (and potentially renewed)
audit.tokens.maxAge = 90

# Audit today for days after which an unused token should be revoked (and potentially renewed)
audit.tokens.maxUnusedAge = 30

#========================= PORTFOLIOS AND APPS AUDIT CONFIGURATION =========================

# Audit (and warn) for empty portfolios
audit.portfolios.empty = yes

# Audit (and warn) for empty portfolios
audit.applications.empty = yes
```