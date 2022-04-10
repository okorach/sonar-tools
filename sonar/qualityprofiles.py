#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

    Abstraction of the SonarQube "quality profile" concept

'''
import datetime
import json
import pytz
from sonar import env, rules
import sonar.sqobject as sq
import sonar.utilities as util

import sonar.audit.rules as arules
import sonar.audit.problem as pb


class QualityProfile(sq.SqObject):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key, endpoint)
        if data is not None:
            self.name = data['name']
            if 'lastUsed' in data:
                self.last_used = util.string_to_date(data['lastUsed'])
            else:
                self.last_used = None
            self.last_updated = util.string_to_date(data['rulesUpdatedAt'])
            self.language = data['language']
            self.language_name = data['languageName']
            self.is_default = data['isDefault']
            self.project_count = data.get('projectCount', None)
            self.is_built_in = data['isBuiltIn']
            self.nbr_rules = int(data['activeRuleCount'])
            self.nbr_deprecated_rules = int(data['activeDeprecatedRuleCount'])
            self.parent_key = data.get('parentKey', None)
            self.parent_name = data.get('parentName', None)

    def __str__(self):
        return f"quality profile '{self.name}' of language '{self.language_name}'"

    def get_permissions(self, perm_type):
        resp = env.get(f'permissions/{perm_type}', ctxt=self.endpoint, params={'projectKey': self.key, 'ps': 1})
        data = json.loads(resp.text)
        nb_perms = int(data['paging']['total'])
        nb_pages = (nb_perms + 99) // 100
        perms = []
        for page in range(nb_pages):
            resp = env.get(f'permissions/{perm_type}', ctxt=self.endpoint,
                           params={'projectKey': self.key, 'ps': 100, 'p': page + 1})
            data = json.loads(resp.text)
            for p in data[perm_type]:
                perms.append(p)
        return perms

    def last_use(self, as_days=False):
        if self.last_used is None:
            return None
        if not as_days:
            return self.last_used
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        return abs(today - self.last_used).days

    def last_update(self, as_days=False):
        if self.last_updated is None:
            return None
        if not as_days:
            return self.last_updated
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        return abs(today - self.last_updated).days

    def is_child(self):
        return self.parent_key is not None

    def inherits_from_built_in(self):
        return self.get_built_in_parent() is not None

    def get_built_in_parent(self):
        if self.is_built_in:
            return self
        parent = self.parent_name
        if parent is None:
            return None
        parent_qp = search(self.endpoint, {'language': self.language, 'qualityProfile': parent})[0]
        return parent_qp.get_built_in_parent()

    def has_deprecated_rules(self):
        return self.nbr_deprecated_rules > 0

    def audit(self, audit_settings=None):
        util.logger.debug("Auditing %s", str(self))
        if self.is_built_in:
            util.logger.info("%s is built-in, skipping audit", str(self))
            return []

        util.logger.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = []
        age = self.last_update(as_days=True)
        if age > audit_settings['audit.qualityProfiles.maxLastChangeAge']:
            rule = arules.get_rule(arules.RuleId.QP_LAST_CHANGE_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg))

        total_rules = rules.count(endpoint=self.endpoint, params={'languages': self.language})
        if self.nbr_rules < int(total_rules * audit_settings['audit.qualityProfiles.minNumberOfRules']):
            rule = arules.get_rule(arules.RuleId.QP_TOO_FEW_RULES)
            msg = rule.msg.format(str(self), self.nbr_rules, total_rules)
            problems.append(pb.Problem(rule.type, rule.severity, msg))

        age = self.last_use(as_days=True)
        if self.project_count == 0 or age is None:
            rule = arules.get_rule(arules.RuleId.QP_NOT_USED)
            msg = rule.msg.format(str(self))
            problems.append(pb.Problem(rule.type, rule.severity, msg))
        elif age > audit_settings['audit.qualityProfiles.maxUnusedAge']:
            rule = arules.get_rule(arules.RuleId.QP_LAST_USED_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg))
        if audit_settings['audit.qualityProfiles.checkDeprecatedRules']:
            max_deprecated_rules = 0
            parent_qp = self.get_built_in_parent()
            if parent_qp is not None:
                max_deprecated_rules = parent_qp.nbr_deprecated_rules
            if self.nbr_deprecated_rules > max_deprecated_rules:
                rule = arules.get_rule(arules.RuleId.QP_USE_DEPRECATED_RULES)
                msg = rule.msg.format(str(self), self.nbr_deprecated_rules)
                problems.append(pb.Problem(rule.type, rule.severity, msg))

        return problems


def search(endpoint=None, params=None):
    resp = env.get('qualityprofiles/search', ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    qp_list = []
    for qp in data['profiles']:
        qp_list.append(QualityProfile(qp['key'], endpoint=endpoint, data=qp))
    return qp_list


def audit(endpoint=None, audit_settings=None):
    util.logger.info("--- Auditing quality profiles ---")
    problems = []
    langs = {}
    for qp in search(endpoint):
        problems += qp.audit(audit_settings)
        langs[qp.language] = langs.get(qp.language, 0) + 1
    for lang, nb_qp in langs.items():
        if nb_qp > 5:
            rule = arules.get_rule(arules.RuleId.QP_TOO_MANY_QP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(nb_qp, lang, 5)))
    return problems
