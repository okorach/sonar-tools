#
# sonar-tools
# Copyright (C) 2021 Olivier Korach
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
'''

    Abstraction of the SonarQube "branch" concept

'''

import datetime
import pytz
import sonarqube.sqobject as sq
import sonarqube.utilities as util
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb


class Branch(sq.SqObject):
    def __init__(self, project, name, data=None):
        super().__init__(key=name, env=project.env)
        self.name = name
        self.project = project
        self.json = data
        self._last_analysis_date = None
        self._ncloc = None

    def __str__(self):
        return f"Branch '{self.name}' of {str(self.project)}"

    def last_analysis_date(self):
        if self._last_analysis_date is None and 'analysisDate' in self.json:
            self._last_analysis_date = util.string_to_date(self.json['analysisDate'])
        return self._last_analysis_date

    def ncloc(self):
        if self._ncloc is None:
            self._ncloc = int(self.project.get_measure('ncloc', branch=self.name, fallback=0))
        return self._ncloc

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
        return self.json.get('excludedFromPurge', False)

    def is_main(self):
        return self.json.get('isMain', False)

    def delete(self, api=None, params=None):
        util.logger.info("Deleting %s", str(self))
        if not self.post('api/project_branches/delete', params={'branch': self.name, 'project': self.project.key}):
            util.logger.error("%s: deletion failed", str(self))
            return False
        util.logger.info("%s: Successfully deleted", str(self))
        return True

    def audit(self, audit_settings):
        age = self.last_analysis_age()
        if self.is_main() or age is None:
            # Main branch (not purgeable) or branch not analyzed yet
            return []
        max_age = audit_settings['audit.projects.branches.maxLastAnalysisAge']
        problems = []
        if not self.is_purgeable():
            util.logger.debug("%s is kept when inactive (not purgeable)", str(self))
        elif age > max_age:
            rule = rules.get_rule(rules.RuleId.BRANCH_LAST_ANALYSIS)
            msg = rule.msg.format(self.name, self.project.key, age)
            util.logger.warning(msg)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        else:
            util.logger.debug("%s age is %d days", str(self), age)
        return problems
