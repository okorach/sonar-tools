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
from typing import Optional
import math
import json

from datetime import datetime

from sonar.util import types
import sonar.util.constants as c
import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf

from sonar import settings, tasks, measures, utilities, rules

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

    def __init__(self, endpoint: pf.Platform, key: str, data: types.ApiPayload = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.name = None
        self.nbr_issues = None
        self.ncloc = None
        self._description = None
        self._last_analysis = None
        self._visibility = None
        if data is not None:
            self.reload(data)

    def reload(self, data: types.ApiPayload) -> Component:
        log.debug("Reloading %s with %s", str(self), utilities.json_dump(data))
        if not self.sq_json:
            self.sq_json = {}
        self.sq_json.update(data)
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

    def get_tags_params(self) -> dict[str, str]:
        return {"component": self.key}

    def get_subcomponents(self, strategy: str = "children", with_issues: bool = False) -> dict[str, Component]:
        """Returns component subcomponents"""
        parms = {
            "component": self.key,
            "strategy": strategy,
            "ps": 1,
            "metricKeys": "bugs,vulnerabilities,code_smells,security_hotspots",
        }
        data = json.loads(self.get("measures/component_tree", params=parms).text)
        nb_comp = utilities.nbr_total_elements(data)
        log.debug("Found %d subcomponents to %s", nb_comp, str(self))
        nb_pages = math.ceil(nb_comp / 500)
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

    def get_issues(self, filters: types.ApiParams = None) -> dict[str, object]:
        """Returns list of issues for a component, optionally on branches or/and PRs"""
        from sonar.issues import search_all

        log.info("Searching issues for %s with filters %s", str(self), str(filters))
        params = self.search_params()
        if filters is not None:
            params.update(filters)
        params["additionalFields"] = "comments"
        issue_list = search_all(endpoint=self.endpoint, params=params)
        self.nbr_issues = len(issue_list)
        return issue_list

    def count_specific_rules_issues(self, ruleset: list[str], filters: types.ApiParams = None) -> dict[str, int]:
        """Returns the count of issues of a component for a given ruleset"""
        from sonar.issues import count_by_rule

        params = self.search_params()
        if filters is not None:
            params.update(filters)
        params["facets"] = "rules"
        params["rules"] = [r.key for r in ruleset]
        return {k: v for k, v in count_by_rule(endpoint=self.endpoint, **params).items() if v > 0}

    def count_third_party_issues(self, filters: types.ApiParams = None) -> dict[str, int]:
        """Returns the count of issues of a component  corresponding to 3rd party rules"""
        return self.count_specific_rules_issues(ruleset=rules.third_party(self.endpoint), filters=filters)

    def count_instantiated_rules_issues(self, filters: types.ApiParams = None) -> dict[str, int]:
        """Returns the count of issues of a component corresponding to instantiated rules"""
        return self.count_specific_rules_issues(ruleset=rules.instantiated(self.endpoint), filters=filters)

    def get_hotspots(self, filters: types.ApiParams = None) -> dict[str, object]:
        """Returns list of hotspots for a component, optionally on branches or/and PRs"""
        from sonar.hotspots import component_filter, search

        log.info("Searching hotspots for %s with filters %s", str(self), str(filters))
        params = utilities.replace_keys(_ALT_COMPONENTS, component_filter(self.endpoint), self.search_params())
        if filters is not None:
            params.update(filters)
        return search(endpoint=self.endpoint, filters=params)

    def migration_export(self, export_settings: types.ConfigSettings) -> dict[str, any]:
        from sonar.issues import count as issue_count
        from sonar.hotspots import count as hotspot_count

        json_data = {"lastAnalysis": utilities.date_to_string(self.last_analysis())}
        lang_distrib = self.get_measure("ncloc_language_distribution")
        loc_distrib = {}
        if lang_distrib:
            loc_distrib = {m.split("=")[0]: int(m.split("=")[1]) for m in lang_distrib.split(";")}
        loc_distrib["total"] = self.loc()
        json_data["ncloc"] = loc_distrib
        json_data["analysisHistory"] = {r[0]: int(r[2]) for r in self.get_measures_history(["ncloc"])}
        if export_settings["SKIP_ISSUES"]:
            log.debug("Issues count extract skipped for %s`", str(self))
            return json_data

        tpissues = self.count_third_party_issues()
        inst_issues = self.count_instantiated_rules_issues()
        params = self.search_params()
        json_data["issues"] = {
            "thirdParty": tpissues if len(tpissues) > 0 else 0,
            "instantiatedRules": inst_issues if len(inst_issues) > 0 else 0,
            "falsePositives": issue_count(self.endpoint, issueStatuses=["FALSE_POSITIVE"], **params),
        }
        status = "accepted" if self.endpoint.version() >= (10, 2, 0) else "wontFix"
        json_data["issues"][status] = issue_count(self.endpoint, issueStatuses=[status.upper()], **params)
        json_data["hotspots"] = {
            "acknowledged": hotspot_count(self.endpoint, resolution=["ACKNOWLEDGED"], **params),
            "safe": hotspot_count(self.endpoint, resolution=["SAFE"], **params),
            "fixed": hotspot_count(self.endpoint, resolution=["FIXED"], **params),
        }
        log.debug("%s has these notable issues %s", str(self), str(json_data["issues"]))

        return json_data

    def get_measures(self, metrics_list: types.KeyList) -> dict[str, any]:
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
        meas = self.get_measures([metric])
        return meas[metric].value if metric in meas and meas[metric] and meas[metric].value is not None else fallback

    def loc(self) -> int:
        """Returns a component nbr of LOC"""
        if self.ncloc is None:
            self.ncloc = int(self.get_measure("ncloc", fallback=0))
        return self.ncloc

    def get_navigation_data(self) -> types.ApiPayload:
        """Returns a component navigation data"""
        params = utilities.replace_keys(_ALT_COMPONENTS, "component", self.search_params())
        data = json.loads(self.get("navigation/component", params=params).text)
        self.sq_json.update(data)
        return data

    def refresh(self) -> Component:
        """Refreshes a component data"""
        return self.reload(self.get_navigation_data)

    def last_analysis(self) -> datetime:
        """Returns a component last analysis"""
        if not self._last_analysis:
            self.get_navigation_data()
            if "analysisDate" in self.sq_json:
                self._last_analysis = utilities.string_to_date(self.sq_json["analysisDate"])
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
        if visibility:
            settings.set_visibility(self.endpoint, visibility=visibility, component=self)
            self._visibility = visibility

    def _audit_bg_task(self, audit_settings: types.ConfigSettings) -> list[pb.Problem]:
        """Audits project background tasks"""
        if audit_settings.get("audit.mode", "") == "housekeeper":
            return []
        if (
            not audit_settings.get("audit.projects.exclusions", True)
            and not audit_settings.get("audit.projects.analysisWarnings", True)
            and not audit_settings.get("audit.projects.failedTasks", True)
            and not audit_settings.get("audit.project.scm.disabled", True)
        ):
            log.debug("%s: Background task audit disabled, audit skipped", str(self))
            return []
        log.debug("Auditing last background task of %s", str(self))
        last_task = self.last_task()
        if last_task:
            last_task.concerned_object = self
            return last_task.audit(audit_settings)
        return []

    def last_task(self) -> Optional[tasks.Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        return tasks.search_last(component_key=self.key, endpoint=self.endpoint)

    def get_measures_history(self, metrics_list: types.KeyList) -> dict[str, str]:
        """Returns the history of a project metrics"""
        return measures.get_history(self, metrics_list)

    def api_params(self, op: str = c.LIST) -> types.ApiParams:
        from sonar.issues import component_filter

        ops = {c.LIST: {component_filter(self.endpoint): self.key}, c.SET_TAGS: {"issue": self.key}, c.GET_TAGS: {"issues": self.key}}
        return ops[op] if op in ops else ops[c.LIST]

    def search_params(self) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        return self.api_params(c.LIST)

    def component_data(self) -> dict[str, str]:
        """Returns key data"""
        return {"key": self.key, "name": self.name, "type": type(self).__name__.upper(), "branch": "", "url": self.url()}
