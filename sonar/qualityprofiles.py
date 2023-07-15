#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

import json
from http import HTTPStatus
from queue import Queue
from threading import Thread, Lock
from requests import HTTPError
import requests.utils
from sonar import rules, languages
import sonar.permissions.qualityprofile_permissions as permissions
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

_IMPORTABLE_PROPERTIES = ("name", "language", "parentName", "isBuiltIn", "isDefault", "rules", "permissions")

_CLASS_LOCK = Lock()


class QualityProfile(sq.SqObject):
    """
    Abstraction of the SonarQube "quality profile" concept
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    def __init__(self, key, endpoint, data=None):
        """Do not use, use class methods to create objects"""
        super().__init__(key, endpoint)

        self.name = data["name"]  #: Quality profile name
        self.language = data["language"]  #: Quality profile language
        self.is_default = data["isDefault"]  #: Quality profile is default
        self.is_built_in = data["isBuiltIn"]  #: Quality profile is built-in - read-only
        self._json = data
        self._permissions = None
        self._rules = None
        self.__last_use = None
        self.__last_update = None

        self._rules = self.rules()
        self.nbr_rules = int(data["activeRuleCount"])  #: Number of rules in the quality profile
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])  #: Number of deprecated rules in the quality profile

        (self._projects, self._projects_lock) = (None, Lock())
        self.project_count = data.get("projectCount", None)  #: Number of projects using this quality profile
        self.parent_name = data.get("parentName", None)  #: Name of parent profile, or None if none

        self.__last_use = util.string_to_date(data.get("lastUsed", None))
        self.__last_update = util.string_to_date(data.get("rulesUpdatedAt", None))

        util.logger.debug("Created %s", str(self))
        _MAP[_format(self.name, self.language)] = self.key
        _OBJECTS[self.key] = self

    @classmethod
    def read(cls, endpoint, name, language):
        """Creates a QualityProfile object corresponding to quality profile with same name and language in SonarQube

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param name: Quality profile name
        :type name: str
        :param name: Quality profile language
        :type name: str
        :return: The quality profile object
        :rtype: QualityProfile or None if not found
        """
        if not languages.exists(endpoint=endpoint, language=language):
            util.logger.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        util.logger.debug("Reading quality profile '%s' of language '%s'", name, language)
        key = get_id(name, language)
        if key in _OBJECTS:
            return _OBJECTS[key]
        data = util.search_by_name(endpoint, name, _SEARCH_API, _SEARCH_FIELD, extra_params={"language": language})
        return cls(key=data["key"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint, name, language):
        """Creates a new quality profile in SonarQube and returns the corresponding QualityProfile object

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param name: Quality profile name
        :type name: str
        :param description: Quality profile language
        :type description: str
        :return: The quality profile object
        :rtype: QualityProfile or None if creation failed
        """
        if not languages.exists(endpoint=endpoint, language=language):
            util.logger.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        util.logger.debug("Creating quality profile '%s' of language '%s'", name, language)
        r = endpoint.post(_CREATE_API, params={"name": name, "language": language})
        if not r.ok:
            return None
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def load(cls, endpoint, data):
        """Creates a QualityProfile object from the result of a SonarQube API quality profile search data

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param data: The JSON data corresponding to the quality profile
        :type data: dict
        :return: The quality profile object
        :rtype: QualityProfile
        """
        util.logger.debug("Loading quality profile '%s' of language '%s'", data["name"], data["language"])
        return cls(endpoint=endpoint, key=data["key"], data=data)

    def __str__(self):
        """String formatting of the object

        :rtype: str
        """
        return f"quality profile '{self.name}' of language '{self.language}'"

    def url(self):
        """
        :return: the SonarQube permalink URL to the quality profile
        :rtype: str
        """
        return f"{self.endpoint.url}/profiles/show?language={self.language}&name={requests.utils.quote(self.name)}"

    def last_use(self):
        """
        :return: When the quality profile was last used
        :rtype: datetime or None if never
        """
        return self.__last_use

    def last_update(self):
        """
        :return: When the quality profile was last updated
        :rtype: datetime or None
        """
        return self.__last_update

    def set_parent(self, parent_name):
        """Sets the parent quality profile of the current profile

        :param parent_name: Name of the parent quality profile
        :type parent_name: str
        :return: Whether setting the parent was successful or not
        :rtype: bool
        """
        if parent_name is None:
            return False
        if get_object(name=parent_name, language=self.language) is None:
            util.logger.warning("Can't set parent name '%s' to %s, parent not found", str(parent_name), str(self))
            return False
        if self.parent_name is None or self.parent_name != parent_name:
            params = {"qualityProfile": self.name, "language": self.language, "parentQualityProfile": parent_name}
            r = self.post("qualityprofiles/change_parent", params=params)
            return r.ok
        else:
            util.logger.debug("Won't set parent of %s. It's the same as currently", str(self))
            return True

    def is_child(self):
        """
        :return: Whether the quality profile has a parent
        :rtype: bool
        """
        return self.parent_name is not None

    def inherits_from_built_in(self):
        """
        :return: Whether the quality profile inherits from a built-in profile (following parents of parents)
        :rtype: bool
        """
        return self.built_in_parent() is not None

    def built_in_parent(self):
        """
        :return: The built-in parent profile of the profile, or None
        :rtype: QualityProfile or None if profile does not inherit from a built-in profile
        """
        self.is_built_in = self._json.get("isBuiltIn", False)
        if self.is_built_in:
            return self
        if self.parent_name is None:
            return None
        return get_object(endpoint=self.endpoint, name=self.parent_name, language=self.language).built_in_parent()

    def rules(self):
        """
        :return: The list of rules active in the quality profile
        :rtype: dict{<rule_key>: <rule_data>}
        """
        if self._rules is not None:
            # Assume nobody changed QP during execution
            return self._rules
        self._rules = rules.search(self.endpoint, activation="true", qprofile=self.key, s="key", languages=self.language)
        return self._rules

    def activate_rule(self, rule_key, severity=None, **params):
        """Activates a rule in the quality profile

        :param str rule_key: Rule key to activate
        :param severity: Severity of the rule in the quality profiles, defauls to rule rule default severity
        :type severity: str, optional
        :param params: List of parameters associated to the rules, defaults to None
        :type params: dict, optional
        :return: Whether the activation succeeded
        :rtype: bool
        """
        api_params = {"key": self.key, "rule": rule_key, "severity": severity}
        if len(params) > 0:
            api_params["params"] = ";".join([f"{k}={v}" for k, v in params.items()])
        r = self.post("qualityprofiles/activate_rule", params=api_params)
        if r.status_code == HTTPStatus.NOT_FOUND:
            util.logger.error("Rule %s not found, can't activate it in %s", rule_key, str(self))
        elif r.status_code == HTTPStatus.BAD_REQUEST:
            util.logger.error("HTTP error %d while trying to activate rule %s in %s", r.status_code, rule_key, str(self))
        return r.ok

    def activate_rules(self, ruleset):
        """Activates a list of rules in the quality profile
        :return: Whether the activation of all rules was successful
        :rtype: bool
        """
        if not ruleset:
            return False
        ok = True
        for r_key, r_data in ruleset.items():
            util.logger.debug("Activating rule %s in QG %s data %s", r_key, str(self), str(r_data))
            try:
                sev = r_data if isinstance(r_data, str) else r_data.get("severity", None)
                if "params" in r_data:
                    ok = ok and self.activate_rule(rule_key=r_key, severity=sev, **r_data["params"])
                else:
                    ok = ok and self.activate_rule(rule_key=r_key, severity=sev)
            except HTTPError as e:
                ok = False
                util.logger.warning("Activation of rule '%s' in %s failed: HTTP Error %d", r_key, str(self), e.response.status_code)
        return ok

    def update(self, data, queue):
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
            self.activate_rules(data.get("rules", []))
            self.set_permissions(data.get("permissions", []))
            self.set_parent(data.pop(_KEY_PARENT, None))
            self.is_built_in = data.get("isBuiltIn", False)
            self.is_default = data.get("isDefault", False)

        _create_or_update_children(name=self.name, language=self.language, endpoint=self.endpoint, children=data.get(_CHILDREN_KEY, {}), queue=queue)
        return self

    def to_json(self, full=False):
        """
        :param full: If True, exports all properties, including those that can't be set
        :type full: bool
        :return: the quality profile properties as JSON dict
        :rtype: dict
        """
        json_data = self._json.copy()
        json_data.update({"name": self.name, "language": self.language, "parentName": self.parent_name})
        if not self.is_default:
            json_data.pop("isDefault", None)
        if not self.is_built_in:
            json_data.pop("isBuiltIn", None)
            json_data["rules"] = {k: v.export(full) for k, v in self.rules().items()}
        json_data["permissions"] = self.permissions().export()
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def compare(self, another_qp):
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

    def diff(self, another_qp):
        """Returns the list of rules added or modified in self compared to another_qp (for inheritance)
        :param another_qp: The second quality profile to diff
        :type another_qp: QualityProfile
        :return: dict result of the diff ("inLeft", "modified")
        :rtype: dict
        """
        util.logger.debug("Comparing %s and %s", str(self), str(another_qp))
        compare_result = self.compare(another_qp)
        my_rules = self.rules()
        diff_rules = _treat_added_rules(my_rules, compare_result["inLeft"])
        diff_rules.update(_treat_modified_rules(my_rules, compare_result["modified"]))
        return diff_rules

    def projects(self):
        """Returns the list of projects keys using this quality profile
        :return: dict result of the diff ("inLeft", "modified")
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
                    util.logger.debug("Got QP %s data = %s", self.key, str(data))
                    self._projects += [p["key"] for p in data["results"]]
                    page += 1
                    if self.endpoint.version() >= (10, 0, 0):
                        nb_pages = (data["paging"]["total"] + 500 - 1) // 500
                        more = nb_pages >= page
                    else:
                        more = data["more"]

                util.logger.debug("Projects for %s = '%s'", str(self), ", ".join(self._projects))
        return self._projects

    def used_by_project(self, project):
        """
        :param project: The project
        :type project: Project
        :return: Whether the quality profile is used by the project
        :rtype: bool
        """
        return project.key in self.projects()

    def permissions(self):
        """
        :return: The list of users and groups that can edit the quality profile
        :rtype: dict{"users": <users comma separated>, "groups": <groups comma separated>}
        """
        if self._permissions is None:
            self._permissions = permissions.QualityProfilePermissions(self)
        return self._permissions

    def set_permissions(self, perms):
        """Sets the list of users and groups that can can edit the quality profile
        :params perms:
        :type perms: dict{"users": <users comma separated>, "groups": <groups comma separated>}
        :return: Nothing
        """
        self.permissions().set(perms)

    def audit(self, audit_settings=None):
        """Audits a quality profile and return list of problems found

        :param audit_settings: Options of what to audit and thresholds to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s", str(self))
        if self.is_built_in:
            util.logger.info("%s is built-in, skipping audit", str(self))
            return []

        util.logger.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = []
        age = util.age(self.last_update(), rounded=True)
        if age > audit_settings["audit.qualityProfiles.maxLastChangeAge"]:
            rule = arules.get_rule(arules.RuleId.QP_LAST_CHANGE_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        total_rules = rules.count(endpoint=self.endpoint, languages=self.language)
        if self.nbr_rules < int(total_rules * audit_settings["audit.qualityProfiles.minNumberOfRules"]):
            rule = arules.get_rule(arules.RuleId.QP_TOO_FEW_RULES)
            msg = rule.msg.format(str(self), self.nbr_rules, total_rules)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        age = util.age(self.last_use(), rounded=True)
        if self.project_count == 0 or age is None:
            rule = arules.get_rule(arules.RuleId.QP_NOT_USED)
            msg = rule.msg.format(str(self))
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        elif age > audit_settings["audit.qualityProfiles.maxUnusedAge"]:
            rule = arules.get_rule(arules.RuleId.QP_LAST_USED_DATE)
            msg = rule.msg.format(str(self), age)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        if audit_settings["audit.qualityProfiles.checkDeprecatedRules"]:
            max_deprecated_rules = 0
            parent_qp = self.built_in_parent()
            if parent_qp is not None:
                max_deprecated_rules = parent_qp.nbr_deprecated_rules
            if self.nbr_deprecated_rules > max_deprecated_rules:
                rule = arules.get_rule(arules.RuleId.QP_USE_DEPRECATED_RULES)
                msg = rule.msg.format(str(self), self.nbr_deprecated_rules)
                problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        return problems


def search(endpoint, params=None):
    """Searches projects in SonarQube

    :param params: list of parameters to filter quality profiles to search
    :type params: dict
    :return: list of quality profiles
    :rtype: dict{key: QualityProfile}
    """
    return sq.search_objects(
        endpoint=endpoint, api=_SEARCH_API, params=params, key_field="key", returned_field=_SEARCH_FIELD, object_class=QualityProfile
    )


def get_list(endpoint, use_cache=True):
    """
    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :return: the list of all quality profiles
    :rtype: dict{key: QualityProfile}
    """

    with _CLASS_LOCK:
        if len(_OBJECTS) == 0 or not use_cache:
            search(endpoint=endpoint)
    return _OBJECTS


def audit(endpoint, audit_settings=None):
    """Audits all quality profiles and return list of problems found

    :param audit_settings: Configuration of audit
    :type audit_settings: dict
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: list of problems found
    :rtype: list[Problem]
    """
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
            problems.append(
                pb.Problem(rule.type, rule.severity, rule.msg.format(nb_qp, lang, 5), concerned_object=f"{endpoint.url}/profiles?language={lang}")
            )
    return problems


def hierarchize(qp_list):
    """Organize a flat list of QP in hierarchical (inheritance) fashion

    :param qp_list: List of quality profiles
    :type qp_list: {<language>: {<qp_name>: <qd_data>}}
    :return: Same list with child profiles nested in their parent
    :rtype: {<language>: {<qp_name>: {"children": <qp_list>; <qp_data>}}}
    """
    util.logger.info("Organizing quality profiles in hierarchy")
    for lang, qpl in qp_list.copy().items():
        for qp_name, qp_value in qpl.copy().items():
            util.logger.debug("Treating %s:%s", lang, qp_name)
            if "parentName" not in qp_value:
                continue
            util.logger.debug("QP name '%s:%s' has parent '%s'", lang, qp_name, qp_value["parentName"])
            if _CHILDREN_KEY not in qp_list[lang][qp_value["parentName"]]:
                qp_list[lang][qp_value["parentName"]][_CHILDREN_KEY] = {}

            parent_qp = get_object(qp_value["parentName"], lang)
            this_qp = get_object(name=qp_name, language=lang)
            qp_value["rules"] = {}
            for k, v in this_qp.diff(parent_qp).items():
                qp_value["rules"][k] = v if isinstance(v, str) or "templateKey" not in v else v["severity"]

            qp_list[lang][qp_value["parentName"]][_CHILDREN_KEY][qp_name] = qp_value
            qp_list[lang].pop(qp_name)
            qp_value.pop("parentName")
    return qp_list


def export(endpoint, in_hierarchy=True, full=False):
    """Exports all quality profiles configuration as dict

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param in_hierarchy: Whether quality profiles dict should be organized hierarchically (following inheritance)
    :type in_hierarchy: bool, optional
    :param full: Whether to export all settings including those that can't be set, defaults to False
    :type full: bool, optional
    :return: dict structure of all quality profiles
    :rtype: dict
    """
    util.logger.info("Exporting quality profiles")
    qp_list = {}
    for qp in get_list(endpoint=endpoint).values():
        util.logger.info("Exporting %s", str(qp))
        json_data = qp.to_json(full=full)
        lang = json_data.pop("language")
        name = json_data.pop("name")
        if lang not in qp_list:
            qp_list[lang] = {}
        qp_list[lang][name] = json_data
    if in_hierarchy:
        qp_list = hierarchize(qp_list)
    return qp_list


def get_object(name, language, endpoint=None):
    """Returns a quality profile Object from its name and language

    :param name: Quality profile name
    :type name: str
    :param language: Quality profile language
    :type language: str
    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :return: The quality profile object, of None if not found
    :rtype: QualityProfile or None
    """
    get_list(endpoint)
    fmt = _format(name, language)
    if fmt not in _MAP:
        return None
    return _OBJECTS[_MAP[fmt]]


def _create_or_update_children(name, language, endpoint, children, queue):
    for qp_name, qp_data in children.items():
        qp_data[_KEY_PARENT] = name
        util.logger.debug("Adding child profile '%s' to update queue", qp_name)
        queue.put((qp_name, language, endpoint, qp_data))


def __import_thread(queue):
    while not queue.empty():
        (name, lang, endpoint, qp_data) = queue.get()
        o = get_object(name=name, language=lang, endpoint=endpoint)
        if o is None:
            o = QualityProfile.create(endpoint=endpoint, name=name, language=lang)
        util.logger.info("Importing quality profile '%s' of language '%s'", name, lang)
        o.update(qp_data, queue)
        util.logger.info("Imported quality profile '%s' of language '%s'", name, lang)
        queue.task_done()


def import_config(endpoint, config_data, threads=8):
    """Imports a configuration in SonarQube

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param config_data: the configuration to import
    :type config_data: dict
    :param threads: Number of threads (quality profiles import) to run in parallel
    :type threads: int
    :return: Nothing
    """
    if "qualityProfiles" not in config_data:
        util.logger.info("No quality profiles to import")
        return
    util.logger.info("Importing quality profiles")
    q = Queue(maxsize=0)
    get_list(endpoint=endpoint)
    for lang, lang_data in config_data["qualityProfiles"].items():
        if not languages.exists(endpoint=endpoint, language=lang):
            util.logger.warning("Language '%s' does not exist, quality profile '%s' import skipped", lang, name)
            continue
        for name, qp_data in lang_data.items():
            q.put((name, lang, endpoint, qp_data))
    for i in range(threads):
        util.logger.debug("Starting quality profile import thread %d", i)
        worker = Thread(target=__import_thread, args=[q])
        worker.setDaemon(True)
        worker.start()
    q.join()


def _format(name, lang):
    """
    :meta private:
    """
    return f"{lang}:{name}"


def get_id(name, language):
    """Finds a quality profile (internal) id from its name and language

    The list of quality profile s must have been load by a search before using get_id
    :param name: Quality profile name
    :type name: str
    :param language: Quality profile language
    :type language: str
    :return: The quality profile internal key or None
    :rtype: str or None
    """
    return _MAP.get(_format(name, language), None)


def exists(endpoint, name, language):
    """
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param name: Quality profile name
    :type name: str
    :param language: Quality profile language
    :type language: str
    :return: whether the project exists
    :rtype: bool
    """
    return get_object(name=name, language=language, endpoint=endpoint) is not None


def _treat_added_rules(my_rules, added_rules):
    diff_rules = {}
    for r in added_rules:
        r_key = r.pop("key")
        diff_rules[r_key] = r
        if r_key in my_rules:
            diff_rules[r_key] = rules.convert_for_export(my_rules[r_key].to_json(), my_rules[r_key].language)
        if "severity" in r:
            if isinstance(diff_rules[r_key], str):
                diff_rules[r_key] = r["severity"]
            else:
                diff_rules[r_key]["severity"] = r["severity"]
    return diff_rules


def _treat_modified_rules(my_rules, modified_rules):
    diff_rules = {}
    for r in modified_rules:
        r_key, r_left, r_right = r["key"], r["left"], r["right"]
        diff_rules[r_key] = {"modified": True}
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
