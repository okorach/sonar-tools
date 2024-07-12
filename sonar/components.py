#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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

    Abstraction of the SonarQube "component" concept

"""
from __future__ import annotations
import json

from datetime import datetime
import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf

from sonar import settings, tasks, measures, utilities

import sonar.audit.problem as pb

# Character forbidden in keys that can be used to separate a key from a post fix
KEY_SEPARATOR = " "

_ALT_COMPONENTS = ("project", "application", "portfolio")
SEARCH_API = "components/search"
_DETAILS_API = "components/show"


class Component(sq.SqObject):
    """
    Abstraction of the Sonar component concept
    """

    def __init__(self, endpoint: pf.Platform, key: str, data: dict[str, str] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.name = None
        self.nbr_issues = None
        self.ncloc = None
        self._description = None
        self._last_analysis = None
        self._tags = None
        self._visibility = None
        if data is not None:
            self.reload(data)

    def reload(self, data: dict[str, str]) -> Component:
        if self._json:
            self._json.update(data)
        else:
            self._json = data
        if "name" in data:
            self.name = data["name"]
        if "visibility" in data:
            self._visibility = data["visibility"]
        if "analysisDate" in data:
            self._last_analysis = utilities.string_to_date(data["analysisDate"])
        return self

    def __str__(self) -> str:
        """String representation of object"""
        return self.key

    def tags(self) -> list[str]:
        """Returns object tags"""
        if self._tags is not None:
            pass
        elif self._json is not None and "tags" in self._json:
            self._tags = self._json["tags"]
        else:
            data = json.loads(self.get(_DETAILS_API, params={"component": self.key}).text)
            if self._json is None:
                self._json = data["component"]
            else:
                self._json.update(data["component"])
            self._tags = self._json["tags"]
            settings.Setting.load(key=settings.COMPONENT_VISIBILITY, endpoint=self.endpoint, component=self, data=data["component"])
        return self._tags if len(self._tags) > 0 else None

    def get_subcomponents(self, strategy: str = "children", with_issues: bool = False) -> dict[str, Component]:
        """Returns component subcomponents"""
        parms = {
            "component": self.key,
            "strategy": strategy,
            "ps": 1,
            "metricKeys": "bugs,vulnerabilities,code_smells,security_hotspots",
        }
        data = json.loads(self.get("measures/component_tree", params=parms).text)
        nb_comp = data["paging"]["total"]
        log.debug("Found %d subcomponents to %s", nb_comp, str(self))
        nb_pages = (nb_comp + 500 - 1) // 500
        comp_list = {}
        parms["ps"] = 500
        for page in range(nb_pages):
            parms["p"] = page + 1
            data = json.loads(self.get("measures/component_tree", params=parms).text)
            for d in data["components"]:
                nbr_issues = 0
                for m in d["measures"]:
                    nbr_issues += int(m["value"])
                if with_issues and nbr_issues == 0:
                    log.debug("Subcomponent %s has 0 issues, skipping", d["key"])
                    continue
                comp_list[d["key"]] = Component(self.endpoint, d["key"], data=d)
                comp_list[d["key"]].nbr_issues = nbr_issues
                log.debug("Component %s has %d issues", d["key"], nbr_issues)
        return comp_list

    def get_issues(self, filters: dict[str, str] = None) -> dict[str, object]:
        """Returns list of issues for a component, optionally on branches or/and PRs"""
        from sonar.issues import component_filter, search_all

        log.info("Searching issues for %s with filters %s", str(self), str(filters))
        params = utilities.replace_keys(_ALT_COMPONENTS, component_filter(self.endpoint), self.search_params())
        if filters is not None:
            params.update(filters)
        params["additionalFields"] = "comments"
        issue_list = search_all(endpoint=self.endpoint, params=params)
        self.nbr_issues = len(issue_list)
        return issue_list

    def get_hotspots(self, filters: dict[str, str] = None) -> dict[str, object]:
        """Returns list of hotspots for a component, optionally on branches or/and PRs"""
        from sonar.hotspots import component_filter, search

        log.info("Searching hotspots for %s with filters %s", str(self), str(filters))
        params = utilities.replace_keys(_ALT_COMPONENTS, component_filter(self.endpoint), self.search_params())
        if filters is not None:
            params.update(filters)
        return search(endpoint=self.endpoint, filters=params)

    def get_measures(self, metrics_list: list[str]) -> dict[str, any]:
        """Retrieves a project list of measures

        :param list metrics_list: List of metrics to return
        :return: List of measures of a projects
        :rtype: dict
        """
        m = measures.get(self, metrics_list)
        if "ncloc" in m and m["ncloc"]:
            self.ncloc = 0 if not m["ncloc"].value else int(m["ncloc"].value)
        return m

    def get_measure(self, metric: str, fallback: int = None) -> any:
        """Returns a component measure"""
        meas = self.get_measures(metric)
        return meas[metric].value if metric in meas and meas[metric].value is not None else fallback

    def loc(self) -> int:
        """Returns a component nbr of LOC"""
        if self.ncloc is None:
            self.ncloc = int(self.get_measure("ncloc", fallback=0))
        return self.ncloc

    def refresh(self) -> Component:
        """Refreshes a component data"""
        params = utilities.replace_keys(_ALT_COMPONENTS, "component", self.search_params())
        return self.reload(json.loads(self.endpoint.get("navigation/component", params=params).text))

    def last_analysis(self) -> datetime:
        """Returns a component last analysis"""
        if not self._last_analysis:
            self.refresh()
        return self._last_analysis

    def url(self) -> str:
        """Returns a component permalink"""
        # Must be implemented in sub classes
        pass

    def visibility(self) -> str:
        """Returns a component visibility (public or private)"""
        if not self._visibility:
            self._visibility = settings.get_visibility(self.endpoint, component=self).value
        return self._visibility

    def set_visibility(self, visibility: str) -> None:
        """Sets a component visibility (public or private)"""
        settings.set_visibility(self.endpoint, visibility=visibility, component=self)
        self._visibility = visibility

    def _audit_bg_task(self, audit_settings: dict[str, str]) -> list[pb.Problem]:
        """Audits project background tasks"""
        if (
            not audit_settings.get("audit.projects.exclusions", True)
            and not audit_settings.get("audit.projects.analysisWarnings", True)
            and not audit_settings.get("audit.projects.failedTasks", True)
            and not audit_settings.get("audit.project.scm.disabled", True)
        ):
            log.debug("%s: Background task audit disabled, audit skipped", str(self))
            return []
        log.debug("Auditing last background task of %s", str(self))
        last_task = tasks.search_last(component_key=self.key, endpoint=self.endpoint)
        if last_task:
            last_task.concerned_object = self
            return last_task.audit(audit_settings)
        return []

    def get_measures_history(self, metrics_list: list[str]) -> dict[str, str]:
        """Returns the history of a project metrics"""
        return measures.get_history(self, metrics_list)

    def search_params(self) -> dict[str, str]:
        """Return params used to search/create/delete for that object"""
        from sonar.issues import component_filter

        return {component_filter(self.endpoint): self.key}

    def component_data(self) -> dict[str, str]:
        """Returns key data"""
        return {"key": self.key, "name": self.name, "type": type(self).__name__.upper(), "branch": "", "url": self.url()}
