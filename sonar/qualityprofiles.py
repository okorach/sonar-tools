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
from sonar import rules, permissions
import sonar.sqobject as sq
import sonar.utilities as util

import sonar.audit.rules as arules
import sonar.audit.problem as pb

_CREATE_API = "qualityprofiles/create"
_SEARCH_API = "qualityprofiles/search"
_DETAILS_API = "qualityprofiles/show"
_SEARCH_FIELD = "profiles"
_QUALITY_PROFILES = {}
_MAP = {}

_KEY_PARENT = "parent"
_CHILDREN_KEY = "children"

class QualityProfile(sq.SqObject):
    def __init__(self, name, endpoint, language=None, data=None, create_data=None):
        super().__init__(name, endpoint)
        self.name = data["name"] if data is not None else name
        self.language = data["name"] if data is not None else language
        self._rules = None
        self._permissions = None
        self.is_built_in = None
        self.is_default = None
        self.language_name = None
        self.parent_name = None
        if create_data is not None:
            util.logger.info("Creating %s", str(self))
            util.logger.debug("from %s", util.json_dump(create_data))
            self.post(_CREATE_API, params={"name": self.name, "language": self.language})
            self.is_built_in = False
            self.set_permissions(create_data.pop("permissions", None))
            self.set_parent(create_data.pop(_KEY_PARENT, None))
            data = search_by_name(endpoint, name, language)
            self.key = data["key"]
            self.set_rules(create_data.pop("rules", None))
        elif data is None:
            util.logger.info("Creating %s", str(self))
            self.key = name_to_uuid(name, language)
            data = json.loads(self.get(_DETAILS_API, params={"key": self.key}).text)
            util.logger.debug("from sonar details data %s", util.json_dump(data))
        else:
            util.logger.debug("from sonar list data %s", util.json_dump(data))
        self._json = data
        self.name = data["name"]
        self.language_name = data["languageName"]
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
        self._rules = self.rules()
        self._projects = None
        self._permissions = self.permissions()
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])
        self.parent_name = data.get("parentName", None)
        _MAP[_format(self.name, self.language)] = self.key
        _QUALITY_PROFILES[self.key] = self

    def uuid(self):
        return _uuid(self.key)

    def __str__(self):
        return f"quality profile '{self.name}' of language '{self.language}'"

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

    def set_parent(self, parent_name):
        if parent_name is None:
            return
        if get_object(parent_name, self.language) is None:
            util.logger.warning("Can't set parent name '%s' to %s", str(parent_name), str(self))
            return
        if self.parent_name is None or self.parent_name != parent_name:
            params = {"qualityProfile": self.name, "language": self.language, "parentQualityProfile": parent_name}
            self.post("qualityprofiles/change_parent", params=params)
        else:
            util.logger.info("Won't set parent of %s. It's the same as currently", str(self))

    def is_child(self):
        return self.parent_name is not None

    def inherits_from_built_in(self):
        return self.get_built_in_parent() is not None

    def get_built_in_parent(self):
        if self.is_built_in:
            return self
        if self.parent_name is None:
            return None
        parent_qp = get_object(self.endpoint, self.parent_name, self.language)
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

    def set_rules(self, ruleset):
        if ruleset is None or len(ruleset) == 0:
            return
        params = {"key": self.key}
        for r_key, r_data in ruleset.items():
            params.update({"rule": r_key, "severity": r_data.get("severity", None)})
            params.pop("params", None)
            if "params" in r_data:
                params["params"] = ";".join([f"{k}={v}" for k, v in r_data["params"].items()])
            r = self.post("qualityprofiles/activate_rule", params=params, exit_on_error=False)
            if r.status_code == 404:
                util.logger.error("Rule %s not found, can't activate it in %s", r_key, str(self))
            elif r.status_code == 400:
                util.logger.error("HTTP error 400 while trying to activate rule %s in %s", r_key, str(self))
            elif r.status_code // 100 != 2:
                util.log_and_exit(r.status_code)

    def update(self, data):
        util.logger.debug("Updating %s with %s", str(self), util.json_dump(data))
        if self.is_built_in:
            util.logger.info("Not updating built-in %s", str(self))
        else:
            if "name" in data and data["name"] != self.name:
                util.logger.info("Renaming %s with %s", str(self), data["name"])
                self.post("qualitygates/rename", params={"id": self.key, "name": data["name"]})
                _MAP.pop(_format(self.name, self.language), None)
                self.name = data["name"]
                _MAP[_format(self.name, self.language)] = self
            self.set_rules(data.get("rules", []))
            self.set_permissions(data.get("permissions", []))
            self.set_parent(data.pop(_KEY_PARENT, None))
            self.is_built_in = data.get("isBuiltIn", False)
            self.is_default = data.get("isDefault", False)

        _create_or_update_children(name=self.name, language=self.language, endpoint=self.endpoint, children=data.get(_CHILDREN_KEY, {}))
        return self

    def to_json(self, full_specs=False, include_rules=False):
        json_data = {"name": self.name, "language": self.language}
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
        json_data["parentName"] = self.parent_name
        if include_rules:
            json_data["rules"] = self.rules(full_specs=full_specs)

        perms = util.remove_nones(self.permissions())
        if perms is not None and len(perms) > 0:
            for t in ("users", "groups"):
                if t in perms:
                    perms[t] = util.list_to_csv(perms[t], ", ", True)
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
        if self.endpoint.version() < (8, 9, 0):
            return None
        if self._permissions is not None:
            return self._permissions
        self._permissions = {}
        self._permissions["users"] = permissions.get_qp(self.endpoint, self.name, self.language, "users", "login")
        self._permissions["groups"] = permissions.get_qp(self.endpoint, self.name, self.language, "groups", "name")
        return self._permissions

    def set_permissions(self, perms):
        if perms is None or len(perms) == 0:
            return
        params = {"qualityProfile": self.name, "language": self.language}
        if "users" in perms:
            for u in util.csv_to_list(perms["users"]):
                params["login"] = u
                self.post("qualityprofiles/add_user", params=params)
            params.pop("login")
        if "groups" in perms:
            for g in util.csv_to_list(perms["groups"]):
                params["group"] = g
                self.post("qualityprofiles/add_group", params=params)
        self._permissions = self.permissions()

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


def search(endpoint, params=None):
    return sq.search_objects(
        endpoint=endpoint, api=_SEARCH_API, params=params, key_field="key", returned_field=_SEARCH_FIELD, object_class=QualityProfile
    )


def get_list(endpoint=None):
    if endpoint is not None and len(_QUALITY_PROFILES) == 0:
        search(endpoint=endpoint)
    return _QUALITY_PROFILES


def search_by_name(endpoint, name, language):
    return util.search_by_name(endpoint, name, _SEARCH_API, _SEARCH_FIELD, extra_params={"language": language})


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
            if _CHILDREN_KEY not in qp_list[lang][qp_value["parentName"]]:
                qp_list[lang][qp_value["parentName"]][_CHILDREN_KEY] = {}
            if strip_rules:
                parent_qp = get_object(qp_value["parentName"], lang)
                this_qp = get_object(qp_name, lang)
                qp_value["rules"] = this_qp.diff(parent_qp)
            qp_list[lang][qp_value["parentName"]][_CHILDREN_KEY][qp_name] = qp_value
            qp_list[lang].pop(qp_name)
            qp_value.pop("parentName")
    return qp_list


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


def get_object(name, language, endpoint=None):
    if len(_QUALITY_PROFILES) == 0:
        get_list(endpoint)
    fmt = _format(name, language)
    if fmt not in _MAP:
        return None
    return _QUALITY_PROFILES[_MAP[fmt]]


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


def create(name, language, endpoint=None, create_data=None):
    o = get_object(name=name, language=language, endpoint=endpoint)
    if o is None:
        o = QualityProfile(name=name, language=language, endpoint=endpoint, create_data=create_data)
    else:
        util.logger.info("%s already exist, creation skipped", str(o))
    return o


def _create_or_update_children(name, language, endpoint, children):
    for qp_name, qp_data in children.items():
        qp_data[_KEY_PARENT] = name
        util.logger.debug("Updating child '%s' with %s", qp_name, util.json_dump(qp_data))
        create_or_update(endpoint, qp_name, language, qp_data)


def create_or_update(endpoint, name, language, qp_data):
    o = get_object(endpoint=endpoint, name=name, language=language)
    if o is None:
        util.logger.debug("Quality profile '%s' does not exist, creating...", name)
        create(name=name, language=language, endpoint=endpoint, create_data=qp_data)
        _create_or_update_children(name=name, language=language, endpoint=endpoint, children=qp_data.get(_CHILDREN_KEY, {}))
    else:
        o.update(qp_data)


def import_config(endpoint, config_data):
    if "qualityProfiles" not in config_data:
        util.logger.info("No quality profiles to import")
        return
    util.logger.info("Importing quality profiles")
    get_list(endpoint=endpoint)
    for lang, lang_data in config_data["qualityProfiles"].items():
        for name, qp_data in lang_data.items():
            util.logger.info("Importing quality profile '%s' of language '%s'", name, lang)
            create_or_update(endpoint, name, lang, qp_data)


def _format(name, lang):
    return f"{lang}:{name}"


def name_to_uuid(name, lang):
    return _MAP.get(_format(name, lang), None)


def _uuid(key):
    return key
