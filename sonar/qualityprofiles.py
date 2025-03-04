#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

"""Abstraction of the SonarQube Quality Profile concept"""
from __future__ import annotations
from typing import Optional
import json
from datetime import datetime
from http import HTTPStatus

from queue import Queue
from threading import Thread, Lock
from requests import RequestException
import requests.utils

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types, cache, constants as c
from sonar import exceptions
from sonar import rules, languages
import sonar.permissions.qualityprofile_permissions as permissions
import sonar.sqobject as sq
import sonar.utilities as util

from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem

_KEY_PARENT = "parent"
_CHILDREN_KEY = "children"

_IMPORTABLE_PROPERTIES = ("name", "language", "parentName", "isBuiltIn", "isDefault", "rules", "permissions")

_CLASS_LOCK = Lock()


class QualityProfile(sq.SqObject):
    """
    Abstraction of the SonarQube "quality profile" concept
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "profiles"
    API = {
        c.CREATE: "qualityprofiles/create",
        c.GET: "qualityprofiles/search",
        c.DELETE: "qualityprofiles/delete",
        c.LIST: "qualityprofiles/search",
        c.RENAME: "qualityprofiles/rename",
    }

    def __init__(self, endpoint: pf.Platform, key: str, data: types.ApiPayload = None) -> None:
        """Do not use, use class methods to create objects"""
        super().__init__(endpoint=endpoint, key=key)

        self.name = data["name"]  #: Quality profile name
        self.language = data["language"]  #: Quality profile language
        self.is_default = data["isDefault"]  #: Quality profile is default
        self.is_built_in = data["isBuiltIn"]  #: Quality profile is built-in - read-only
        self.sq_json = data
        self._permissions = None
        self._rules = None
        self.__last_use = None
        self.__last_update = None

        # self._rules = self.rules()
        self.nbr_rules = int(data["activeRuleCount"])  #: Number of rules in the quality profile
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])  #: Number of deprecated rules in the quality profile

        (self._projects, self._projects_lock) = (None, Lock())
        self.project_count = data.get("projectCount", None)  #: Number of projects using this quality profile
        self.parent_name = data.get("parentName", None)  #: Name of parent profile, or None if none

        self.__last_use = util.string_to_date(data.get("lastUsed", None))
        self.__last_update = util.string_to_date(data.get("rulesUpdatedAt", None))

        log.debug("Created %s", str(self))
        QualityProfile.CACHE.put(self)

    @classmethod
    def read(cls, endpoint: pf.Platform, name: str, language: str) -> Optional[QualityProfile]:
        """Creates a QualityProfile object corresponding to quality profile with same name and language in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality profile name
        :param str language: Quality profile language
        :return: The quality profile object
        :rtype: QualityProfile or None if not found
        """
        if not languages.exists(endpoint=endpoint, language=language):
            log.error("Language '%s' does not exist, quality profile creation aborted", language)
            return None
        log.debug("Reading quality profile '%s' of language '%s'", name, language)
        o = QualityProfile.CACHE.get(name, language, endpoint.url)
        if o:
            return o
        data = util.search_by_name(
            endpoint, name, QualityProfile.API[c.LIST], QualityProfile.SEARCH_RETURN_FIELD, extra_params={"language": language}
        )
        return cls(key=data["key"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, name: str, language: str) -> Optional[QualityProfile]:
        """Creates a new quality profile in SonarQube and returns the corresponding QualityProfile object

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality profile name
        :param str description: Quality profile language
        :return: The quality profile object
        :rtype: QualityProfile or None if creation failed
        """
        if not languages.exists(endpoint=endpoint, language=language):
            log.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        log.debug("Creating quality profile '%s' of language '%s'", name, language)
        try:
            endpoint.post(QualityProfile.API[c.CREATE], params={"name": name, "language": language})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating quality profile '{language}:{name}'", catch_http_errors=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(f"{language}:{name}", e.response.text)
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def clone(cls, endpoint: pf.Platform, name: str, language: str, original_qp_name: str) -> Optional[QualityProfile]:
        """Creates a new quality profile in SonarQube with rules copied from original_key

        :param endpoint: Reference to the SonarQube platform
        :param name: Quality profile name
        :param language: Quality profile language
        :param original_qp_name: Original quality profile name
        :return: The cloned quality profile object
        """
        log.info("Cloning quality profile name '%s' into quality profile name '%s'", original_qp_name, name)
        l = [qp for qp in get_list(endpoint, use_cache=False).values() if qp.name == original_qp_name and qp.language == language]
        if len(l) != 1:
            raise exceptions.ObjectNotFound(f"{language}:{original_qp_name}", f"Quality profile {language}:{original_qp_name} not found")
        original_qp = l[0]
        log.debug("Found QP to clone: %s", str(original_qp))
        try:
            endpoint.post("qualityprofiles/copy", params={"toName": name, "fromKey": original_qp.key})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"cloning {str(original_qp)} into name '{name}'", catch_http_errors=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(f"{language}:{name}", e.response.text)
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> None:
        """Creates a QualityProfile object from the result of a SonarQube API quality profile search data

        :param Platform endpoint: Reference to the SonarQube platform
        :param dict data: The JSON data corresponding to the quality profile
        :type data: dict
        :return: The quality profile object
        :rtype: QualityProfile
        """
        log.debug("Loading quality profile '%s' of language '%s'", data["name"], data["language"])
        return cls(endpoint=endpoint, key=data["key"], data=data)

    def __str__(self) -> str:
        """String formatting of the object"""
        return f"quality profile '{self.name}' of language '{self.language}'"

    def __hash__(self) -> int:
        return hash((self.name, self.language, self.endpoint.url))

    def url(self) -> str:
        """
        :return: the SonarQube permalink URL to the quality profile
        :rtype: str
        """
        return f"{self.endpoint.url}/profiles/show?language={self.language}&name={requests.utils.quote(self.name)}"

    def last_use(self) -> datetime:
        """
        :return: When the quality profile was last used
        :rtype: datetime or None if never
        """
        return self.__last_use

    def last_update(self) -> datetime:
        """
        :return: When the quality profile was last updated
        :rtype: datetime or None
        """
        return self.__last_update

    def set_parent(self, parent_name: str) -> bool:
        """Sets the parent quality profile of the current profile

        :param str parent_name: Name of the parent quality profile
        :return: Whether setting the parent was successful or not
        :rtype: bool
        """
        log.info("Setting parent %s to %s", str(parent_name), self.parent_name)
        if parent_name is None:
            return False
        if get_object(endpoint=self.endpoint, name=parent_name, language=self.language) is None:
            log.warning("Can't set parent name '%s' to %s, parent not found", str(parent_name), str(self))
            return False
        if parent_name == self.name:
            log.error("Can't set %s as parent of itself", str(self))
            return False
        elif self.parent_name is None or self.parent_name != parent_name:
            r = self.post("qualityprofiles/change_parent", params={**self.api_params(c.GET), "parentQualityProfile": parent_name})
            self.parent_name = parent_name
            self.rules(use_cache=False)
            return r.ok
        else:
            log.debug("Won't set parent of %s. It's the same as currently", str(self))
            return True

    def set_as_default(self) -> bool:
        """Sets the quality profile as the default for the language
        :return: Whether setting as default quality profile was successful
        :rtype: bool
        """
        r = self.post("qualityprofiles/set_default", params=self.api_params(c.GET))
        if r.ok:
            self.is_default = True
            # Turn off default for all other profiles except the current profile
            for qp in get_list(self.endpoint).values():
                if qp.language == self.language and qp.key != self.key:
                    qp.is_default = False
        return r.ok

    def is_child(self) -> bool:
        """
        :return: Whether the quality profile has a parent
        :rtype: bool
        """
        return self.parent_name is not None

    def inherits_from_built_in(self) -> bool:
        """
        :return: Whether the quality profile inherits from a built-in profile (following parents of parents)
        :rtype: bool
        """
        return self.built_in_parent() is not None

    def built_in_parent(self) -> Optional[QualityProfile]:
        """
        :return: The built-in parent profile of the profile, or None
        :rtype: QualityProfile or None if profile does not inherit from a built-in profile
        """
        self.is_built_in = self.sq_json.get("isBuiltIn", False)
        if self.is_built_in:
            return self
        if self.parent_name is None:
            return None
        return get_object(endpoint=self.endpoint, name=self.parent_name, language=self.language).built_in_parent()

    def rules(self, use_cache: bool = False) -> dict[str, rules.Rule]:
        """
        :return: The list of rules active in the quality profile
        :rtype: dict{<rule_key>: <rule_data>}
        """
        if self._rules is not None and use_cache:
            # Assume nobody changed QP during execution
            return self._rules
        rule_key_list = rules.search_keys(self.endpoint, activation="true", qprofile=self.key, s="key", languages=self.language)
        self._rules = {k: rules.get_object(self.endpoint, k) for k in rule_key_list}
        return self._rules

    def activate_rule(self, rule_key: str, severity: Optional[str] = None, **params) -> bool:
        """Activates a rule in the quality profile

        :param str rule_key: Rule key to activate
        :param str severity: Severity of the rule in the quality profiles, defaults to the rule default severity
        :param params: List of parameters associated to the rules, defaults to None
        :return: Whether the activation succeeded
        :rtype: bool
        """
        log.debug("Activating rule %s in %s", rule_key, str(self))
        api_params = {"key": self.key, "rule": rule_key, "severity": severity}
        if len(params) > 0:
            api_params["params"] = ";".join([f"{k}={v}" for k, v in params.items()])
        try:
            r = self.post("qualityprofiles/activate_rule", params=api_params)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"activating rule {rule_key} in {str(self)}", catch_all=True)
            return False
        if self._rules is None:
            self._rules = {}
        self._rules[rule_key] = rules.get_object(self.endpoint, rule_key)
        return r.ok

    def deactivate_rule(self, rule_key: str) -> bool:
        """Deactivates a rule in the quality profile

        :param str rule_key: Rule key to deactivate
        :return: Whether the deactivation succeeded
        :rtype: bool
        """
        log.debug("Deactivating rule %s in %s", rule_key, str(self))
        try:
            r = self.post("qualityprofiles/deactivate_rule", params={"key": self.key, "rule": rule_key})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"deactivating rule {rule_key} in {str(self)}", catch_all=True)
            return False
        return r.ok

    def deactivate_rules(self, ruleset: list[str]) -> bool:
        """Deactivates a list of rules in the quality profile
        :return: Whether the deactivation of all rules was successful
        :rtype: bool
        """
        ok = True
        for r_key in ruleset:
            ok = ok and self.deactivate_rule(rule_key=r_key)
        self.rules(use_cache=False)
        return ok

    def activate_rules(self, ruleset: dict[str, str]) -> bool:
        """Activates a list of rules in the quality profile
        :return: Whether the activation of all rules was successful
        :rtype: bool
        """
        ok = True
        for r_key, r_data in ruleset.items():
            sev = r_data if isinstance(r_data, str) else r_data.get("severity", None)
            if "params" in r_data:
                ok = ok and self.activate_rule(rule_key=r_key, severity=sev, **r_data["params"])
            else:
                ok = ok and self.activate_rule(rule_key=r_key, severity=sev)
        self.rules(use_cache=False)
        return ok

    def set_rules(self, ruleset: dict[str, str]) -> bool:
        """Sets the quality profile with a set of rules. If the quality profile current has rules
        not in the ruleset these rules are deactivated
        :return: Whether the quality profile was set with all the given rules
        :rtype: bool
        """
        if not ruleset:
            return False
        current_rules = list(self.rules(use_cache=False).keys())
        keys_to_activate = util.difference(list(ruleset.keys()), current_rules)
        rules_to_activate = {k: ruleset[k] for k in keys_to_activate}
        rules_to_deactivate = util.difference(current_rules, list(ruleset.keys()))
        log.info("set_rules: Activating %d rules and deactivating %d rules", len(rules_to_activate), len(rules_to_deactivate))
        ok = self.activate_rules(rules_to_activate)
        ok = ok and self.deactivate_rules(rules_to_deactivate)
        return ok

    def update(self, data: types.ObjectJsonRepr, queue: Queue) -> QualityProfile:
        """Updates a QP with data coming from sonar-config"""
        if self.is_built_in:
            log.debug("Not updating built-in %s", str(self))
        else:
            log.debug("Updating %s with %s", str(self), str(data))
            if "name" in data and data["name"] != self.name:
                log.info("Renaming %s with %s", str(self), data["name"])
                self.post(QualityProfile.API[c.RENAME], params={"id": self.key, "name": data["name"]})
                QualityProfile.CACHE.pop(self)
                self.name = data["name"]
                QualityProfile.CACHE.put(self)
            self.set_parent(data.pop(_KEY_PARENT, None))
            self.set_rules(data.get("rules", []))
            self.set_permissions(data.get("permissions", []))
            self.is_built_in = data.get("isBuiltIn", False)
            if data.get("isDefault", False):
                self.set_as_default()

        _create_or_update_children(name=self.name, language=self.language, endpoint=self.endpoint, children=data.get(_CHILDREN_KEY, {}), queue=queue)
        return self

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """
        :param full: If True, exports all properties, including those that can't be set
        :type full: bool
        :return: the quality profile properties as JSON dict
        :rtype: dict
        """
        json_data = self.sq_json.copy()
        json_data.update({"name": self.name, "language": self.language, "parentName": self.parent_name})
        full = export_settings.get("FULL_EXPORT", False)
        if not self.is_default:
            json_data.pop("isDefault", None)
        if not self.is_built_in:
            json_data.pop("isBuiltIn", None)
            json_data["rules"] = {k: v.export(full) for k, v in self.rules().items()}
        json_data["permissions"] = self.permissions().export(export_settings)
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def compare(self, another_qp: QualityProfile) -> dict[str, str]:
        """Compares 2 quality profiles rulesets
        :param another_qp: The second quality profile to compare with self
        :type another_qp: QualityProfile
        :return: dict result of the compare ("inLeft", "inRight", "same", "modified")
        :rtype: dict
        """
        data = json.loads(self.get("qualityprofiles/compare", params={"leftKey": self.key, "rightKey": another_qp.key}).text)
        for r in data["inLeft"] + data["same"] + data["inRight"] + data["modified"]:
            for k in ("name", "pluginKey", "pluginName", "languageKey", "languageName"):
                r.pop(k, None)
        return data

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        operations = {
            c.GET: {"qualityProfile": self.name, "language": self.language},
            c.LIST: {"q": self.name, "language": self.language},
            c.DELETE: {"qualityProfile": self.name, "language": self.language},
        }
        return operations[op] if op in operations else operations[c.GET]

    def _treat_added_rules(self, added_rules: dict[str:str], added_flag: bool = True) -> dict[str:str]:
        diff_rules = {}
        my_rules = self.rules()
        for r in added_rules:
            r_key = r.pop("key")
            diff_rules[r_key] = r
            if (added_flag and r_key in my_rules) or (not added_flag and r_key not in my_rules):
                rule_obj = rules.get_object(endpoint=self.endpoint, key=r_key)
                diff_rules[r_key] = rules.convert_for_export(rule_obj.to_json(), rule_obj.language)
            if "severity" in r:
                if isinstance(diff_rules[r_key], str):
                    diff_rules[r_key] = r["severity"]
                else:
                    diff_rules[r_key]["severity"] = r["severity"]
        return diff_rules

    def _treat_removed_rules(self, removed_rules: dict[str:str]) -> dict[str:str]:
        return self._treat_added_rules(removed_rules, added_flag=False)

    def _treat_modified_rules(self, modified_rules: dict[str:str]) -> dict[str:str]:
        diff_rules = {}
        my_rules = self.rules()
        for r in modified_rules:
            r_key, r_left, r_right = r["key"], r["left"], r["right"]
            diff_rules[r_key] = {}
            parms = None
            if r_left["severity"] != r_right["severity"]:
                diff_rules[r_key]["severity"] = r_left["severity"]
            if len(r_left.get("params", {})) > 0:
                diff_rules[r_key]["params"] = r_left["params"]
                parms = r_left["params"]
            if r_key not in my_rules:
                continue
            data = rules.convert_for_export(my_rules[r_key].to_json(), my_rules[r_key].language)
            if "templateKey" in data:
                diff_rules[r_key]["templateKey"] = data["templateKey"]
                diff_rules[r_key]["params"] = data["params"]
                if parms:
                    diff_rules[r_key]["params"].update(parms)
        return diff_rules

    def diff(self, another_qp: QualityProfile, qp_json_data: dict[str:str]) -> tuple[dict[str:str], dict[str:str]]:
        """Returns the list of rules added or modified in self compared to another_qp (for inheritance)
        :param another_qp: The second quality profile to diff
        :type another_qp: QualityProfile
        :return: dict result of the diff ("inLeft", "modified")
        :rtype: dict
        """
        log.debug("Comparing %s and %s", str(self), str(another_qp))
        compare_result = self.compare(another_qp)
        diff_rules = {"addedRules": {}, "modifiedRules": {}}
        if len(compare_result["inLeft"]) > 0:
            diff_rules["addedRules"] = self._treat_added_rules(compare_result["inLeft"])
        if len(compare_result["modified"]) > 0:
            diff_rules["modifiedRules"] = self._treat_modified_rules(compare_result["modified"])
        if len(compare_result["inRight"]) > 0:
            diff_rules["removedRules"] = self._treat_removed_rules(compare_result["inRight"])
        elif self.endpoint.version() >= (10, 3, 0):
            diff_rules["removedRules"] = {}

        log.debug("Returning QP diff %s", str(diff_rules))
        for index in ("addedRules", "modifiedRules", "removedRules"):
            if index not in diff_rules:
                continue
            if index not in qp_json_data:
                qp_json_data[index] = {}
            for k, v in diff_rules[index].items():
                qp_json_data[index][k] = v if isinstance(v, str) or "templateKey" not in v else v["severity"]

        return (diff_rules, qp_json_data)

    def projects(self) -> types.KeyList:
        """Returns the list of projects keys using this quality profile
        :return: List of projects using explicitly this QP
        :rtype: List[project_key]
        """

        with self._projects_lock:
            if self._projects is None:
                self._projects = []
                params = {"key": self.key, "ps": 500}
                page = 1
                more = True
                while more:
                    params["p"] = page
                    data = json.loads(self.get("qualityprofiles/projects", params=params).text)
                    log.debug("Got QP %s data = %s", self.key, str(data))
                    self._projects += [p["key"] for p in data["results"]]
                    page += 1
                    if self.endpoint.version() >= (10, 0, 0):
                        more = util.nbr_pages(data) >= page
                    else:
                        more = data["more"]

                log.debug("Projects for %s = '%s'", str(self), ", ".join(self._projects))
        return self._projects

    def used_by_project(self, project: object) -> bool:
        """
        :param Project project: The project
        :return: Whether the quality profile is used by the project
        :rtype: bool
        """
        return project.key in self.projects()

    def permissions(self) -> permissions.QualityProfilePermissions:
        """
        :return: The list of users and groups that can edit the quality profile
        :rtype: dict{"users": <users comma separated>, "groups": <groups comma separated>}
        """
        if self._permissions is None:
            self._permissions = permissions.QualityProfilePermissions(self)
        return self._permissions

    def set_permissions(self, perms: types.ObjectJsonRepr) -> None:
        """Sets the list of users and groups that can can edit the quality profile
        :params perms:
        :type perms: dict{"users": <users comma separated>, "groups": <groups comma separated>}
        :return: Nothing
        """
        self.permissions().set(perms)

    def audit(self, audit_settings: types.ConfigSettings = None) -> list[Problem]:
        """Audits a quality profile and return list of problems found

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        log.info("Auditing %s", str(self))
        if self.is_built_in:
            log.info("%s is built-in, skipping audit", str(self))
            return []

        log.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = []
        age = util.age(self.last_update(), rounded=True)
        if age > audit_settings.get("audit.qualityProfiles.maxLastChangeAge", 180):
            problems.append(Problem(get_rule(RuleId.QP_LAST_CHANGE_DATE), self, str(self), age))

        total_rules = rules.count(endpoint=self.endpoint, languages=self.language)
        if self.nbr_rules < int(total_rules * audit_settings.get("audit.qualityProfiles.minNumberOfRules", 0.5)):
            problems.append(Problem(get_rule(RuleId.QP_TOO_FEW_RULES), self, str(self), self.nbr_rules, total_rules))

        age = util.age(self.last_use(), rounded=True)
        if self.project_count == 0 or age is None:
            problems.append(Problem(get_rule(RuleId.QP_NOT_USED), self, str(self)))
        elif age > audit_settings.get("audit.qualityProfiles.maxUnusedAge", 60):
            rule = get_rule(RuleId.QP_LAST_USED_DATE)
            problems.append(Problem(rule, self, str(self), age))
        if audit_settings.get("audit.qualityProfiles.checkDeprecatedRules", True):
            max_deprecated_rules = 0
            parent_qp = self.built_in_parent()
            if parent_qp is not None:
                max_deprecated_rules = parent_qp.nbr_deprecated_rules
            if self.nbr_deprecated_rules > max_deprecated_rules:
                problems.append(Problem(get_rule(RuleId.QP_USE_DEPRECATED_RULES), self, str(self), self.nbr_deprecated_rules))
        return problems


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, QualityProfile]:
    """Searches projects in SonarQube

    param Platform endpoint: Reference to the SonarQube platform
    :param dict params: list of parameters to filter quality profiles to search
    :return: list of quality profiles
    :rtype: dict{key: QualityProfile}
    """
    return sq.search_objects(endpoint=endpoint, object_class=QualityProfile, params=params)


def get_list(endpoint: pf.Platform, use_cache: bool = True) -> dict[str, QualityProfile]:
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :return: the list of all quality profiles
    :rtype: dict{key: QualityProfile}
    """

    with _CLASS_LOCK:
        if len(QualityProfile.CACHE) == 0 or not use_cache:
            QualityProfile.CACHE.clear()
            search(endpoint=endpoint)
    return QualityProfile.CACHE.objects


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings = None, **kwargs) -> list[Problem]:
    """Audits all quality profiles and return list of problems found

    :param Platform endpoint: reference to the SonarQube platform
    :param dict audit_settings: Configuration of audit
    :return: list of problems found
    :rtype: list[Problem]
    """
    if not audit_settings.get("audit.qualityProfiles", True):
        log.info("Auditing quality profiles is disabled, audit skipped...")
        return []
    log.info("--- Auditing quality profiles ---")
    rules.get_list(endpoint=endpoint)
    problems = []
    langs = {}
    for qp in search(endpoint=endpoint).values():
        problems += qp.audit(audit_settings)
        langs[qp.language] = langs.get(qp.language, 0) + 1
    for lang, nb_qp in langs.items():
        if nb_qp > 5:
            rule = get_rule(RuleId.QP_TOO_MANY_QP)
            problems.append(Problem(rule, f"{endpoint.url}/profiles?language={lang}", nb_qp, lang, 5))
    if "write_q" in kwargs:
        kwargs["write_q"].put(problems)
    return problems


def hierarchize_language(qp_list: dict[str, str], endpoint: pf.Platform, language: str) -> types.ObjectJsonRepr:
    """Organizes a flat list of quality profiles in inheritance hierarchy"""
    log.debug("Organizing QP list %s in hierarchy", str(qp_list.keys()))
    hierarchy = qp_list.copy()
    to_remove = []
    for qp_name, qp_json_data in hierarchy.items():
        if "parentName" in qp_json_data:
            if qp_json_data["parentName"] not in hierarchy:
                log.critical("Can't find parent %s in quality profiles", qp_json_data["parentName"])
                continue
            parent_qp_name = qp_json_data.pop("parentName")
            parent_qp = hierarchy[parent_qp_name]
            if _CHILDREN_KEY not in parent_qp:
                parent_qp[_CHILDREN_KEY] = {}
            this_qp = get_object(endpoint=endpoint, name=qp_name, language=language)
            (_, diff_data) = this_qp.diff(get_object(endpoint=endpoint, name=parent_qp_name, language=language), qp_json_data)
            diff_data.pop("rules", None)
            parent_qp[_CHILDREN_KEY][qp_name] = diff_data
            to_remove.append(qp_name)
    for qp_name in to_remove:
        hierarchy.pop(qp_name)
    return hierarchy


def hierarchize(qp_list: types.ObjectJsonRepr, endpoint: pf.Platform) -> types.ObjectJsonRepr:
    """Organize a flat list of QP in hierarchical (inheritance) fashion

    :param qp_list: List of quality profiles
    :type qp_list: {<language>: {<qp_name>: <qd_data>}}
    :return: Same list with child profiles nested in their parent
    :rtype: {<language>: {<qp_name>: {"children": <qp_list>; <qp_data>}}}
    """
    log.info("Organizing quality profiles in hierarchy")
    hierarchy = {}
    for lang, lang_qp_list in qp_list.items():
        hierarchy[lang] = hierarchize_language(lang_qp_list, endpoint=endpoint, language=lang)
    return hierarchy


def flatten_language(language: str, qp_list: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Converts a hierarchical list of QP of a given language into a flat list"""
    flat_list = {}
    for qp_name, qp_data in qp_list.copy().items():
        if _CHILDREN_KEY in qp_data:
            children = flatten_language(language, qp_data[_CHILDREN_KEY])
            for child in children.values():
                if "parent" not in child:
                    child["parent"] = f"{language}:{qp_name}"
            qp_data.pop(_CHILDREN_KEY)
            flat_list.update(children)
        flat_list[f"{language}:{qp_name}"] = qp_data
    return flat_list


def flatten(qp_list: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Organize a hierarchical list of QP in a flat list"""
    flat_list = {}
    for lang, lang_qp_list in qp_list.items():
        flat_list.update(flatten_language(lang, lang_qp_list))
    return flat_list


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports all or a list of quality profiles configuration as dict

    :param ConfigSettings export_settings: Export parameters
    :return: Dict of quality profiles JSON representation
    :rtype: ObjectJsonRepr
    """
    log.info("Exporting quality profiles")
    qp_list = {}
    for qp in get_list(endpoint=endpoint).values():
        log.info("Exporting %s", str(qp))
        json_data = qp.to_json(export_settings=export_settings)
        lang = json_data.pop("language")
        name = json_data.pop("name")
        if lang not in qp_list:
            qp_list[lang] = {}
        qp_list[lang][name] = json_data
    qp_list = hierarchize(qp_list, endpoint=endpoint)
    write_q = kwargs.get("write_q", None)
    if write_q:
        write_q.put(qp_list)
        write_q.put(util.WRITE_END)
    return dict(sorted(qp_list.items()))


def get_object(endpoint: pf.Platform, name: str, language: str) -> Optional[QualityProfile]:
    """Returns a quality profile Object from its name and language

    :param endpoint: Reference to the SonarQube platform
    :param name: Quality profile name
    :param language: Quality profile language

    :return: The quality profile object, of None if not found
    """
    get_list(endpoint)
    o = QualityProfile.CACHE.get(name, language, endpoint.url)
    if not o:
        raise exceptions.ObjectNotFound(name, message=f"Quality Profile '{language}:{name}' not found")
    return o


def _create_or_update_children(name: str, language: str, endpoint: pf.Platform, children: dict[str, StopAsyncIteration], queue: Queue) -> None:
    """Updates or creates all children of a QP"""
    for qp_name, qp_data in children.items():
        qp_data[_KEY_PARENT] = name
        log.debug("Adding child profile '%s' to update queue", qp_name)
        queue.put((qp_name, language, endpoint, qp_data))


def __import_thread(queue: Queue) -> None:
    """Callback function for multithreaded QP import"""
    while not queue.empty():
        (name, lang, endpoint, qp_data) = queue.get()
        try:
            o = get_object(endpoint=endpoint, name=name, language=lang)
        except exceptions.ObjectNotFound:
            if qp_data.get("isBuiltIn", False):
                log.info("Won't import built-in quality profile '%s'", name)
                queue.task_done()
                continue
            log.info("Quality profile '%s' of language '%s' does not exist, creating it", name, lang)
            try:
                # Statistically a new QP is close to Sonar way so better start with the Sonar way ruleset and
                # add/remove a few rules, than adding all rules from 0
                o = QualityProfile.clone(endpoint=endpoint, name=name, language=lang, original_qp_name="Sonar way")
            except Exception:
                o = QualityProfile.create(endpoint=endpoint, name=name, language=lang)
        log.info("Importing quality profile '%s' of language '%s'", name, lang)
        o.update(qp_data, queue)
        log.info("Imported quality profile '%s' of language '%s'", name, lang)
        queue.task_done()


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
    """Imports a configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param dict config_data: the configuration to import
    :param threads: Number of threads (quality profiles import) to run in parallel
    :type threads: int
    :return: Nothing
    """
    threads = 8
    if "qualityProfiles" not in config_data:
        log.info("No quality profiles to import")
        return False
    log.info("Importing quality profiles")
    q = Queue(maxsize=0)
    get_list(endpoint=endpoint)
    for lang, lang_data in config_data["qualityProfiles"].items():
        if not languages.exists(endpoint=endpoint, language=lang):
            log.warning("Language '%s' does not exist, quality profiles import skipped for this language", lang)
            continue
        for name, qp_data in lang_data.items():
            q.put((name, lang, endpoint, qp_data))
    for i in range(threads):
        log.debug("Starting quality profile import thread %d", i)
        worker = Thread(target=__import_thread, args=[q])
        worker.setDaemon(True)
        worker.start()
    q.join()
    return True


def exists(endpoint: pf.Platform, name: str, language: str) -> bool:
    """
    :param Platform endpoint: reference to the SonarQube platform
    :param str name: Quality profile name
    :param str language: Quality profile language
    :return: whether the project exists
    :rtype: bool
    """
    try:
        get_object(endpoint=endpoint, name=name, language=language)
        return True
    except exceptions.ObjectNotFound:
        return False


def convert_one_qp_yaml(qp: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Converts a QP in a modified version more suitable for YAML export"""

    if _CHILDREN_KEY in qp:
        qp[_CHILDREN_KEY] = {k: convert_one_qp_yaml(q) for k, q in qp[_CHILDREN_KEY].items()}
        qp[_CHILDREN_KEY] = util.dict_to_list(qp[_CHILDREN_KEY], "name")
    for rule_group in "rules", "modifiedRules", "addedRules", "removedRules":
        if rule_group in qp:
            qp[rule_group] = rules.convert_rule_list_for_yaml(qp[rule_group])
    return qp


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    new_json = {}
    for lang, qp_list in util.remove_nones(original_json).items():
        new_json[lang] = {"profiles": util.dict_to_list(qp_list, "name")}
    new_json = util.dict_to_list(new_json, "language")
    for lang in new_json:
        lang["profiles"] = [convert_one_qp_yaml(qp) for qp in lang["profiles"]]
    return new_json
