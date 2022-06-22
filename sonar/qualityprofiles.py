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
from http import HTTPStatus
import pytz
from sonar import rules, permissions, languages
import sonar.sqobject as sq
import sonar.utilities as util

import sonar.audit.rules as arules
import sonar.audit.problem as pb

_CREATE_API = "qualityprofiles/create"
_SEARCH_API = "qualityprofiles/search"
_DETAILS_API = "qualityprofiles/show"
_SEARCH_FIELD = "profiles"
_OBJECTS = {}
_MAP = {}

_KEY_PARENT = "parent"
_CHILDREN_KEY = "children"


class QualityProfile(sq.SqObject):
    @classmethod
    def read(cls, name, language, endpoint):
        if not languages.exists(endpoint=endpoint, language=language):
            util.logger.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        util.logger.debug("Reading quality profile '%s'  of language '%s'", name, language)
        key = name_to_key(name, language)
        if key in _OBJECTS:
            return _OBJECTS[key]
        data = search_by_name(endpoint=endpoint, name=name, language=language)
        return cls(key=data["key"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, name, language, endpoint, **kwargs):
        if not languages.exists(endpoint=endpoint, language=language):
            util.logger.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        params = {"name": name, "language": language}
        util.logger.debug("Creating quality profile '%s' of language '%s'", name, language)
        r = endpoint.post(_CREATE_API, params=params)
        if not r.ok:
            return None
        o = cls.read(name=name, language=language, endpoint=endpoint)
        return o

    @classmethod
    def load(cls, name, language, endpoint, data):
        util.logger.debug("Loading quality profile '%s' of language '%s'", name, language)
        key = data["key"]  # name_to_key(name, language)
        o = cls(key=key, endpoint=endpoint, data=data)
        return o

    def __init__(self, key, endpoint, data=None):
        super().__init__(key, endpoint)

        self._json = data
        self._permissions = None
        self._rules = None
        self.last_used = None
        self.last_updated = None
        self.name = data["name"]
        self.language = data["language"]
        self.is_default = data["isDefault"]
        self.is_built_in = data["isBuiltIn"]

        self._rules = self.rules()
        self.nbr_rules = int(data["activeRuleCount"])
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])

        self._projects = None
        self.project_count = data.get("projectCount", None)
        self.parent_name = data.get("parentName", None)
        self.language_name = data["languageName"]
        self.last_used = util.string_to_date(data.get("lastUsed", None))
        self.last_updated = util.string_to_date(data.get("rulesUpdatedAt", None))

        util.logger.info("Created %s", str(self))
        _MAP[_format(self.name, self.language)] = self.key
        _OBJECTS[self.key] = self

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
        if get_object(name=parent_name, language=self.language) is None:
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
        self.is_built_in = self._json.get("isBuiltIn", False)
        if self.is_built_in:
            return self
        if self.parent_name is None:
            return None
        parent_qp = get_object(endpoint=self.endpoint, name=self.parent_name, language=self.language)
        return parent_qp.get_built_in_parent()

    def has_deprecated_rules(self):
        return self.nbr_deprecated_rules > 0

    def rules(self, full_specs=False):
        if self._rules is not None:
            # Assume nobody changed QP during execution
            return self._rules
        self._rules = {}
        page, nb_pages = 1, 1
        # TODO: Filter on QP key for speed
        params = {"activation": "true", "qprofile": self.key, "s": "key", "languages": self.language, "ps": 500}
        while page <= nb_pages:
            params["p"] = page
            data = json.loads(self.get("rules/search", params=params).text)
            if full_specs:
                self._rules += data["rules"]
            else:
                for r in data["rules"]:
                    if "templateKey" in r:
                        r.pop("params")
                    r.pop("tags", None)
                    r.pop("mdNote", None)
                    self._rules[r["key"]] = rules.convert_for_export(r, self.language, with_template_key=False, full_specs=full_specs)
            nb_pages = util.nbr_pages(data)
            page += 1
        return self._rules

    def set_rules(self, ruleset):
        if ruleset is None or len(ruleset) == 0:
            return
        params = {"key": self.key}
        for r_key, r_data in ruleset.items():
            if isinstance(r_data, str):
                params.update({"rule": r_key, "severity": r_data})
            else:
                params.update({"rule": r_key, "severity": r_data.get("severity", None)})
            params.pop("params", None)
            if "params" in r_data:
                params["params"] = ";".join([f"{k}={v}" for k, v in r_data["params"].items()])
            r = self.post("qualityprofiles/activate_rule", params=params, exit_on_error=False)
            if r.status_code == HTTPStatus.NOT_FOUND:
                util.logger.error("Rule %s not found, can't activate it in %s", r_key, str(self))
            elif r.status_code == HTTPStatus.BAD_REQUEST:
                util.logger.error("HTTP error %d while trying to activate rule %s in %s", r.status_code, r_key, str(self))
            elif not r.ok:
                util.log_and_exit(r)

    def update(self, data):
        if self.is_built_in:
            util.logger.debug("Not updating built-in %s", str(self))
        else:
            util.logger.debug("Updating %s with %s", str(self), str(data))
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
        json_data = {"name": self.name, "language": self.language, "parentName": self.parent_name}
        if self.is_built_in:
            json_data["isBuiltIn"] = True
            include_rules = False
        if self.is_default:
            json_data["isDefault"] = True
        if full_specs:
            json_data.update(
                {
                    "key": self.key,
                    "lastUpdated": self.last_updated,
                    "rulesCount": self.nbr_rules,
                    "projectsCount": self.project_count,
                    "deprecatedRulesCount": self.nbr_deprecated_rules,
                    "lastUsed": self.last_used,
                    "languageName": self.language_name,
                }
            )
        if include_rules:
            json_data["rules"] = self.rules(full_specs=full_specs)
        json_data["permissions"] = self.permissions().export()
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
        my_rules = self.rules()
        diff_rules = {}
        util.json_dump_debug(comp, "Comparing 2 QP ")
        for r in comp["inLeft"]:
            r_key = r.pop("key")
            diff_rules[r_key] = my_rules.get(r_key, r)
            if "severity" in r:
                if isinstance(diff_rules[r_key], str):
                    diff_rules[r_key] = r["severity"]
                else:
                    diff_rules[r_key]["severity"] = r["severity"]
        for r in comp["modified"]:
            r_key = r["key"]
            diff_rules[r_key] = {"modified": True}
            parms = None
            if r["left"]["severity"] != r["right"]["severity"]:
                diff_rules[r_key]["severity"] = r["left"]["severity"]
            if "params" in r["left"] and len(r["left"]["params"]) > 0:
                diff_rules[r_key]["params"] = r["left"]["params"]
                parms = r["left"]["params"]
            if "templateKey" in my_rules.get(r["key"], {}):
                diff_rules[r_key]["templateKey"] = my_rules[r_key]["templateKey"]
                diff_rules[r_key]["params"] = my_rules[r_key]["params"]
                if parms is not None:
                    diff_rules[r_key]["params"].update(parms)
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
            self._projects += [p["key"] for p in data["results"]]
            more = data["more"]
            page += 1
        util.logger.debug("Projects for %s = '%s'", str(self), ", ".join(self._projects))
        return self._projects

    def selected_for_project(self, key):
        for project_key in self.projects():
            if key == project_key:
                return True
        return False

    def permissions(self):
        if self._permissions is None:
            self._permissions = permissions.QualityProfilePermissions(self)
        return self._permissions

    def set_permissions(self, perms):
        self.permissions().set(perms)

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
    if endpoint is not None and len(_OBJECTS) == 0:
        search(endpoint=endpoint)
    return _OBJECTS


def search_by_name(endpoint, name, language):
    return util.search_by_name(endpoint, name, _SEARCH_API, _SEARCH_FIELD, extra_params={"language": language})


def audit(endpoint=None, audit_settings=None):
    util.logger.info("--- Auditing quality profiles ---")
    get_list(endpoint=endpoint)
    problems = []
    langs = {}
    for qp in search(endpoint).values():
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
                this_qp = get_object(name=qp_name, language=lang)
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
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    fmt = _format(name, language)
    if fmt not in _MAP:
        return None
    return _OBJECTS[_MAP[fmt]]


def _create_or_update_children(name, language, endpoint, children):
    for qp_name, qp_data in children.items():
        qp_data[_KEY_PARENT] = name
        util.logger.debug("Updating child '%s' with %s", qp_name, util.json_dump(qp_data))
        o = get_object(name=qp_name, language=language, endpoint=endpoint)
        if o is None:
            o = QualityProfile.create(name=qp_name, language=language, endpoint=endpoint)
        o.update(qp_data)


def import_config(endpoint, config_data):
    if "qualityProfiles" not in config_data:
        util.logger.info("No quality profiles to import")
        return
    util.logger.info("Importing quality profiles")
    get_list(endpoint=endpoint)
    for lang, lang_data in config_data["qualityProfiles"].items():
        for name, qp_data in lang_data.items():
            if not languages.exists(endpoint=endpoint, language=lang):
                util.logger.warning("Language '%s' does not exist, quality profile '%s' import skipped", lang, name)
                continue
            o = get_object(name=name, language=lang, endpoint=endpoint)
            if o is None:
                o = QualityProfile.create(name=name, language=lang, endpoint=endpoint)
            util.logger.info("Importing quality profile '%s' of language '%s'", name, lang)
            o.update(qp_data)


def _format(name, lang):
    return f"{lang}:{name}"


def name_to_key(name, lang):
    return _MAP.get(_format(name, lang), None)


def exists(language, name, endpoint):
    return get_object(name=name, language=language, endpoint=endpoint) is not None
