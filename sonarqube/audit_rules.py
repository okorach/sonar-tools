import enum
import json
import sonarqube.audit_severities as sev
import sonarqube.audit_types as typ

import sonarqube.utilities as util

RULES = {}

class RuleId(enum.Enum):
    DEFAULT_ADMIN_PASSWORD = 1

    SETTING_FORCE_AUTH = 100
    SETTING_PROJ_DEFAULT_VISIBILITY = 101
    SETTING_CPD_CROSS_PROJECT = 102

    SETTING_BASE_URL = 103
    SETTING_DB_CLEANER = 104
    SETTING_MAINT_GRID = 105
    SETTING_SLB_RETENTION = 106
    SETTING_TD_LOC_COST = 107

    PROJ_LAST_ANALYSIS = 1000
    PROJ_NOT_ANALYZED = 1001
    PROJ_VISIBILITY = 1002
    PROJ_DUPLICATE = 1003

    PROJ_PERM_MAX_USERS = 1100
    PROJ_PERM_MAX_ADM_USERS = 1101
    PROJ_PERM_MAX_ISSUE_ADM_USERS = 1102
    PROJ_PERM_MAX_HOTSPOT_ADM_USERS = 1103
    PROJ_PERM_MAX_SCAN_USERS = 1104

    PROJ_PERM_MAX_GROUPS = 1200
    PROJ_PERM_MAX_ADM_GROUPS = 1201
    PROJ_PERM_MAX_ISSUE_ADM_GROUPS = 1202
    PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS = 1203
    PROJ_PERM_MAX_SCAN_GROUPS = 1204
    PROJ_PERM_ANYONE = 1205

    QG_NO_COND = 2000
    QG_TOO_MANY_COND = 2001
    QG_NOT_USED = 2002
    QG_TOO_MANY_GATES = 2003
    QG_WRONG_METRIC = 2004
    QG_WRONG_THRESHOLD = 2005

    QP_TOO_MANY_QP = 3000
    QP_LAST_USED_DATE = 3001
    QP_LAST_CHANGE_DATE = 3002
    QP_TOO_FEW_RULES = 3003
    QP_NOT_USED = 3004
    QP_USE_DEPRECATED_RULES = 3005

    def __str__(self):
        return repr(self.name)[1:-1]


class Rule:
    def __init__(self, rule_id, severity, rule_type, concerned_object, message):
        self.id = to_id(rule_id)
        self.severity = sev.to_severity(severity)
        self.type = typ.to_type(rule_type)
        self.object = concerned_object
        self.msg = message


def to_id(val):
    for enum_val in RuleId:
        if repr(enum_val.name)[1:-1] == val:
            return enum_val
    return None


def load():
    global RULES
    import pathlib
    util.logger.info("Loading audit rules")
    path = pathlib.Path(__file__).parent
    with open(path / 'rules.json', 'r') as rulefile:
        rules = json.loads(rulefile.read())
    rulefile.close()
    RULES = {}
    for rule_id, rule in rules.items():
        RULES[to_id(rule_id)] = Rule(rule_id, rule['severity'], rule['type'], rule.get('object', ''), rule['message'])


def show():
    global RULES
    for rule_id, rule in RULES.items():
        util.logger.info("Rule {}: {}, {}, {}".format(str(rule_id), str(rule.severity), str(rule.type), str(rule.msg)))

'''
{
    RuleId.DEFAULT_ADMIN_PASSWORD:
        {
            'severity': Severity.CRITICAL,
            'type': Type.SECURITY,
            'message': "Default admin password has not been changed, this is a critical security risk"
        },
    RuleId.SETTING_FORCE_AUTH:
        {
            'severity': Severity.HIGH,
            'type': Type.SECURITY,
            'message': "'sonar.forceAuthentation' is set to 'false', this is a security risk"
        },
    RuleId.SETTING_PROJ_DEFAULT_VISIBILITY:
        {
            'severity': Severity.HIGH,
            'type': Type.SECURITY,
            'message': "Projects default visibility is 'Public', this is a security risk"
        },
    RuleId.SETTING_CPD_CROSS_PROJECT:
        {
            'severity': Severity.MEDIUM,
            'type': Type.PERFORMANCE,
            'message': "Cross project duplication is set to 'true', this can have a negative performance impact"
        },
    RuleId.SETTING_BASE_URL:
        {
            'severity': Severity.HIGH,
            'type': Type.OPERATIONS,
            'message': "'sonar.core.serverBaseURL' is not set, this may break some features"
        },
    RuleId.SETTING_DB_CLEANER:
        {
            'severity': Severity.MEDIUM,
            'type': Type.OPERATIONS,
            'message': "DB Cleaner setting '{}' is outside of recommended range [{}-{}]"
        },
    RuleId.SETTING_MAINT_GRID:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Maintainability rating threshold for '{}' is outside of recommended range [{}-{}]"
        },
    RuleId.SETTING_SLB_RETENTION:
        {
            'severity': Severity.MEDIUM,
            'type': Type.PERFORMANCE,
            'message': "Short Lived Branches retention duration '{}' is outside of recommended range [{}-{}]"
        },
    RuleId.SETTING_TD_LOC_COST:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Time to develop 1 line of code '{} min' is outside of recommended range [{}-{}]"
        },
    RuleId.PROJ_LAST_ANALYSIS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.PERFORMANCE,
            'message': "Project '{}' has not been analyzed since {} days, it could be deleted"
        },
    RuleId.PROJ_NOT_ANALYZED:
        {
            'severity': Severity.LOW,
            'type': Type.PERFORMANCE,
            'message': "Project '{}' has been created but never analyzed, it could be deleted"
        },
    RuleId.PROJ_VISIBILITY:
        {
            'severity': Severity.HIGH,
            'type': Type.SECURITY,
            'message': "Project '{}' visibility is 'Public', this is a security risk"
        },
    RuleId.PROJ_DUPLICATE:
        {
            'severity': Severity.MEDIUM,
            'type': Type.PERFORMANCE,
            'messsage': "Project '{}' is likely to be a duplicate of project '{}', it could be deleted"
        },
    RuleId.PROJ_PERM_MAX_USERS:
        {
            'severity': Severity.MEDIUM,
            'Type': Type.OPERATIONS,
            'message': "Project '{}' has {} users with permissions, this is too much, use groups instead"
        },
    RuleId.PROJ_PERM_MAX_ADM_USERS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} users with admin permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_ISSUE_ADM_USERS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} users with issue admin permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_USERS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} users with hotspot admin permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_SCAN_USERS:
        {
            'severity': Severity.HIGH,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} users with analysis permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_GROUPS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} groups with permissions, this is more than the {} recommended"
        },
    RuleId.PROJ_PERM_MAX_ADM_GROUPS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} groups with admin permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS:
        {
            'severity': Severity.MEDIUM,
            'Type': Type.GOVERNANCE,
            'message': "Project '{}' has {} groups with issue admin permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS:
        {
            'severity': Severity.MEDIUM,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} groups with hotspot admin permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_MAX_SCAN_GROUPS:
        {
            'severity': Severity.HIGH,
            'type': Type.GOVERNANCE,
            'message': "Project '{}' has {} groups with analysis permission, this is more than the max {} recommended"
        },
    RuleId.PROJ_PERM_ANYONE:
        {
            'severity': Severity.HIGH,
            'type': Type.SECURITY,
            'message': "Group 'Anyone' has permissions on Project '{}', this is a security risk"
        },
    RuleId.QG_NO_COND:
    {
        'severity': Severity.HIGH,
        'type': Type.GOVERNANCE,
        'message': "Quality Gate '{}' has no conditions defined, this is meaningless"
    },
    RuleId.QG_TOO_MANY_COND:
    {
        'severity': Severity.MEDIUM,
        'type': Type.GOVERNANCE,
        'message': "Quality Gate '{}' has {} conditions defined, more than the max {} recommended"
    },
    RuleId.QG_NOT_USED:
    {
        'severity': Severity.MEDIUM,
        'type': Type.OPERATIONS,
        'message': "Quality Gate '{}' is not used, it should be deleted"
    },
    RuleId.QG_TOO_MANY_GATES:
    {
        'severity': Severity.MEDIUM,
        'type': Type.GOVERNANCE,
        'message': "There are {} Quality Gates defined, this is more than the max {} recommended"
    },
    RuleId.QG_WRONG_METRIC:
    {
        'severity': Severity.HIGH,
        'type': Type.GOVERNANCE,
        'message': "Quality Gate '{}' has a condition on metric '{}', this is not recommended"
    },
    RuleId.QG_WRONG_THRESHOLD:
    {
        'severity': Severity.HIGH,
        'type': Type.GOVERNANCE,
        'message': "Quality Gate '{}' threshold {} on metric '{}', is outside of the recommended range [{}-{}]"
    },
    RuleId.QP_TOO_MANY_QP:
    {
        'severity': Severity.MEDIUM,
        'type': Type.GOVERNANCE,
        'message': "There are {} Quality Profiles defined for language '{}', this is more than the max {} recommended"
    },
    RuleId.QP_LAST_USED_DATE:
    {
        'severity': Severity.MEDIUM,
        'type': Type.OPERATIONS,
        'message': "Quality Profiles '{}' of language '{}' has not been used since {} days, it should be deleted"
    },
    RuleId.QP_LAST_CHANGE_DATE:
    {
        'severity': Severity.MEDIUM,
        'type': Type.GOVERNANCE,
        'message': "Quality Profiles '{}' of language '{}' has not been updated since {} days, it should be updated"
    },
    RuleId.QP_TOO_FEW_RULES:
    {
        'severity': Severity.HIGH,
        'type': Type.GOVERNANCE,
        'message': "Quality Profiles '{}' of language '{}' has {} rules, this is too few"
    },
    RuleId.QP_NOT_USED:
    {
        'severity': Severity.MEDIUM,
        'type': Type.OPERATIONS,
        'message': "Quality Profiles '{}' of language '{}' is not used, it should be deleted"
    },
    RuleId.QP_USE_DEPRECATED_RULES:
    {
        'severity': Severity.MEDIUM,
        'type': Type.GOVERNANCE,
        'message': "Quality Profiles '{}' of language '{}' uses deprecated rules, it should be updated"
    }
}
'''
