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
import pytz
import requests.utils
from sonar import projects, measures, components, syncer
from sonar.findings import issues, hotspots
import sonar.utilities as util

from sonar.audit import rules, problem

_BRANCHES = {}


class Branch(components.Component):
    def __init__(self, project, name, data=None, endpoint=None):
        if endpoint is not None:
            super().__init__(name, endpoint)
        else:
            super().__init__(name, project.endpoint)
        self.name = name
        self.project = project
        self.json = data
        self._last_analysis_date = None
        self._ncloc = None
        _BRANCHES[self.uuid()] = self
        util.logger.debug("Created object %s", str(self))

    def __str__(self):
        return f"branch '{self.name}' of {str(self.project)}"

    def uuid(self):
        return _uuid(self.project.key, self.name)

    def last_analysis_date(self):
        if self._last_analysis_date is None and "analysisDate" in self.json:
            self._last_analysis_date = util.string_to_date(self.json["analysisDate"])
        return self._last_analysis_date

    def last_analysis_age(self, rounded_to_days=True):
        last_analysis = self.last_analysis_date()
        if last_analysis is None:
            return None
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        if rounded_to_days:
            return (today - last_analysis).days
        else:
            return today - last_analysis

    def is_purgeable(self):
        return self.json.get("excludedFromPurge", False)

    def is_main(self):
        return self.json.get("isMain", False)

    def delete(self, api=None, params=None):
        util.logger.info("Deleting %s", str(self))
        if not self.post(
            "api/project_branches/delete",
            params={"branch": self.name, "project": self.project.key},
        ):
            util.logger.error("%s: deletion failed", str(self))
            return False
        util.logger.info("%s: Successfully deleted", str(self))
        return True

    def url(self):
        return f"{self.endpoint.url}/dashboard?id={self.project.key}&branch={requests.utils.quote(self.name)}"

    def __audit_zero_loc(self):
        if self.last_analysis_date() is not None and self.ncloc() == 0:
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [
                problem.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self)),
                    concerned_object=self,
                )
            ]
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
        if not self.is_purgeable():
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


def get_object(branch, project_key_or_obj, data=None, endpoint=None):
    (p_key, p_obj) = projects.key_obj(project_key_or_obj)
    b_id = _uuid(p_key, branch)
    if b_id not in _BRANCHES:
        _ = Branch(p_obj, branch, data=data, endpoint=endpoint)
    return _BRANCHES[b_id]
