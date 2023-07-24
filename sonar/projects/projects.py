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

    Abstraction of the SonarQube "project" concept

"""
import os
import re
import json
from http import HTTPStatus
from threading import Thread, Lock
from queue import Queue
from requests.exceptions import HTTPError
from sonar import sqobject, components, qualitygates, qualityprofiles, tasks, options, settings, webhooks, devops, measures, exceptions
import sonar.permissions.permissions as perms
from sonar.projects import pull_requests, branches
from sonar.findings import issues, hotspots
import sonar.utilities as util
import sonar.permissions.project_permissions as pperms

from sonar.audit import rules, severities
import sonar.audit.problem as pb

_OBJECTS = {}
_CLASS_LOCK = Lock()

MAX_PAGE_SIZE = 500
_SEARCH_API = "projects/search"
_CREATE_API = "projects/create"
_NAV_API = "navigation/component"
PRJ_QUALIFIER = "TRK"
APP_QUALIFIER = "APP"

_BIND_SEP = ":::"

_IMPORTABLE_PROPERTIES = (
    "key",
    "name",
    "binding",
    settings.NEW_CODE_PERIOD,
    "qualityProfiles",
    "links",
    "permissions",
    "branches",
    "tags",
    "visibility",
    "qualityGate",
    "webhooks",
)


class Project(components.Component):
    """
    Abstraction of the SonarQube project concept
    """

    @classmethod
    def get_object(cls, endpoint, key):
        """Creates a project from a search in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to search
        :raises ObjectNotFound: if project key not found
        :return: The Project
        :rtype: Project
        """
        if key in _OBJECTS:
            return _OBJECTS[key]
        try:
            data = json.loads(endpoint.get(_SEARCH_API, params={"projects": key}, mute=(HTTPStatus.FORBIDDEN,)).text)
            if len(data["components"]) == 0:
                raise exceptions.ObjectNotFound(key, f"Project key {key} not found")
            return cls.load(endpoint, data["components"][0])
        except HTTPError as e:
            if e.response.status_code != HTTPStatus.FORBIDDEN:
                raise
            data = json.loads(endpoint.get(_NAV_API, params={"component": key}).text)
            if "errors" in data:
                raise exceptions.ObjectNotFound(key, f"Project key {key} not found")
            return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint, data):
        """Creates a project loaded with JSON data coming from api/components/search request

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to search
        :param dict data: Project data entry in the search results
        :return: The Project
        :rtype: Project
        """
        key = data["key"]
        if key in _OBJECTS:
            o = _OBJECTS[key]
        else:
            o = cls(endpoint, key)
        o.reload(data)
        return o

    @classmethod
    def create(cls, endpoint, key, name):
        """Creates a Project object after creating it in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to create
        :param str name: Project name
        :return: The Project
        :rtype: Project
        """
        try:
            endpoint.post(_CREATE_API, params={"project": key, "name": name})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists(key, e.response.text)
        o = cls(endpoint, key)
        o.name = name
        return o

    def __init__(self, endpoint, key):
        super().__init__(key, endpoint)
        self._last_analysis = "undefined"
        self._branches_last_analysis = "undefined"
        self._permissions = None
        self._branches = None
        self._pull_requests = None
        self._ncloc_with_branches = None
        self._binding = {"has_binding": True, "binding": None}
        self._new_code = None
        super().__init__(key, endpoint)
        _OBJECTS[key] = self
        util.logger.debug("Created object %s", str(self))

    def __str__(self):
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"project '{self.key}'"

    def refresh(self):
        """Refresh a project from SonarQube

        :raises ObjectNotFound: if project key not found
        :return: self
        :rtype: Project
        """
        data = json.loads(self.get(_SEARCH_API, params={"projects": self.key}).text)
        if len(data["components"]) == 0:
            _OBJECTS.pop(self.uuid(), None)
            raise exceptions.ObjectNotFound(self.key, f"Project key {self.key} not found")
        return self.reload(data["components"][0])

    def reload(self, data):
        """Reloads a project with JSON data coming from api/components/search request

        :param dict data: Data to load
        :return: self
        :rtype: Project
        """
        """Loads a project object with contents of an api/projects/search call"""
        if self._json is None:
            self._json = data
        else:
            self._json.update(data)
        self.name = data["name"]
        self._visibility = data["visibility"]
        if "lastAnalysisDate" in data:
            self._last_analysis = util.string_to_date(data["lastAnalysisDate"])
        elif "analysisDate" in data:
            self._last_analysis = util.string_to_date(data["analysisDate"])
        else:
            self._last_analysis = None
        self.revision = data.get("revision", None)
        return self

    def url(self):
        """
        :return: the SonarQube permalink to the project
        :rtype: str
        """
        return f"{self.endpoint.url}/dashboard?id={self.key}"

    def last_analysis(self, include_branches=False):
        """
        :param include_branches: Take into account branch to determine last analysis, defaults to False
        :type include_branches: bool, optional
        :return: Project last analysis date
        :rtype: datetime
        """
        if self._last_analysis == "undefined":
            self.refresh()
        if not include_branches:
            return self._last_analysis
        if self._branches_last_analysis != "undefined":
            return self._branches_last_analysis

        self._branches_last_analysis = self._last_analysis
        if self.endpoint.version() >= (9, 2, 0):
            # Starting from 9.2 project last analysis date takes into account branches and PR
            return self._branches_last_analysis

        util.logger.debug("Branches = %s", str(self.branches().values()))
        util.logger.debug("PR = %s", str(self.pull_requests().values()))
        for b in self.branches().values() + self.pull_requests().values():
            if b.last_analysis() is None:
                continue
            b_ana_date = b.last_analysis()
            if self._branches_last_analysis is None or b_ana_date > self._branches_last_analysis:
                self._branches_last_analysis = b_ana_date
        return self._branches_last_analysis

    def loc(self):
        """
        :return: Number of LoCs of the project, taking into account branches and pull requests, if any
        :rtype: int
        """
        if self._ncloc_with_branches is not None:
            return self._ncloc_with_branches
        if self.endpoint.edition() == "community":
            self._ncloc_with_branches = super().loc()
        else:
            self._ncloc_with_branches = max([b.loc() for b in self.branches().values() + self.pull_requests().values()])
        return self._ncloc_with_branches

    def get_measures(self, metrics_list):
        """Retrieves a project list of measures

        :param list metrics_list: List of metrics to return
        :return: List of measures of a projects
        :rtype: dict
        """
        m = measures.get(self, metrics_list)
        if "ncloc" in m:
            self.ncloc = 0 if not m["ncloc"].value else int(m["ncloc"].value)
        return m

    def branches(self, use_cache=True):
        """
        :return: Dict of branches of the project
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :type use_cache: bool
        :rtype: dict{<branchName>: <Branch>}
        """
        if not self._branches or not use_cache:
            try:
                self._branches = branches.get_list(self)
            except exceptions.UnsupportedOperation:
                self._branches = {}
        return self._branches

    def main_branch(self):
        """
        :return: Main branch of the project
        :rtype: Branch
        """
        for b in self.branches().values():
            if b.is_main():
                return b
        if self.endpoint.edition() != "community":
            util.logger.warning("Could not find main branch for %s", str(self))
        return None

    def pull_requests(self, use_cache=True):
        """
        :return: List of pull requests of the project
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :type use_cache: bool
        :rtype: dict{PR_ID: PullRequest}
        """
        if self._pull_requests is None or not use_cache:
            try:
                self._pull_requests = pull_requests.get_list(self)
            except exceptions.UnsupportedOperation:
                self._pull_requests = {}
        return self._pull_requests

    def delete(self):
        """Deletes a project in SonarQube

        :raises ObjectNotFound: If object to delete was not found in SonarQube
        :raises request.HTTPError: In all other cases of HTTP Errors
        :return: Nothing
        """
        loc = int(self.get_measure("ncloc", fallback="0"))
        util.logger.info("Deleting %s, name '%s' with %d LoCs", str(self), self.name, loc)
        ok = sqobject.delete_object(self, "projects/delete", {"project": self.key}, _OBJECTS)
        util.logger.info("Successfully deleted %s - %d LoCs", str(self), loc)
        return ok

    def has_binding(self):
        """
        :return: Whether the project has a DevOps platform binding
        :rtype: bool
        """
        _ = self.binding()
        return self._binding["has_binding"]

    def binding(self):
        """
        :return: The project DevOps platform binding
        :rtype: dict
        """
        if self._binding["has_binding"] and self._binding["binding"] is None:
            try:
                resp = self.get("alm_settings/get_binding", params={"project": self.key}, mute=(HTTPStatus.NOT_FOUND,))
                self._binding["has_binding"] = True
                self._binding["binding"] = json.loads(resp.text)
            except HTTPError as e:
                if e.response.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST):
                    # Hack: 8.9 returns 404, 9.x returns 400
                    self._binding["has_binding"] = False
                else:
                    util.exit_fatal(
                        f"alm_settings/get_binding returning status code {e.response.status_code}, exiting",
                        options.ERR_SONAR_API,
                    )
        return self._binding["binding"]

    def is_part_of_monorepo(self):
        """
        :return: From the DevOps binding, Whether the project is part of a monorepo
        :rtype: bool
        """
        if self.binding() is None:
            return False
        return self.binding()["monorepo"]

    def binding_key(self):
        """Computes a unique project binding key

        :meta private:
        """
        p_bind = self.binding()
        if p_bind is None:
            return None
        key = p_bind["alm"] + _BIND_SEP + p_bind["repository"]
        if p_bind["alm"] in ("azure", "bitbucket"):
            key += _BIND_SEP + p_bind["slug"]
        return key

    def __audit_last_analysis(self, audit_settings):
        """Audits whether the last analysis of the project is too old or not

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s last analysis date", str(self))
        problems = []
        age = util.age(self.last_analysis(include_branches=True), True)
        if age is None:
            if not audit_settings["audit.projects.neverAnalyzed"]:
                util.logger.debug("Auditing of never analyzed projects is disabled, skipping")
            else:
                rule = rules.get_rule(rules.RuleId.PROJ_NOT_ANALYZED)
                msg = rule.msg.format(str(self))
                problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
            return problems

        max_age = audit_settings["audit.projects.maxLastAnalysisAge"]
        if max_age == 0:
            util.logger.debug("Auditing of projects with old analysis date is disabled, skipping")
        elif age > max_age:
            rule = rules.get_rule(rules.RuleId.PROJ_LAST_ANALYSIS)
            severity = severities.Severity.HIGH if age > 365 else rule.severity
            loc = self.get_measure("ncloc", fallback="0")
            msg = rule.msg.format(str(self), loc, age)
            problems.append(pb.Problem(rule.type, severity, msg, concerned_object=self))

        util.logger.debug("%s last analysis is %d days old", str(self), age)
        return problems

    def __audit_branches(self, audit_settings):
        """Audits project branches

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if not audit_settings["audit.projects.branches"]:
            util.logger.debug("Auditing of branchs is disabled, skipping...")
            return []
        util.logger.debug("Auditing %s branches", str(self))
        problems = []
        main_br_count = 0
        for branch in self.branches().values():
            problems += branch.audit(audit_settings)
            if branch.name in ("main", "master"):
                main_br_count += 1
                if main_br_count > 1:
                    rule = rules.get_rule(rules.RuleId.PROJ_MAIN_AND_MASTER)
                    problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self))
        return problems

    def __audit_pull_requests(self, audit_settings):
        """Audits project pul requests

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        max_age = audit_settings["audit.projects.pullRequests.maxLastAnalysisAge"]
        if max_age == 0:
            util.logger.debug("Auditing of pull request last analysis age is disabled, skipping...")
            return []
        problems = []
        for pr in self.pull_requests().values():
            problems += pr.audit(audit_settings)
        return problems

    def __audit_visibility(self, audit_settings):
        """Audits project visibility and return problems if project is public

        :param audit_settings: Options and Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if not audit_settings.get("audit.projects.visibility", True):
            util.logger.debug("Project visibility audit is disabled by configuration, skipping...")
            return []
        util.logger.debug("Auditing %s visibility", str(self))
        visi = self.visibility()
        if visi != "private":
            rule = rules.get_rule(rules.RuleId.PROJ_VISIBILITY)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self), visi), concerned_object=self)]
        util.logger.debug("%s visibility is 'private'", str(self))
        return []

    def __audit_languages(self, audit_settings):
        """Audits project utility languages and returns problems if too many LoCs of these

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if not audit_settings.get("audit.projects.utilityLocs", False):
            util.logger.debug("Utility LoCs audit disabled by configuration, skipping")
            return []
        util.logger.debug("Auditing %s utility LoC count", str(self))

        total_locs = 0
        languages = {}
        resp = self.get_measure("ncloc_language_distribution")
        if resp is None:
            return []
        for lang in self.get_measure("ncloc_language_distribution").split(";"):
            (lang, ncloc) = lang.split("=")
            languages[lang] = int(ncloc)
            total_locs += int(ncloc)
        utility_locs = sum(lcount for lang, lcount in languages.items() if lang in ("xml", "json"))
        if total_locs > 100000 and (utility_locs / total_locs) > 0.5:
            rule = rules.get_rule(rules.RuleId.PROJ_UTILITY_LOCS)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self), utility_locs), concerned_object=self)]
        util.logger.debug("%s utility LoCs count (%d) seems reasonable", str(self), utility_locs)
        return []

    def __audit_zero_loc(self, audit_settings):
        """Audits project utility projects with 0 LoCs

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if (
            (not audit_settings["audit.projects.branches"] or self.endpoint.edition() == "community")
            and self.last_analysis() is not None
            and self.loc() == 0
        ):
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
        return []

    def __audit_binding_valid(self, audit_settings):
        if self.endpoint.edition() == "community" or not audit_settings["audit.projects.bindings.validation"] or not self.has_binding():
            util.logger.info(
                "Community edition, binding validation disabled or %s has no binding, skipping binding validation...",
                str(self),
            )
            return []
        try:
            _ = self.get("alm_settings/validate_binding", params={"project": self.key})
            util.logger.debug("%s binding is valid", str(self))
            return []
        except HTTPError as e:
            # Hack: 8.9 returns 404, 9.x returns 400
            if e.response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                rule = rules.get_rule(rules.RuleId.PROJ_INVALID_BINDING)
                return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
            else:
                util.exit_fatal(f"alm_settings/validate_binding returning status code {e.response.status_code}, exiting", options.ERR_SONAR_API)

    def audit(self, audit_settings):
        """Audits a project and returns the list of problems found

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s", str(self))
        return (
            self.__audit_last_analysis(audit_settings)
            + self.__audit_branches(audit_settings)
            + self.__audit_pull_requests(audit_settings)
            + self.__audit_visibility(audit_settings)
            + self.__audit_languages(audit_settings)
            + self.permissions().audit(audit_settings)
            + self._audit_bg_task(audit_settings)
            + self.__audit_binding_valid(audit_settings)
            + self.__audit_zero_loc(audit_settings)
        )

    def export_zip(self, timeout=180):
        """Exports project as zip file, synchronously

        :param timeout: timeout in seconds to complete the export operation
        :type timeout: int
        :return: export status (success/failure/timeout), and zip file path
        :rtype: dict
        """
        util.logger.info("Exporting %s (synchronously)", str(self))
        if self.endpoint.version() < (9, 2, 0) and self.endpoint.edition() not in ("enterprise", "datacenter"):
            raise exceptions.UnsupportedOperation(
                "Project export is only available with Enterprise and Datacenter Edition, or with SonarQube 9.2 or higher for any Edition"
            )
        try:
            resp = self.post("project_dump/export", params={"key": self.key})
        except HTTPError as e:
            return {"status": f"HTTP_ERROR {e.response.status_code}"}
        data = json.loads(resp.text)
        status = tasks.Task(data["taskId"], endpoint=self.endpoint, concerned_object=self, data=data).wait_for_completion(timeout=timeout)
        if status != tasks.SUCCESS:
            util.logger.error("%s export %s", str(self), status)
            return {"status": status}
        dump_file = json.loads(self.get("project_dump/status", params={"key": self.key}).text)["exportedDump"]
        util.logger.debug("%s export %s, dump file %s", str(self), status, dump_file)
        return {"status": status, "file": dump_file}

    def export_async(self):
        """Export project as zip file, synchronously

        :return: export taskId or None if starting the export failed
        :rtype: str or None
        """
        util.logger.info("Exporting %s (asynchronously)", str(self))
        try:
            return json.loads(self.post("project_dump/export", params={"key": self.key}).text)["taskId"]
        except HTTPError:
            return None

    def import_zip(self):
        """Imports a project zip file in SonarQube

        :raises http.HTTPError:
        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.info("Importing %s (asynchronously)", str(self))
        if self.endpoint.edition() not in ("enterprise", "datacenter"):
            raise exceptions.UnsupportedOperation("Project import is only available with Enterprise and Datacenter Edition")
        return self.post("project_dump/import", params={"key": self.key}).ok

    def get_findings(self, branch=None, pr=None):
        """Returns a project list of findings (issues and hotspots)

        :param branch: branch name to consider, if any
        :type branch: str, optional
        :param pr: PR key to consider, if any
        :type pr: str, optional
        :return: JSON of all findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        if self.endpoint.version() < (9, 1, 0) or self.endpoint.edition() not in ("enterprise", "datacenter"):
            util.logger.warning("export_findings only available in EE and DCE starting from SonarQube 9.1, returning no issues")
            return {}
        util.logger.info("Exporting findings for %s", str(self))
        findings_list = {}
        params = {"project": self.key}
        if branch is not None:
            params["branch"] = branch
        elif pr is not None:
            params["pullRequest"] = pr

        data = json.loads(self.get("projects/export_findings", params=params).text)["export_findings"]
        findings_conflicts = {"SECURITY_HOTSPOT": 0, "BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        nbr_findings = {"SECURITY_HOTSPOT": 0, "BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        util.logger.debug(util.json_dump(data))
        for i in data:
            key = i["key"]
            if key in findings_list:
                util.logger.warning("Finding %s (%s) already in past findings", i["key"], i["type"])
                findings_conflicts[i["type"]] += 1
            # FIXME - Hack for wrong projectKey returned in PR
            # m = re.search(r"(\w+):PULL_REQUEST:(\w+)", i['projectKey'])
            i["projectKey"] = self.key
            i["branch"] = branch
            i["pullRequest"] = pr
            nbr_findings[i["type"]] += 1
            if i["type"] == "SECURITY_HOTSPOT":
                findings_list[key] = hotspots.get_object(key, endpoint=self.endpoint, data=i, from_export=True)
            else:
                findings_list[key] = issues.get_object(key, endpoint=self.endpoint, data=i, from_export=True)
        for t in ("SECURITY_HOTSPOT", "BUG", "CODE_SMELL", "VULNERABILITY"):
            if findings_conflicts[t] > 0:
                util.logger.warning("%d %s findings missed because of JSON conflict", findings_conflicts[t], t)
        util.logger.info("%d findings exported for %s branch %s PR %s", len(findings_list), str(self), branch, pr)
        for t in ("SECURITY_HOTSPOT", "BUG", "CODE_SMELL", "VULNERABILITY"):
            util.logger.info("%d %s exported", nbr_findings[t], t)

        return findings_list

    def sync(self, another_project, sync_settings):
        """Syncs project issues with another project

        :param Project another_project: other project to sync issues into
        :type another_project:
        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        tgt_branches = another_project.branches().values()
        report = []
        counters = {}
        for b_src in self.branches().values():
            for b_tgt in tgt_branches:
                if b_src.name == b_tgt.name:
                    (tmp_report, tmp_counts) = b_src.sync(b_tgt, sync_settings=sync_settings)
                    report += tmp_report
                    counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def sync_branches(self, sync_settings):
        """Syncs project issues across all its branches

        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        my_branches = self.branches()
        report = []
        counters = {}
        for b_src in my_branches.values():
            for b_tgt in my_branches.values():
                if b_src.name == b_tgt.name:
                    continue
                (tmp_report, tmp_counts) = b_src.sync(b_tgt, sync_settings=sync_settings)
                report += tmp_report
                counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def quality_profiles(self):
        """Returns the project quality profiles

        :return: dict of quality profiles indexed by language
        :rtype: dict{language: QualityProfile}
        """
        util.logger.debug("Getting %s quality profiles", str(self))
        qp_list = qualityprofiles.get_list(self.endpoint)
        return {qp.language: qp for qp in qp_list.values() if qp.used_by_project(self)}

    def quality_gate(self):
        """Returns the project quality gate

        :return: name of quality gate and whether it's the default
        :rtype: tuple(name, is_default)
        """
        data = json.loads(self.get(api="qualitygates/get_by_project", params={"project": self.key}).text)
        return (data["qualityGate"]["name"], data["qualityGate"]["default"])

    def webhooks(self):
        """
        :return: Project webhooks indexed by their key
        :rtype: dict{key: WebHook}
        """
        util.logger.debug("Getting %s webhooks", str(self))
        return webhooks.get_list(endpoint=self.endpoint, project_key=self.key)

    def links(self):
        """
        :return: list of project links
        :rtype: list[{type, name, url}]
        """
        data = json.loads(self.get(api="project_links/search", params={"projectKey": self.key}).text)
        link_list = None
        for link in data["links"]:
            if link_list is None:
                link_list = []
            link_list.append({"type": link["type"], "name": link.get("name", link["type"]), "url": link["url"]})
        return link_list

    def __export_get_binding(self):
        binding = self.binding()
        if binding:
            # Remove redundant fields
            binding.pop("alm", None)
            binding.pop("url", None)
            if not binding["monorepo"]:
                binding.pop("monorepo")
        return binding

    def __export_get_qp(self):
        qp_json = {qp.language: f"{qp.name}" for qp in self.quality_profiles().values()}
        if len(qp_json) == 0:
            return None
        return qp_json

    def __get_branch_export(self):
        branch_data = {}
        my_branches = self.branches().values()
        for branch in my_branches:
            exp = branch.export(full_export=False)
            if len(my_branches) == 1 and branch.is_main() and len(exp) <= 1:
                # Don't export main branch with no data
                continue
            branch_data[branch.name] = exp
        # If there is only 1 branch with no specific config except being main, don't return anything
        if len(branch_data) == 0 or (len(branch_data) == 1 and len(exp) <= 1):
            return None
        return util.remove_nones(branch_data)

    def export(self, settings_list=None, include_inherited=False, full=False):
        """Exports the entire project configuration as JSON

        :return: All project configuration settings
        :rtype: dict
        """
        util.logger.info("Exporting %s", str(self))
        json_data = self._json.copy()
        json_data.update({"key": self.key, "name": self.name})
        json_data["binding"] = self.__export_get_binding()
        nc = self.new_code()
        if nc != "":
            json_data[settings.NEW_CODE_PERIOD] = nc
        json_data["qualityProfiles"] = self.__export_get_qp()
        json_data["links"] = self.links()
        json_data["permissions"] = self.permissions().to_json(csv=True)
        json_data["branches"] = self.__get_branch_export()
        json_data["tags"] = util.list_to_csv(self.tags(), separator=", ")
        json_data["visibility"] = self.visibility()
        (json_data["qualityGate"], qg_is_default) = self.quality_gate()
        if qg_is_default:
            json_data.pop("qualityGate")

        json_data["webhooks"] = webhooks.export(self.endpoint, self.key)
        json_data = util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full)
        settings_dict = settings.get_bulk(endpoint=self, component=self, settings_list=settings_list, include_not_set=False)
        # json_data.update({s.to_json() for s in settings_dict.values() if include_inherited or not s.inherited})
        for s in settings_dict.values():
            if not include_inherited and s.inherited:
                continue
            json_data.update(s.to_json())
        return util.remove_nones(json_data)

    def new_code(self):
        """
        :return: The project new code definition
        :rtype: str
        """
        if self._new_code is None:
            new_code = settings.Setting.read(settings.NEW_CODE_PERIOD, self.endpoint, component=self)
            self._new_code = new_code.value if new_code else ""
        return self._new_code

    def permissions(self):
        """
        :return: The project permissions
        :rtype: ProjectPermissions
        """
        if self._permissions is None:
            self._permissions = pperms.ProjectPermissions(self)
        return self._permissions

    def set_permissions(self, desired_permissions):
        """Sets project permissions

        :param desired_permissions: dict describing permissions
        :type desired_permissions: dict
        :return: Nothing
        """
        self.permissions().set(desired_permissions)

    def set_links(self, desired_links):
        """Sets project links

        :param desired_links: dict describing links
        :type desired_links: dict
        :return: Whether the operation was successful
        """
        params = {"projectKey": self.key}
        ok = True
        for link in desired_links.get("links", {}):
            if link.get("type", "") != "custom":
                continue
            params.update(link)
            ok = ok and self.post("project_links/create", params=params).ok

    def set_tags(self, tags):
        """Sets project tags

        :param list tags: list of tags
        :return: Whether the operation was successful
        """
        if tags is None:
            return
        my_tags = util.list_to_csv(tags) if isinstance(tags, list) else util.csv_normalize(tags)
        r = self.post("project_tags/set", params={"project": self.key, "tags": my_tags})
        self._tags = util.csv_to_list(my_tags)
        return r.ok

    def set_quality_gate(self, quality_gate):
        """Sets project quality gate

        :param quality_gate: quality gate name
        :type quality_gate: str
        :return: Whether the operation was successful
        :rtype: bool
        """
        if quality_gate is None:
            return False
        try:
            _ = qualitygates.QualityGate.get_object(self.endpoint, quality_gate)
        except exceptions.ObjectNotFound:
            util.logger.warning("Quality gate '%s' not found, can't set it for %s", quality_gate, str(self))
            return False
        util.logger.debug("Setting quality gate '%s' for %s", quality_gate, str(self))
        r = self.post("qualitygates/select", params={"projectKey": self.key, "gateName": quality_gate})
        return r.ok

    def set_quality_profile(self, language, quality_profile):
        """Sets project quality profile for a given language

        :param language: Language mnemonic, following SonarQube convention
        :type language: str
        :param quality_profile: Name of the quality profile in the language
        :type quality_profile: str
        :return: Whether the operation was successful
        :rtype: bool
        """
        if not qualityprofiles.exists(endpoint=self.endpoint, language=language, name=quality_profile):
            util.logger.warning("Quality profile '%s' in language '%s' does not exist, can't set it for %s", quality_profile, language, str(self))
            return False
        util.logger.debug("Setting quality profile '%s' of language '%s' for %s", quality_profile, language, str(self))
        r = self.post("qualityprofiles/add_project", params={"project": self.key, "qualityProfile": quality_profile, "language": language})
        return r.ok

    def rename_main_branch(self, main_branch_name):
        """Renames the project main branch

        :param main_branch_name: New main branch name
        :type main_branch_name: str
        :return: Whether the operation was successful
        :rtype: bool
        """
        br = self.main_branch()
        if br:
            return br.rename(main_branch_name)
        util.logger.warning("No main branch to rename found for %s", str(self))
        return False

    def set_webhooks(self, webhook_data):
        """Sets project webhooks

        :param dict webhook_data: JSON describing the webhooks
        :return: Nothing
        """
        current_wh = self.webhooks()
        current_wh_names = [wh.name for wh in current_wh.values()]
        wh_map = {wh.name: k for k, wh in current_wh.items()}
        # FIXME: Handle several webhooks with same name
        for wh_name, wh in webhook_data.items():
            if wh_name in current_wh_names:
                current_wh[wh_map[wh_name]].update(name=wh_name, **wh)
            else:
                webhooks.update(name=wh_name, endpoint=self.endpoint, project=self.key, **wh)

    def set_settings(self, data):
        """Sets project settings (webhooks, settings, new code period)

        :param dict data: JSON describing the settings
        :return: Nothing
        """
        util.logger.debug("Setting %s settings with %s", str(self), util.json_dump(data))
        for key, value in data.items():
            if key in ("branches", settings.NEW_CODE_PERIOD):
                continue
            if key == "webhooks":
                self.set_webhooks(value)
            else:
                settings.set_setting(endpoint=self.endpoint, key=key, value=value, component=self)

        nc = data.get(settings.NEW_CODE_PERIOD, None)
        if nc is not None:
            (nc_type, nc_val) = settings.decode(settings.NEW_CODE_PERIOD, nc)
            settings.set_new_code_period(self.endpoint, nc_type, nc_val, project_key=self.key)
        # TODO: Update branches (main, new code definition, keepWhenInactive)
        # util.logger.debug("Checking main branch")
        # for branch, branch_data in data.get("branches", {}).items():
        #    if branches.exists(branch_name=branch, project_key=self.key, endpoint=self.endpoint):
        #        branches.get_object(branch, self, endpoint=self.endpoint).update(branch_data)()

    def set_devops_binding(self, data):
        """Sets project devops binding settings

        :param dict data: JSON describing the devops binding
        :return: Nothing
        """
        util.logger.debug("Setting devops binding of %s to %s", str(self), util.json_dump(data))
        alm_key = data["key"]
        if not devops.platform_exists(alm_key, self.endpoint):
            util.logger.warning("DevOps platform '%s' does not exists, can't set it for %s", alm_key, str(self))
            return False
        alm_type = devops.devops_type(platform_key=alm_key, endpoint=self.endpoint)
        mono = data.get("monorepo", False)
        repo = data["repository"]
        if alm_type == "github":
            self.set_binding_github(alm_key, repository=repo, monorepo=mono, summary_comment=data.get("summaryComment", True))
        elif alm_type == "gitlab":
            self.set_binding_gitlab(alm_key, repository=repo, monorepo=mono)
        elif alm_type == "azure":
            self.set_binding_azure_devops(alm_key, repository=repo, monorepo=mono, slug=data["slug"])
        elif alm_type == "bitbucket":
            self.set_binding_bitbucket_server(alm_key, repository=repo, monorepo=mono, slug=data["slug"])
        elif alm_type == "bitbucketcloud":
            self.set_binding_bitbucket_cloud(alm_key, repository=repo, monorepo=mono)
        else:
            util.logger.error("Invalid devops platform type '%s' for %s, setting skipped", alm_key, str(self))
            return False
        return True

    def __std_binding_params(self, alm_key, repo, monorepo):
        return {"almSetting": alm_key, "project": self.key, "repository": repo, "monorepo": str(monorepo).lower()}

    def set_binding_github(self, devops_platform_key, repository, monorepo=False, summary_comment=True):
        """Sets project devops binding for github

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in github
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :param summary_comment: Whether summary comments should be posted, defaults to True
        :type summary_comment: bool, optional
        :return: Nothing
        """
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["summaryCommentEnabled"] = str(summary_comment).lower()
        self.post("alm_settings/set_github_binding", params=params)

    def set_binding_gitlab(self, devops_platform_key, repository, monorepo=False):
        """Sets project devops binding for gitlab

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in gitlab
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        self.post("alm_settings/set_gitlab_binding", params=params)

    def set_binding_bitbucket_server(self, devops_platform_key, repository, slug, monorepo=False):
        """Sets project devops binding for bitbucket server

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in bitbucket server
        :param str slug: project repository SLUG
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["slug"] = slug
        self.post("alm_settings/set_bitbucket_binding", params=params)

    def set_binding_bitbucket_cloud(self, devops_platform_key, repository, monorepo=False):
        """Sets project devops binding for bitbucket cloud

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in bitbucket cloud
        :param str slug: project repository SLUG
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        self.post("alm_settings/set_bitbucketcloud_binding", params=params)

    def set_binding_azure_devops(self, devops_platform_key, slug, repository, monorepo=False):
        """Sets project devops binding for azure devops

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str slug: project SLUG in Azure DevOps
        :param str repository: project repository name in azure devops
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["projectName"] = slug
        params["repositoryName"] = params.pop("repository")
        self.post("alm_settings/set_azure_binding", params=params)

    def update(self, data):
        """Updates a project with a whole configuration set

        :param dict data: JSON of configuration settings
        :return: Nothing
        """
        if "permissions" in data:
            decoded_perms = {}
            for ptype in perms.PERMISSION_TYPES:
                if ptype not in data["permissions"]:
                    continue
                decoded_perms[ptype] = {u: perms.decode(v) for u, v in data["permissions"][ptype].items()}
            self.set_permissions(decoded_perms)
        self.set_links(data)
        self.set_tags(data.get("tags", None))
        self.set_quality_gate(data.get("qualityGate", None))
        for lang, qp_name in data.get("qualityProfiles", {}).items():
            self.set_quality_profile(language=lang, quality_profile=qp_name)
        for bname, bdata in data.get("branches", {}).items():
            if bdata.get("isMain", False):
                self.rename_main_branch(bname)
                break
        if "binding" in data:
            self.set_devops_binding(data["binding"])
        else:
            util.logger.debug("%s has no devops binding, skipped", str(self))
        settings_to_apply = {
            k: v for k, v in data.items() if k not in ("permissions", "tags", "links", "qualityGate", "qualityProfiles", "binding", "name")
        }
        # TODO: Set branch settings
        self.set_settings(settings_to_apply)

    def search_params(self):
        """Return params used to search for that object

        :meta private:
        """
        return {"project": self.key}


def count(endpoint, params=None):
    """Counts projects

    :param params: list of parameters to filter projects to search
    :type params: dict
    :return: Count of projects
    :rtype: int
    """
    new_params = {} if params is None else params.copy()
    new_params.update({"ps": 1, "p": 1})
    data = json.loads(endpoint.get(_SEARCH_API, params=params).text)
    return data["paging"]["total"]


def search(endpoint, params=None):
    """Searches projects in SonarQube

    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param params: list of parameters to narrow down the search
    :type params: dict
    :return: list of projects
    :rtype: dict{key: Project}
    """
    new_params = {} if params is None else params.copy()
    new_params["qualifiers"] = "TRK"
    return sqobject.search_objects(
        api="projects/search",
        params=new_params,
        key_field="key",
        returned_field="components",
        endpoint=endpoint,
        object_class=Project,
    )


def get_list(endpoint, key_list=None, use_cache=True):
    """
    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param key_list: List of portfolios keys to get, if None or empty all portfolios are returned
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :return: the list of all quality profiles
    :rtype: dict{key: QualityProfile}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            util.logger.info("Listing projects")
            return search(endpoint=endpoint)
    return {key: Project.get_object(endpoint, key) for key in util.csv_to_list(key_list)}


def key_obj(key_or_obj):
    if isinstance(key_or_obj, str):
        return (key_or_obj, _OBJECTS.get(key_or_obj, None))
    else:
        return (key_or_obj.key, key_or_obj)


def __audit_thread(queue, results, audit_settings, bindings):
    audit_bindings = audit_settings["audit.projects.bindings"]
    while not queue.empty():
        util.logger.debug("Picking from the queue")
        project = queue.get()
        results += project.audit(audit_settings)
        if project.endpoint.edition() == "community" or not audit_bindings or project.is_part_of_monorepo():
            queue.task_done()
            util.logger.debug("%s audit done", str(project))
            continue
        bindkey = project.binding_key()
        if bindkey and bindkey in bindings:
            rule = rules.get_rule(rules.RuleId.PROJ_DUPLICATE_BINDING)
            results.append(pb.Problem(rule.type, rule.severity, rule.msg.format(str(project), str(bindings[bindkey])), concerned_object=project))
        else:
            bindings[bindkey] = project
        queue.task_done()
        util.logger.debug("%s audit done", str(project))
    util.logger.debug("Queue empty, exiting thread")


def audit(endpoint, audit_settings, key_list=None):
    """Audits all or a list of projects

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param audit_settings: Configuration of audit
    :type audit_settings: dict
    :param key_list: List of project keys to audit, defaults to None (all projects)
    :type key_list: str, optional
    :return: list of problems found
    :rtype: list[Problem]
    """
    util.logger.info("--- Auditing projects ---")
    plist = get_list(endpoint, key_list)
    problems = []
    q = Queue(maxsize=0)
    for p in plist.values():
        q.put(p)
    bindings = {}
    for i in range(audit_settings["threads"]):
        util.logger.debug("Starting project audit thread %d", i)
        worker = Thread(target=__audit_thread, args=(q, problems, audit_settings, bindings))
        worker.setDaemon(True)
        worker.setName(f"ProjectAudit{i}")
        worker.start()
    q.join()
    if not audit_settings["audit.projects.duplicates"]:
        util.logger.info("Project duplicates auditing was disabled by configuration")
        return problems
    for key, p in plist.items():
        util.logger.debug("Auditing for potential duplicate projects")
        for key2 in plist:
            if key2 != key and re.match(key2, key):
                rule = rules.get_rule(rules.RuleId.PROJ_DUPLICATE)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(str(p), key2), concerned_object=p))
    return problems


def __export_thread(queue, results, full):
    while not queue.empty():
        project = queue.get()
        results[project.key] = project.export(full=full)
        results[project.key].pop("key")
        queue.task_done()


def export(endpoint, key_list=None, full=False, threads=8):
    """Exports all or a list of projects configuration as dict

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param key_list: List of project keys to export, defaults to None (all projects)
    :type key_list: str
    :param full: Whether to export all settings including those useless for re-import, defaults to False
    :type full: bool, optional
    :param threads: Number of parallel threads for export, defaults to 8
    :type threads: int, optional
    :return: list of projects
    :rtype: dict{key: Project}
    """
    for qp in qualityprofiles.get_list(endpoint).values():
        qp.projects()

    q = Queue(maxsize=0)
    for p in get_list(endpoint=endpoint, key_list=key_list).values():
        q.put(p)
    project_settings = {}
    for i in range(threads):
        util.logger.debug("Starting project export thread %d", i)
        worker = Thread(target=__export_thread, args=(q, project_settings, full))
        worker.setDaemon(True)
        worker.setName(f"ProjectExport{i}")
        worker.start()
    q.join()
    return project_settings


def exists(key, endpoint):
    """
    :param key: project key to check
    :type key: str
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: whether the project exists
    :rtype: bool
    """
    try:
        Project.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


def loc_csv_header(**kwargs):
    arr = ["# Project Key"]
    if kwargs[options.WITH_NAME]:
        arr.append("Project name")
    arr.append("LoC")
    if kwargs[options.WITH_LAST_ANALYSIS]:
        arr.append("Last analysis")
    if kwargs[options.WITH_URL]:
        arr.append("URL")
    return arr


def import_config(endpoint, config_data, key_list=None):
    """Imports a configuration in SonarQube

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param config_data: the configuration to import
    :type config_data: dict
    :param key_list: List of project keys to be considered for the import, defaults to None (all projects)
    :type key_list: str
    :return: Nothing
    """
    if "projects" not in config_data:
        util.logger.info("No projects to import")
        return
    util.logger.info("Importing projects")
    get_list(endpoint=endpoint)
    nb_projects = len(config_data["projects"])
    i = 0
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["projects"].items():
        if new_key_list and key not in new_key_list:
            continue
        util.logger.info("Importing project key '%s'", key)
        try:
            o = Project.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            o = Project.create(endpoint, key, data["name"])
        o.update(data)
        i += 1
        if i % 20 == 0 or i == nb_projects:
            util.logger.info("Imported %d/%d projects (%d%%)", i, nb_projects, (i * 100 // nb_projects))


def __export_zip_thread(queue, results, statuses, export_timeout):
    while not queue.empty():
        project = queue.get()
        try:
            dump = project.export_zip(timeout=export_timeout)
        except exceptions.UnsupportedOperation:
            queue.task_done()
            util.exit_fatal("Zip export unsupported on your SonarQube version", options.ERR_UNSUPPORTED_OPERATION)
        status = dump["status"]
        statuses[status] = 1 if status not in statuses else statuses[status] + 1
        data = {"key": project.key, "status": status}
        if status == "SUCCESS":
            data["file"] = os.path.basename(dump["file"])
            data["path"] = dump["file"]
        results.append(data)
        util.logger.info("%s", ", ".join([f"{k}:{v}" for k, v in statuses.items()]))
        queue.task_done()


def export_zip(endpoint, key_list=None, threads=8, export_timeout=30):
    """Export as zip all or a list of projects

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param key_list: List of project keys to export, defaults to None (all projects)
    :type key_list: str, optional
    :param threads: Number of parallel threads for export, defaults to 8
    :type threads: int, optional
    :param export_timeout: Tiemout to export the project, defaults to 30
    :type export_timeout: int, optional
    :return: list of exported projects and platform version
    :rtype: dict
    """
    statuses, exports = {}, []
    projects_list = get_list(endpoint, key_list)
    nbr_projects = len(projects_list)
    util.logger.info("Exporting %d projects to export", nbr_projects)
    q = Queue(maxsize=0)
    for p in projects_list.values():
        q.put(p)
    for i in range(threads):
        util.logger.debug("Starting project export thread %d", i)
        worker = Thread(target=__export_zip_thread, args=(q, exports, statuses, export_timeout))
        worker.setDaemon(True)
        worker.setName(f"ZipExport{i}")
        worker.start()
    q.join()

    return {
        "sonarqube_environment": {
            "version": endpoint.version(digits=2, as_string=True),
            "plugins": endpoint.plugins(),
        },
        "project_exports": exports,
    }
