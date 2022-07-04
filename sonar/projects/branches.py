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

import datetime
import json
import pytz
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
        self._ncloc = None
        if data:
            self.__load(data)
        _OBJECTS[self.uuid()] = self
        util.logger.debug("Created %s", str(self))

    def __str__(self):
        return f"branch '{self.name}' of {str(self.project)}"

    def read(self):
        data = json.loads(self.get(_LIST_API, params={"project": self.project.key}).text)
        for br in data.get("branches", []):
            if br["name"] == self.name:
                self.__load(br)
                break

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
        return _uuid(self.project.key, self.name)

    def last_analysis_date(self):
        if self._last_analysis is None:
            self.read()
        return self._last_analysis

    def last_analysis_age(self, rounded_to_days=True):
        last_analysis = self.last_analysis_date()
        if last_analysis is None:
            return None
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        if rounded_to_days:
            return (today - last_analysis).days
        else:
            return today - last_analysis

    def is_kept_when_inactive(self):
        if self._keep_when_inactive is None or self._json is None:
            self.read()
        return self._keep_when_inactive

    def is_main(self):
        if self._is_main is None or self._json is None:
            self.read()
        return self._is_main

    def delete(self, api=None, params=None):
        util.logger.info("Deleting %s", str(self))
        if not self.post("project_branches/delete", params={"branch": self.name, "project": self.project.key}):
            util.logger.error("%s: deletion failed", str(self))
            return False
        util.logger.info("%s: Successfully deleted", str(self))
        return True

    def new_code(self):
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
        return f"{self.endpoint.url}/dashboard?id={self.project.key}&branch={requests.utils.quote(self.name)}"

    def rename(self, new_name):
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
        if self.last_analysis_date() is not None and self.ncloc() == 0:
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [problem.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
        return []

    def get_measures(self, metrics_list):
        m = measures.get(self.project.key, metrics_list, branch=self.name, endpoint=self.endpoint)
        if "ncloc" in m:
            self._ncloc = 0 if m["ncloc"] is None else int(m["ncloc"])
            if self.is_main():
                self.project._ncloc = self._ncloc
        return m

    def get_issues(self):
        return issues.search_all(
            endpoint=self.endpoint,
            params={
                "componentKeys": self.project.key,
                "branch": self.name,
                "additionalFields": "comments",
            },
        )

    def get_hotspots(self):
        return hotspots.search(
            endpoint=self.endpoint,
            params={
                "projectKey": self.project.key,
                "branch": self.name,
                "additionalFields": "comments",
            },
        )

    def get_findings(self):
        return self.get_issues() + self.get_hotspots()

    def sync(self, another_branch, sync_settings):
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
        age = self.last_analysis_age()
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
        util.logger.debug("Auditing %s", str(self))
        return self.__audit_last_analysis(audit_settings) + self.__audit_zero_loc()


def _uuid(project_key, branch_name):
    return f"{project_key} {branch_name}"


def get_object(branch, project, data=None):
    if project.endpoint.edition() == "community":
        util.logger.debug("Branches not available in Community Edition")
        return None
    b_id = _uuid(project.key, branch)
    if b_id not in _OBJECTS:
        _ = Branch(project, branch, data=data, endpoint=project.endpoint)
    return _OBJECTS[b_id]


def get_list(project):
    if project.endpoint.edition() == "community":
        util.logger.debug("branches not available in Community Edition")
        return {}
    util.logger.debug("Reading all branches of %s", str(project))
    data = json.loads(project.endpoint.get(_LIST_API, params={"project": project.key}).text)
    return [get_object(branch=branch["name"], project=project, data=branch) for branch in data.get("branches", {})]


def exists(branch_name, project_key, endpoint):
    return branch_name in get_list(project=projects.get_object(project_key, endpoint))
