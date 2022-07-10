#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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

    Abstraction of the SonarQube "branch" concept

"""

import json
import requests.utils
from sonar import measures, components, syncer, settings
from sonar.projects import projects
from sonar.findings import issues, hotspots
import sonar.utilities as util

from sonar.audit import rules, problem

_OBJECTS = {}
_LIST_API = "project_branches/list"


class Branch(components.Component):
    def __init__(self, project, name, data=None, endpoint=None):
        if endpoint is not None:
            super().__init__(name, endpoint)
        else:
            super().__init__(name, project.endpoint)
        self.name = name
        self.project = project
        self._is_main = None
        self._json = data
        self._new_code = None
        self._last_analysis = None
        self._keep_when_inactive = None
        if data:
            self.__load(data)
        _OBJECTS[self.uuid()] = self
        util.logger.debug("Created %s", str(self))

    def __str__(self):
        return f"branch '{self.name}' of {str(self.project)}"

    def read(self):
        """Reads a branch in SonarQube (refresh with latest data)

        :return: itself
        :rtype: Branch
        """
        data = json.loads(self.get(_LIST_API, params={"project": self.project.key}).text)
        for br in data.get("branches", []):
            if br["name"] == self.name:
                self.__load(br)
                break
        return self

    def __load(self, data):
        if self._json is None:
            self._json = data
        else:
            self._json.update(data)
        self._is_main = self._json["isMain"]
        self._last_analysis = util.string_to_date(self._json.get("analysisDate", None))
        self._keep_when_inactive = self._json.get("excludedFromPurge", False)
        self._is_main = self._json.get("isMain", False)

    def uuid(self):
        """Computes a uuid for the branch that can serve as index
        :return: the UUID
        :rtype: str
        """
        return _uuid(self.project.key, self.name)

    def last_analysis(self):
        """
        :param include_branches: Unused, present for inheritance reasons
        :type include_branches: bool, optional
        :return: Datetime of last analysis
        :rtype: datetime
        """
        if self._last_analysis is None:
            self.read()
        return self._last_analysis

    def is_kept_when_inactive(self):
        """
        :return: Whether the branch is kept when inactive
        :rtype: bool
        """
        if self._keep_when_inactive is None or self._json is None:
            self.read()
        return self._keep_when_inactive

    def is_main(self):
        """
        :return: Whether the branch is the project main branch
        :rtype: bool
        """
        if self._is_main is None or self._json is None:
            self.read()
        return self._is_main

    def delete(self, api=None, params=None):
        """Deletes a branch

        :return: Whether the deletion was successful
        :rtype: bool
        """
        util.logger.info("Deleting %s", str(self))
        r = self.post("project_branches/delete", params={"branch": self.name, "project": self.project.key})
        if r.ok:
            util.logger.info("%s: Successfully deleted", str(self))
        else:
            util.logger.error("%s: deletion failed", str(self))
        return r.ok

    def new_code(self):
        """
        :return: The branch new code period definition
        :rtype: str
        """
        if self._new_code is None:
            data = json.loads(self.get(api="new_code_periods/list", params={"project": self.project.key}).text)
            for b in data["newCodePeriods"]:
                new_code = settings.new_code_to_string(b)
                if b["branchKey"] == self.name:
                    self._new_code = new_code
                else:
                    b_obj = get_object(b["branchKey"], self.project)
                    b_obj._new_code = new_code
        return self._new_code

    def export(self, full_export=True):
        """Exports a branch configuration (is main, keep when inactive, optionally name, project)

        :param full_export: Also export branches attributes that are not needed for import, defaults to True
        :type include_branches: bool, optional
        :return: The branch new code period definition
        :rtype: str
        """
        util.logger.debug("Exporting %s", str(self))
        data = {settings.NEW_CODE_PERIOD: self.new_code()}
        if self.is_main():
            data["isMain"] = True
        if self.is_kept_when_inactive() and not self.is_main():
            data["keepWhenInactive"] = True
        if self.new_code():
            data[settings.NEW_CODE_PERIOD] = self.new_code()
        if full_export:
            data.update({"name": self.name, "project": self.project.key})
        data = util.remove_nones(data)
        return None if len(data) == 0 else data

    def url(self):
        """
        :return: The branch URL in SonarQube as permalink
        :rtype: str
        """
        return f"{self.endpoint.url}/dashboard?id={self.project.key}&branch={requests.utils.quote(self.name)}"

    def rename(self, new_name):
        """Renames a branch

        :param new_name: New branch name
        :type new_name: str
        :return: Whether the branch was renamed
        :rtype: bool
        """
        if not self.is_main():
            util.logger.error("Can't rename any other branch than the main branch")
            return False
        if self.name == new_name:
            util.logger.debug("Skipping rename %s with same new name", str(self))
            return True
        util.logger.info("Renaming main branch of %s from '%s' to '%s'", str(self.project), self.name, new_name)
        resp = self.post("project_branches/rename", params={"project": self.project.key, "name": new_name}, exit_on_error=False)
        if not resp.ok:
            util.logger.error("HTTP %d - %s", resp.status_code, resp.text)
            return False
        self.name = new_name
        return True

    def __audit_zero_loc(self):
        if self.last_analysis() and self.loc() == 0:
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [problem.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
        return []

    def get_measures(self, metrics_list):
        """Retrieves a branch list of measures

        :param metrics_list: List of metrics to return
        :type metrics_list: str (comma separated)
        :return: List of measures of a projects
        :rtype: dict
        """
        return measures.get(self, metrics_list)

    def get_issues(self):
        """Returns a branch list of issues

        :return: dict of Issues, with issue key as key
        :rtype: dict{key: Issue}
        """
        return issues.search_all(
            endpoint=self.endpoint,
            params={
                "componentKeys": self.project.key,
                "branch": self.name,
                "additionalFields": "comments",
            },
        )

    def get_hotspots(self):
        """Returns a branch list of hotspots

        :return: dict of Hotspots, with hotspot key as key
        :rtype: dict{key: Hotspot}
        """
        return hotspots.search(
            endpoint=self.endpoint,
            params={
                "projectKey": self.project.key,
                "branch": self.name,
                "additionalFields": "comments",
            },
        )

    def get_findings(self):
        """Returns a branch list of findings

        :return: dict of Findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        return self.get_issues() + self.get_hotspots()

    def sync(self, another_branch, sync_settings):
        """Syncs branch findings with another branch

        :param another_branch: other branch to sync issues into (not necesssarily of same project)
        :type another_branch: Branch
        :param sync_settings: Parameters to configure the sync
        :type sync_settings: dict
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        report, counters = [], {}
        (report, counters) = syncer.sync_lists(
            self.get_issues(),
            another_branch.get_issues(),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        (tmp_report, tmp_counts) = syncer.sync_lists(
            self.get_hotspots(),
            another_branch.get_hotspots(),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        report += tmp_report
        counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def __audit_last_analysis(self, audit_settings):
        age = util.age(self.last_analysis())
        if self.is_main() or age is None:
            # Main branch (not purgeable) or branch not analyzed yet
            return []
        max_age = audit_settings["audit.projects.branches.maxLastAnalysisAge"]
        problems = []
        if self.is_kept_when_inactive():
            util.logger.debug("%s is kept when inactive (not purgeable)", str(self))
        elif age > max_age:
            rule = rules.get_rule(rules.RuleId.BRANCH_LAST_ANALYSIS)
            msg = rule.msg.format(str(self), age)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
        else:
            util.logger.debug("%s age is %d days", str(self), age)
        return problems

    def audit(self, audit_settings):
        """Audits a branch and return list of problems found

        :param audit_settings: Options of what to audit and thresholds to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s", str(self))
        return self.__audit_last_analysis(audit_settings) + self.__audit_zero_loc()

    def search_params(self):
        """Return params used to search for that object

        :meta private:
        """
        return {"project": self.project.key, "branch": self.name}


def _uuid(project_key, branch_name):
    return f"{project_key} {branch_name}"


def get_object(branch, project, data=None):
    """Retrieves a branch

    :param branch: Branch name
    :type branch: str
    :param project: Project the branch belongs to
    :type project: Project
    :return: The Branch object
    :rtype: Branch
    """
    if project.endpoint.edition() == "community":
        util.logger.debug("Branches not available in Community Edition")
        return None
    b_id = _uuid(project.key, branch)
    if b_id not in _OBJECTS:
        _ = Branch(project, branch, data=data, endpoint=project.endpoint)
    return _OBJECTS[b_id]


def get_list(project):
    """Retrieves a branch

    :param branch: Branch name
    :type branch: str
    :param project: Project the branch belongs to
    :type project: Project
    :return: The Branch object
    :rtype: Branch
    """
    if project.endpoint.edition() == "community":
        util.logger.debug("branches not available in Community Edition")
        return {}
    util.logger.debug("Reading all branches of %s", str(project))
    data = json.loads(project.endpoint.get(_LIST_API, params={"project": project.key}).text)
    return [get_object(branch=branch["name"], project=project, data=branch) for branch in data.get("branches", {})]


def exists(branch_name, project_key, endpoint):
    """
    :param branch_name: Branch name
    :type branch_name: str
    :param project_key: Project key
    :type project_key: str
    :return: Whether the branch exists in SonarQube
    :rtype: bool
    """
    return branch_name in get_list(project=projects.get_object(project_key, endpoint))
