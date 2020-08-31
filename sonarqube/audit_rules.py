import enum
import json
import sonarqube.audit_severities as sev
import sonarqube.audit_types as typ

import sonarqube.utilities as util

__RULES__ = {}


class RuleId(enum.Enum):
    DEFAULT_ADMIN_PASSWORD = 1

    SETTING_FORCE_AUTH = 100
    SETTING_PROJ_DEFAULT_VISIBILITY = 101
    SETTING_CPD_CROSS_PROJECT = 102

    SETTING_NOT_SET = 110
    SETTING_SET = 111
    SETTING_VALUE_INCORRECT = 112
    SETTING_VALUE_OUT_OF_RANGE = 113

    SETTING_BASE_URL = 120
    SETTING_DB_CLEANER = 121
    SETTING_MAINT_GRID = 122
    SETTING_SLB_RETENTION = 123
    SETTING_TD_LOC_COST = 124

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
    PROJ_PERM_SONAR_USERS_ELEVATED_PERMS = 1205
    PROJ_PERM_ANYONE = 1206

    PROJ_XML_LOCS = 1300

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


class RuleConfigError(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message


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
    global __RULES__
    import pathlib
    util.logger.info("Loading audit rules")
    path = pathlib.Path(__file__).parent
    with open(path / 'rules.json', 'r') as rulefile:
        rules = json.loads(rulefile.read())
    rulefile.close()
    __RULES__ = {}
    for rule_id, rule in rules.items():
        if to_id(rule_id) is None:
            raise RuleConfigError("Rule '{}' from rules.json is not a legit ruleId".format(rule_id))
        if typ.to_type(rule.get('type', '')) is None:
            raise RuleConfigError("Rule '{}' from rules.json has no or incorrect type".format(rule_id))
        if sev.to_severity(rule.get('severity', '')) is None:
            raise RuleConfigError("Rule '{}' from rules.json has no or incorrect severity".format(rule_id))
        if 'message' not in rule:
            raise RuleConfigError("Rule '{}' from rules.json has no message defined'".format(rule_id))
        __RULES__[to_id(rule_id)] = Rule(
            rule_id, rule['severity'], rule['type'], rule.get('object', ''), rule['message'])

    # Cross check that all rule Ids are defined in the JSON
    for rule in RuleId:
        if rule not in __RULES__:
            raise RuleConfigError("Rule {} has no configuration defined in 'rules.json'".format(str(rule)))


def get_rule(rule_id):
    global __RULES__
    return __RULES__[rule_id]
