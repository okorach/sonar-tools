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
"""

    Abstraction of the SonarQube "quality gate" concept

"""

from http import HTTPStatus
import json
from requests.exceptions import HTTPError
import sonar.sqobject as sq
from sonar import measures, exceptions
import sonar.permissions.qualitygate_permissions as permissions
from sonar.projects import projects
import sonar.utilities as util

from sonar.audit import rules, severities, types
import sonar.audit.problem as pb


_OBJECTS = {}
_MAP = {}

#: Quality gates APIs
APIS = {
    "create": "qualitygates/create",
    "list": "qualitygates/list",
    "rename": "qualitygates/rename",
    "details": "qualitygates/show",
    "get_projects": "qualitygates/search",
}

__NEW_ISSUES_SHOULD_BE_ZERO = "Any numeric threshold on new issues should be 0 or should be removed from QG conditions"

GOOD_QG_CONDITIONS = {
    "new_reliability_rating": (1, 1, "Any rating other than A would let bugs slip through in new code"),
    "new_security_rating": (1, 1, "Any rating other than A would let vulnerabilities slip through in new code"),
    "new_maintainability_rating": (1, 1, "Expectation is that code smells density on new code is low enough to get A rating"),
    "new_coverage": (20, 90, "Coverage below 20% is a too low bar, above 90% is overkill"),
    "new_bugs": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_vulnerabilities": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_security_hotspots": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_blocker_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_critical_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_major_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_duplicated_lines_density": (1, 5, "Duplication on new code of less than 1% is overkill, more than 5% is too relaxed"),
    "new_security_hotspots_reviewed": (100, 100, "All hotspots on new code must be reviewed, any other condition than 100% make little sense"),
    "reliability_rating": (4, 4, "Threshold on overall code should not be too strict or passing the QG will be often impossible"),
    "security_rating": (4, 4, "Threshold on overall code should not be too strict or passing the QG will be often impossible"),
}

_IMPORTABLE_PROPERTIES = ("isDefault", "isBuiltIn", "conditions", "permissions")


class QualityGate(sq.SqObject):
    """
    Abstraction of the Sonar Quality Gate concept
    """

    @classmethod
    def get_object(cls, endpoint, name):
        """Reads a quality gate from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality gate
        :return: the QualityGate object or None if not found
        :rtype: QualityGate or None
        """
        if name in _MAP and _MAP[name] in _OBJECTS:
            return _OBJECTS[_MAP[name]]
        data = search_by_name(endpoint, name)
        if not data:
            raise exceptions.ObjectNotFound(name, f"Quality gate '{name}' not found")
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint, data):
        """Creates a quality gate from search data
        :return: the QualityGate object
        :rtype: QualityGate or None
        """
        # SonarQube 10 compatibility: "id" field dropped, replaced by "name"
        o = _OBJECTS.get(data.get("id", data["name"]))
        if not o:
            o = cls(data["name"], endpoint, data=data)
        o._json = data
        return o

    @classmethod
    def create(cls, endpoint, name):
        r = endpoint.post(APIS["create"], params={"name": name})
        if not r.ok:
            return None
        return cls.get_object(endpoint, name)

    def __init__(self, name, endpoint, data):
        super().__init__(name, endpoint)
        self.name = name  #: Object name
        self.is_built_in = False  #: Whether the quality gate is built in
        self.is_default = False  #: Whether the quality gate is the default
        self._conditions = None  #: Quality gate conditions
        self._permissions = None  #: Quality gate permissions
        self._projects = None  #: Projects using this quality profile
        self._json = data
        self.name = data.pop("name")
        self.key = data.pop("id", self.name)
        self.is_default = data.get("isDefault", False)
        self.is_built_in = data.get("isBuiltIn", False)
        self.conditions()
        self.permissions()
        _OBJECTS[self.key] = self
        _MAP[self.name] = self.key

    def __str__(self):
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"quality gate '{self.name}'"

    def url(self):
        """
        :return: the SonarQube permalink URL to the quality gate
        :rtype: str
        """
        return f"{self.endpoint.url}/quality_gates/show/{self.key}"

    def projects(self):
        """
        :raises ObjectNotFound: Quality gate not found
        :return: The list of projects using this quality gate
        :rtype: dict {<projectKey>: <projectData>}
        """
        if self._projects is not None:
            return self._projects
        params = {"gateName": self.name, "ps": 500}
        page, nb_pages = 1, 1
        self._projects = {}
        while page <= nb_pages:
            params["p"] = page
            try:
                resp = self.get(APIS["get_projects"], params=params)
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.name, f"{str(self)} not found")
            data = json.loads(resp.text)
            for prj in data["results"]:
                util.logger.info("Proj = %s", str(prj))
                key = prj["key"] if "key" in prj else prj["id"]
                self._projects[key] = projects.Project.get_object(self.endpoint, key)
            nb_pages = util.nbr_pages(data)
            page += 1
        return self._projects

    def count_projects(self):
        """
        :return: The number of projects using this quality gate
        :rtype: int
        """
        return len(self.projects())

    def conditions(self, encoded=False):
        """
        :param encoded: Whether to encode the conditions or not, defaults to False
        :type encoded: bool, optional
        :return: The quality gate conditions, encoded (for simplication) or not
        :rtype: list
        """
        if self._conditions is None:
            self._conditions = []
            data = json.loads(self.get(APIS["details"], params={"name": self.name}).text)
            for c in data.get("conditions", []):
                self._conditions.append(c)
        if encoded:
            return _encode_conditions(self._conditions)
        return self._conditions

    def clear_conditions(self):
        """Clears all quality gate conditions, if quality gate is not built-in
        :return: Nothing
        """
        if self.is_built_in:
            util.logger.debug("Can't clear conditions of built-in %s", str(self))
        else:
            util.logger.debug("Clearing conditions of %s", str(self))
            for c in self.conditions():
                self.post("qualitygates/delete_condition", params={"id": c["id"]})
            self._conditions = None

    def set_conditions(self, conditions_list):
        """Sets quality gate conditions (overriding any previous conditions)
        :param conditions_list: List of conditions, encoded
        :type conditions_list: dict
        :return: Whether the operation succeeded
        :rtype: bool
        """
        if not conditions_list or len(conditions_list) == 0:
            return True
        if self.is_built_in:
            util.logger.debug("Can't set conditions of built-in %s", str(self))
            return False
        self.clear_conditions()
        util.logger.debug("Setting conditions of %s", str(self))
        params = {"gateName": self.name}
        ok = True
        for cond in conditions_list:
            (params["metric"], params["op"], params["error"]) = _decode_condition(cond)
            ok = ok and self.post("qualitygates/create_condition", params=params).ok
        self.conditions()
        return ok

    def permissions(self):
        """
        :return: The quality gate permissions
        :rtype: QualityGatePermissions
        """
        if self._permissions is None:
            self._permissions = permissions.QualityGatePermissions(self)
        return self._permissions

    def set_permissions(self, permissions_list):
        """Sets quality gate permissions
        :param permissions_list:
        :type permissions_list: dict {"users": [<userlist>], "groups": [<grouplist>]}
        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.permissions().set(permissions_list)

    def update(self, **data):
        """Updates a quality gate
        :param dict data: Considered keys: "name", "conditions", "permissions"
        """
        if "name" in data and data["name"] != self.name:
            util.logger.info("Renaming %s with %s", str(self), data["name"])
            self.post(APIS["rename"], params={"id": self.key, "name": data["name"]})
            _MAP.pop(self.name, None)
            self.name = data["name"]
            _MAP[self.name] = self
        ok = self.set_conditions(data.get("conditions", []))
        ok = ok and self.set_permissions(data.get("permissions", []))
        return ok

    def __audit_conditions(self):
        problems = []
        for c in self.conditions():
            m = c["metric"]
            if m not in GOOD_QG_CONDITIONS:
                rule = rules.get_rule(rules.RuleId.QG_WRONG_METRIC)
                msg = rule.msg.format(str(self), m)
                problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
                continue
            val = int(c["error"])
            (mini, maxi, msg) = GOOD_QG_CONDITIONS[m]
            util.logger.debug("Condition on metric '%s': Check that %d in range [%d - %d]", m, val, mini, maxi)
            if val < mini or val > maxi:
                msg = f"{str(self)} condition on metric '{m}': {msg}".format(self.name, m, msg)
                problems.append(pb.Problem(types.Type.BAD_PRACTICE, severities.Severity.HIGH, msg, concerned_object=self))
        return problems

    def audit(self, audit_settings=None):
        """
        :meta private:
        """
        my_name = str(self)
        util.logger.debug("Auditing %s", my_name)
        problems = []
        if self.is_built_in:
            return problems
        max_cond = int(util.get_setting(audit_settings, "audit.qualitygates.maxConditions", 8))
        nb_conditions = len(self.conditions())
        util.logger.debug("Auditing %s number of conditions (%d) is OK", my_name, nb_conditions)
        if nb_conditions == 0:
            rule = rules.get_rule(rules.RuleId.QG_NO_COND)
            msg = rule.msg.format(my_name)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        elif nb_conditions > max_cond:
            rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_COND)
            msg = rule.msg.format(my_name, nb_conditions, max_cond)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        problems += self.__audit_conditions()
        util.logger.debug("Auditing that %s has some assigned projects", my_name)
        if not self.is_default and len(self.projects()) == 0:
            rule = rules.get_rule(rules.RuleId.QG_NOT_USED)
            msg = rule.msg.format(my_name)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems

    def to_json(self, full=False):
        json_data = self._json
        if not self.is_default and not full:
            json_data.pop("isDefault")
        if self.is_built_in:
            if full:
                json_data["_conditions"] = self.conditions(encoded=True)
        else:
            if not full:
                json_data.pop("isBuiltIn")
            json_data["conditions"] = self.conditions(encoded=True)
            json_data["permissions"] = self.permissions().export()
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))


def audit(endpoint=None, audit_settings=None):
    """
    :meta private:
    """
    util.logger.info("--- Auditing quality gates ---")
    problems = []
    quality_gates_list = get_list(endpoint)
    max_qg = util.get_setting(audit_settings, "audit.qualitygates.maxNumber", 5)
    nb_qg = len(quality_gates_list)
    util.logger.debug("Auditing that there are no more than %s quality gates", str(max_qg))
    if nb_qg > max_qg:
        rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_GATES)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(nb_qg, 5), concerned_object=f"{endpoint.url}/quality_gates"))
    for qg in quality_gates_list.values():
        problems += qg.audit(audit_settings)
    return problems


def get_list(endpoint):
    """
    :return: The whole list of quality gates
    :rtype: dict {<name>: <QualityGate>}
    """
    util.logger.info("Getting quality gates")
    data = json.loads(endpoint.get(APIS["list"]).text)
    qg_list = {}
    for qg in data["qualitygates"]:
        util.logger.debug("Getting QG %s", str(qg))
        qg_obj = QualityGate(name=qg["name"], endpoint=endpoint, data=qg)
        if endpoint.version() < (7, 9, 0) and "default" in data and data["default"] == qg["id"]:
            qg_obj.is_default = True
        qg_list[qg_obj.name] = qg_obj
    return qg_list


def export(endpoint, full=False):
    """
    :return: The list of quality gates in their JSON representation
    :rtype: dict
    """
    util.logger.info("Exporting quality gates")
    qg_list = {}
    for k, qg in get_list(endpoint).items():
        qg_list[k] = qg.to_json(full)
    return qg_list


def import_config(endpoint, config_data):
    """Imports quality gates in a SonarQube platform
    Quality gates already existing  are updates with the provided configuration

    :param Platform endpoint: Reference to the SonarQube platform
    :param dict config_data: JSON representation of quality gates (as per export format)
    :return: Whether the import succeeded
    :rtype: bool
    """
    if "qualityGates" not in config_data:
        util.logger.info("No quality gates to import")
        return True
    util.logger.info("Importing quality gates")
    ok = True
    for name, data in config_data["qualityGates"].items():
        try:
            o = QualityGate.get_object(endpoint, name)
        except exceptions.ObjectNotFound:
            o = QualityGate.create(endpoint, name)
        ok = ok and o.update(**data)
    return ok


def count(endpoint):
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :return: Number of quality gates
    :rtype: int
    """
    return len(get_list(endpoint))


def exists(endpoint, gate_name):
    """Returns whether a quality gate exists

    :param Platform endpoint: Reference to the SonarQube platform
    :param str gate_name: Quality gate name
    :return: Whether the quality gate exists
    :rtype: bool
    """
    try:
        _ = QualityGate.get_object(endpoint, gate_name)
        return True
    except exceptions.ObjectNotFound:
        return False


def _encode_conditions(conds):
    simple_conds = []
    for c in conds:
        simple_conds.append(_encode_condition(c))
    return simple_conds


def _encode_condition(c):
    metric, op, val = c["metric"], c["op"], c["error"]
    if op == "GT":
        op = ">="
    elif op == "LT":
        op = "<="
    if metric.endswith("rating"):
        val = measures.get_rating_letter(val)
    return f"{metric} {op} {val}"


def _decode_condition(c):
    (metric, op, val) = c.strip().split(" ")
    if op in (">", ">="):
        op = "GT"
    elif op in ("<", "<="):
        op = "LT"
    if metric.endswith("rating"):
        val = measures.get_rating_number(val)
    return (metric, op, val)


def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, APIS["list"], "qualitygates")
