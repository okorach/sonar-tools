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
"""

    Abstraction of the SonarQube "quality profile" concept

"""
import datetime
import json
import pytz
from sonar import env, rules, permissions
import sonar.sqobject as sq
import sonar.utilities as util

import sonar.audit.rules as arules
import sonar.audit.problem as pb

_QUALITY_PROFILES = {}
_NAME_MAP = {}


class QualityProfile(sq.SqObject):
    def __init__(self, key, endpoint, data=None):
        super().__init__(key, endpoint)
        if data is None:
            data = json.loads(self.get("qualityprofiles/show", params={"key": key}).text)
        self._json = data
        self.name = data["name"]
        if "lastUsed" in data:
            self.last_used = util.string_to_date(data["lastUsed"])
        else:
            self.last_used = None
        self.last_updated = util.string_to_date(data["rulesUpdatedAt"])
        self.language = data["language"]
        self.language_name = data["languageName"]
        self.is_default = data["isDefault"]
        self.project_count = data.get("projectCount", None)
        self.is_built_in = data["isBuiltIn"]
        self.nbr_rules = int(data["activeRuleCount"])
        self._rules = None
        self._projects = None
        self._permissions = None
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])
        self.parent_key = data.get("parentKey", None)
        self.parent_name = data.get("parentName", None)
        _NAME_MAP[f"{self.language}:{self.name}"] = self.uuid()
        _QUALITY_PROFILES[self.uuid()] = self

    def uuid(self):
        return _uuid(self.key)

    def __str__(self):
        return f"quality profile '{self.name}' of language '{self.language_name}'"

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
        parent_qp = search(self.endpoint, {"language": self.language, "qualityProfile": parent})[0]
        return parent_qp.get_built_in_parent()

    def has_deprecated_rules(self):
        return self.nbr_deprecated_rules > 0

    def rules(self, full_specs=False):
        if self._rules is not None:
            # Assume nobody changed QP during execution
            return self._rules
        self._rules = {}
        page, nb_pages = 1, 1
        params = {"activation": "true", "qprofile": self.key, "s": "key", "ps": 500}
        while page <= nb_pages:
            params["p"] = page
            data = json.loads(self.get("rules/search", params=params).text)
            if full_specs:
                self._rules += data["rules"]
            else:
                for r in data["rules"]:
                    self._rules[r["key"]] = _convert_rule(r, self.language, full_specs)
            nb_pages = util.nbr_pages(data)
            page += 1
        return self._rules

    def to_json(self, full_specs=False, include_rules=False):
        json_data = {
            "name": self.name,
            "language": self.language,
        }
        if full_specs:
            json_data.update(
                {
                    "key": self.key,
                    "lastUpdated": self.last_updated,
                    "isDefault": self.is_default,
                    "isBuiltIn": self.is_built_in,
                    "rulesCount": self.nbr_rules,
                    "projectsCount": self.project_count,
                    "deprecatedRulesCount": self.nbr_deprecated_rules,
                    "lastUsed": self.last_used,
                    "languageName": self.language_name,
                }
            )
        if self.parent_key is not None:
            json_data["parentName"] = self.parent_name
            if full_specs:
                json_data["parentKey"] = self.parent_key
        if include_rules:
            json_data["rules"] = self.rules(full_specs=full_specs)

        perms = util.remove_nones(self.permissions())
        if perms is not None and len(perms) > 0:
            json_data["permissions"] = perms

        return util.remove_nones(json_data)

    def compare(self, another_qp):
        params = {"leftKey": self.key, "rightKey": another_qp.key}
        data = json.loads(self.get("qualityprofiles/compare", params=params).text)
        for r in data["inLeft"] + data["same"] + data["inRight"] + data["modified"]:
            for k in ("name", "pluginKey", "pluginName", "languageKey", "languageName"):
                r.pop(k, None)
        return data

    def diff(self, another_qp):
        comp = self.compare(another_qp)
        diff_rules = {}
        util.json_dump_debug(comp, "Comparing 2 QP ")
        for r in comp["inLeft"]:
            diff_rules[r["key"]] = r
            r.pop("key")
        for r in comp["modified"]:
            diff_rules[r["key"]] = {"modified": True}
            if r["left"]["severity"] != r["right"]["severity"]:
                diff_rules[r["key"]]["severity"] = r["left"]["severity"]
            if "params" in r["left"] and len(r["left"]["params"]) > 0:
                diff_rules[r["key"]]["params"] = r["left"]["params"]
        return diff_rules

    def projects(self):
        if self._projects is not None:
            # Assume nobody changed QP during execution
            return self._projects
        self._projects = []
        params = {"key": self.key, "ps": 500}
        page = 1
        more = True
        while more:
            params["p"] = page
            data = json.loads(self.get("qualityprofiles/projects", params=params).text)
            self._projects += data["results"]
            more = data["more"]
            page += 1
        return self._projects

    def selected_for_project(self, key):
        for p in self.projects():
            if key == p["key"]:
                return True
        return False

    def permissions(self):
        if self.endpoint.version() < (9, 2, 0):
            return None
        if self._permissions is not None:
            return self._permissions
        self._permissions = {}
        self._permissions["users"] = permissions.get_qp(self.endpoint, self.name, self.language, "users", "login")
        self._permissions["groups"] = permissions.get_qp(self.endpoint, self.name, self.language, "groups", "name")
        return self._permissions

    def audit(self, audit_settings=None):
        util.logger.debug("Auditing %s", str(self))
        if self.is_built_in:
            util.logger.info("%s is built-in, skipping audit", str(self))
            return []

        util.logger.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = []
        age = self.last_update(as_days=True)
        if age > audit_settings["audit.qualityProfiles.maxLastChangeAge"]:
            rule = arules.get_rule(arules.RuleId.QP_LAST_CHANGE_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg))

        total_rules = rules.count(endpoint=self.endpoint, params={"languages": self.language})
        if self.nbr_rules < int(total_rules * audit_settings["audit.qualityProfiles.minNumberOfRules"]):
            rule = arules.get_rule(arules.RuleId.QP_TOO_FEW_RULES)
            msg = rule.msg.format(str(self), self.nbr_rules, total_rules)
            problems.append(pb.Problem(rule.type, rule.severity, msg))

        age = self.last_use(as_days=True)
        if self.project_count == 0 or age is None:
            rule = arules.get_rule(arules.RuleId.QP_NOT_USED)
            msg = rule.msg.format(str(self))
            problems.append(pb.Problem(rule.type, rule.severity, msg))
        elif age > audit_settings["audit.qualityProfiles.maxUnusedAge"]:
            rule = arules.get_rule(arules.RuleId.QP_LAST_USED_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg))
        if audit_settings["audit.qualityProfiles.checkDeprecatedRules"]:
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
    resp = env.get("qualityprofiles/search", ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    qp_list = []
    for qp in data["profiles"]:
        qp_list.append(QualityProfile(qp["key"], endpoint=endpoint, data=qp))
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


def hierarchize(qp_list, strip_rules=True):
    """Organize a flat list of QP in hierarchical (inheritance) fashion"""
    for lang, qpl in qp_list.copy().items():
        for qp_name, qp_value in qpl.copy().items():
            if "parentName" not in qp_value:
                continue
            util.logger.debug("QP name %s has parent %s", qp_name, qp_value["parentName"])
            if "childrens" not in qp_list[lang][qp_value["parentName"]]:
                qp_list[lang][qp_value["parentName"]]["childrens"] = {}
            if strip_rules:
                parent_qp = get_object(key=name_to_uuid(qp_value["parentName"], lang))
                this_qp = get_object(key=name_to_uuid(qp_name, lang))
                qp_value["rules"] = this_qp.diff(parent_qp)
            qp_list[lang][qp_value["parentName"]]["childrens"][qp_name] = qp_value
            qp_list[lang].pop(qp_name)
            qp_value.pop("parentName")
    return qp_list


def get_list(endpoint=None):
    if endpoint is not None and len(_QUALITY_PROFILES) == 0:
        search(endpoint=endpoint)
    return _QUALITY_PROFILES


def export(endpoint, in_hierarchy=True):
    util.logger.info("Exporting quality profiles")
    qp_list = {}
    for qp in get_list(endpoint=endpoint).values():
        util.logger.info("Exporting %s", str(qp))
        json_data = qp.to_json(include_rules=True)
        lang = json_data.pop("language")
        name = json_data.pop("name")
        if lang not in qp_list:
            qp_list[lang] = {}
        qp_list[lang][name] = json_data
    if in_hierarchy:
        qp_list = hierarchize(qp_list)
    return qp_list


def get_object(key=None, name=None, lang=None, data=None, endpoint=None):
    if key is None:
        key = name_to_uuid(name, lang)
    if key not in _QUALITY_PROFILES:
        _ = QualityProfile(key=key, data=data, endpoint=endpoint)
    return _QUALITY_PROFILES[key]


def _convert_rule(rule, qp_lang, full_specs=False):
    d = {"severity": rule["severity"]}
    if len(rule["params"]) > 0:
        if not full_specs:
            d["params"] = {}
            for p in rule["params"]:
                d["params"][p["key"]] = p.get("defaultValue", "")
        else:
            d["params"] = rule["params"]
    if "templateKey" in rule:
        d["templateKey"] = rule["templateKey"]
    if rule["isTemplate"]:
        d["isTemplate"] = True
    if rule["lang"] != qp_lang:
        d["language"] = rule["lang"]
    return d


def _format(name, lang):
    return f"{lang}:{name}"


def name_to_uuid(name, lang):
    return _NAME_MAP.get(_format(name, lang), None)


def _uuid(key):
    return key
