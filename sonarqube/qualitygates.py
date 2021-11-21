#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
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
        self.is_default = data.get('isDefault', False)
        self.is_built_in = data.get('isBuiltIn', False)
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

    def audit(self, audit_settings=None):
        util.logger.debug("Auditing quality gate '%s'", self.name)
        problems = []
        if self.is_built_in:
            return problems
        max_cond = int(util.get_setting(audit_settings, 'audit.qualitygates.maxConditions', 8))
        nb_conditions = len(self.conditions)
        util.logger.debug("Auditing quality gate '%s' number of conditions (%d) is OK",
            self.name, nb_conditions)
        if nb_conditions == 0:
            util.logger.warning("Quality gate '%s' has 0 conditions", self.name)
            rule = rules.get_rule(rules.RuleId.QG_NO_COND)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.name)))
        elif nb_conditions > max_cond:
            util.logger.warning("Quality gate '%s' has too many (%d) conditions", self.name, nb_conditions)
            rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_COND)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.name, len(self.conditions), 8)))
        problems += self.__audit_conditions__()
        util.logger.debug("Auditing quality gate '%s' has some assigned projects", self.name)
        if not self.is_default and not self.get_projects():
            util.logger.warning("Quality gate '%s' has no assigned projects", self.name)
            rule = rules.get_rule(rules.RuleId.QG_NOT_USED)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.name)))
        return problems

    def count(self, params=None):
        if params is None:
            params = {}
        params['gateId'] = self.key
        page = 1
        if self.env.version() < (7, 9, 0):
            params['ps'] = 100
            params['p'] = page
        else:
            params['ps'] = 1
        more = True
        count = 0
        while more:
            resp = env.get('qualitygates/search', ctxt=self.env, params=params)
            data = json.loads(resp.text)
            if self.env.version() >= (7, 9, 0):
                count = data['paging']['total']
                more = False
            else:
                count += len(data['results'])
                more = data['more']
        return count

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
                if 'key' in prj:
                    prj_list[prj['key']] = prj
                else:
                    prj_list[prj['id']] = prj
        return prj_list


def list_qg(endpoint=None):
    resp = env.get('qualitygates/list', ctxt=endpoint)
    data = json.loads(resp.text)
    qg_list = []

    for qg in data['qualitygates']:
        qg_obj = QualityGate(key=qg['id'], endpoint=endpoint, data=qg)
        if endpoint.version() < (7, 9, 0) and 'default' in data and data['default'] == qg['id']:
            qg_obj.is_default = True
        qg_list.append(qg_obj)
    return qg_list


def audit(endpoint=None, audit_settings=None):
    util.logger.info("--- Auditing quality gates ---")
    problems = []
    quality_gates_list = list_qg(endpoint)
    max_qg = util.get_setting(audit_settings, 'audit.qualitygates.maxNumber', 5)
    nb_qg = len(quality_gates_list)
    util.logger.debug("Auditing that there are no more than %s quality gates", str(max_qg))
    if nb_qg > max_qg:
        rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_GATES)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(nb_qg, 5)))
    for qg in quality_gates_list:
        problems += qg.audit(audit_settings)
    return problems
