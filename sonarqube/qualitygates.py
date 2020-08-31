#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "quality gate" concept

'''

import json
import sonarqube.sqobject as sq
import sonarqube.env as env
import sonarqube.utilities as util

import sonarqube.audit_severities as sev
import sonarqube.audit_types as typ
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb


NEW_ISSUES_SHOULD_BE_ZERO = 'Any numeric threshold on new issues should be 0 or should be removed from QG conditions'

GOOD_QG_CONDITIONS = {
    'new_reliability_rating':
        (1, 1, 'Any rating other than A would let bugs slip through in new code'),
    'new_security_rating':
        (1, 1, 'Any rating other than A would let vulnerabilities slip through in new code'),
    'new_maintainability_rating':
        (1, 1, 'Expectation is that code smells density on new code is low enough to get A rating'),
    'new_coverage':
        (20, 90, 'Coverage below 20% is a too low bar, above 90% is overkill'),
    'new_bugs':
        (0, 0, NEW_ISSUES_SHOULD_BE_ZERO),
    'new_vulnerabilities':
        (0, 0, NEW_ISSUES_SHOULD_BE_ZERO),
    'new_security_hotspots':
        (0, 0, NEW_ISSUES_SHOULD_BE_ZERO),
    'new_blocker_violations':
        (0, 0, NEW_ISSUES_SHOULD_BE_ZERO),
    'new_critical_violations':
        (0, 0, NEW_ISSUES_SHOULD_BE_ZERO),
    'new_major_violations':
        (0, 0, NEW_ISSUES_SHOULD_BE_ZERO),
    'new_duplicated_lines_density':
        (1, 5, "Duplication on new code of less than 1% is overkill, more than 5% is too relaxed"),
    'new_security_hotspots_reviewed':
        (100, 100, 'All hotspots on new code must be reviewed, any other condition than 100% make little sense'),
    'reliability_rating':
        (4, 4, 'Threshold on overall code should not be too strict or passing the QG will be often impossible'),
    'security_rating':
        (4, 4, 'Threshold on overall code should not be too strict or passing the QG will be often impossible')
}


class QualityGate(sq.SqObject):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, env=endpoint)
        if data is None:
            return
        self.name = data['name']
        self.is_default = data['isDefault']
        self.is_built_in = data['isBuiltIn']
        resp = env.get('qualitygates/show', ctxt=self.env, params={'id': self.key})
        data = json.loads(resp.text)
        self.conditions = []
        self.projects = None
        for c in data.get('conditions', []):
            self.conditions.append(c)

    def get_projects(self):
        if self.projects is None:
            self.projects = self.search()
        return self.projects

    def count_projects(self):
        _ = self.get_projects()
        return len(self.projects)

    def __audit_conditions__(self):
        problems = []
        for c in self.conditions:
            m = c['metric']
            if m not in GOOD_QG_CONDITIONS:
                rule = rules.get_rule(rules.RuleId.QG_WRONG_METRIC)
                problems.append(pb.Problem(
                    rule.type, rule.severity, rule.msg.format(self.name, m)))
                continue
            val = int(c['error'])
            (mini, maxi, msg) = GOOD_QG_CONDITIONS[m]
            util.logger.debug('Condition on metric "%s": Check that %d in range [%d - %d]', m, val, mini, maxi)
            if val < mini or val > maxi:
                problems.append(pb.Problem(
                    typ.Type.BAD_PRACTICE, sev.Severity.HIGH,
                    "Quality Gate '{}' condition on metric '{}': {}".format(self.name, m, msg)))
        return problems

    def audit(self):
        util.logger.info("Auditing quality gate %s", self.name)
        problems = []
        if self.is_built_in:
            return problems
        nb_conditions = len(self.conditions)
        if nb_conditions == 0:
            rule = rules.get_rule(rules.RuleId.QG_NO_COND)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.name)))
        elif nb_conditions > 8:
            rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_COND)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.name, len(self.conditions))))
        problems += self.__audit_conditions__()
        if not self.is_default and not self.get_projects():
            rule = rules.get_rule(rules.RuleId.QG_NOT_USED)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.name)))
        return problems

    def count(self, params=None):
        if params is None:
            params = {}
        params['gateId'] = self.key
        params['ps'] = 1
        resp = env.get('qualitygates/search', ctxt=self.env, params=params)
        data = json.loads(resp.text)
        return data['paging']['total']

    def search(self, page=0, params=None):
        if params is None:
            params = {}
        params['ps'] = 500
        if page != 0:
            params['p'] = page
            resp = env.get('qualitygates/search', ctxt=self.env, params=params)
            data = json.loads(resp.text)
            return data['results']

        nb_proj = self.count(params=params)
        nb_pages = (nb_proj + 499) // 500
        prj_list = {}
        for p in range(nb_pages):
            params['p'] = p + 1
            for prj in self.search(page=p + 1, params=params):
                prj_list[prj['key']] = prj
        return prj_list


def list_qg(endpoint=None):
    resp = env.get('qualitygates/list', ctxt=endpoint)
    data = json.loads(resp.text)
    qg_list = []
    for qg in data['qualitygates']:
        qg_list.append(QualityGate(key=qg['id'], endpoint=endpoint, data=qg))
    return qg_list


def audit(endpoint=None):
    util.logger.info("Auditing quality gates")
    problems = []
    quality_gates_list = list_qg(endpoint)
    nb_qg = len(quality_gates_list)
    if nb_qg > 5:
        rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_GATES)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(nb_qg, 5)))
    for qg in quality_gates_list:
        problems += qg.audit()
    return problems
