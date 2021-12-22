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

    Abstraction of the SonarQube "quality profile" concept

'''
import datetime
import json
import pytz
import sonarqube.sqobject as sq
import sonarqube.env as env
import sonarqube.rules as rules
import sonarqube.utilities as util
import sonarqube.audit_rules as arules
import sonarqube.audit_problem as pb


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
            self._is_built_in = data['isBuiltIn']
            self.nb_rules = int(data['activeRuleCount'])
            self._nbr_deprecated_rules = int(data['activeDeprecatedRuleCount'])
            self._parent_key = data.get('parentKey', None)
            self._parent_name = data.get('parentName', None)

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

    def last_used_date(self):
        return self.last_used

    def last_updated_date(self):
        return self.last_updated

    def number_associated_projects(self):
        return 0

    def age_of_last_use(self):
        if self.last_used is None:
            return None
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        return abs(today - self.last_used).days

    def age_of_last_update(self):
        if self.last_updated is None:
            return None
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        return abs(today - self.last_updated).days

    def parent_key(self):
        return self._parent_key

    def parent_name(self):
        return self._parent_name

    def is_child(self):
        return self.parent_key() is not None

    def is_built_in(self):
        return self._is_built_in

    def inherits_from_built_in(self):
        return self.get_built_in_parent() is not None

    def get_built_in_parent(self):
        if self.is_built_in():
            return self
        parent = self.parent_name()
        if parent is None:
            return None
        parent_qp = search(self.endpoint, {'language': self.language, 'qualityProfile': self.parent_name()})[0]
        return parent_qp.get_built_in_parent()

    def has_deprecated_rules(self):
        return self.nbr_of_deprecated_rules() > 0

    def nbr_of_deprecated_rules(self):
        return self._nbr_deprecated_rules

    def audit(self, audit_settings=None):
        util.logger.debug("Auditing %s", str(self))
        if self.is_built_in():
            util.logger.debug("%s is built-in, skipping audit", str(self))
            return []

        util.logger.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = []
        age = self.age_of_last_update()
        if age > audit_settings['audit.qualityProfiles.maxLastChangeAge']:
            rule = arules.get_rule(arules.RuleId.QP_LAST_CHANGE_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg))

        total_rules = rules.count(endpoint=self.endpoint, params={'languages': self.language})
        if self.nb_rules < int(total_rules * audit_settings['audit.qualityProfiles.minNumberOfRules']):
            rule = arules.get_rule(arules.RuleId.QP_TOO_FEW_RULES)
            msg = rule.msg.format(str(self), self.nb_rules, total_rules)
            problems.append(pb.Problem(rule.type, rule.severity, msg))

        age = self.age_of_last_use()
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
                max_deprecated_rules = parent_qp.nbr_of_deprecated_rules()
            if self.nbr_of_deprecated_rules() > max_deprecated_rules:
                rule = arules.get_rule(arules.RuleId.QP_USE_DEPRECATED_RULES)
                msg = rule.msg.format(str(self), self._nbr_deprecated_rules)
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
