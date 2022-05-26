#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

    Abstraction of the SonarQube "portfolio" concept

"""
import json
from sonar import aggregations, env, measures, options, permissions
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}

LIST_API = "views/list"
SEARCH_API = "views/search"
GET_API = "views/show"
MAX_PAGE_SIZE = 500
PORTFOLIO_QUALIFIER = "VW"

SELECTION_MODE_MANUAL = "MANUAL"
SELECTION_MODE_REGEXP = "REGEXP"
SELECTION_MODE_TAGS = "TAGS"
SELECTION_MODE_OTHERS = "REST"
SELECTION_MODE_NONE = "NONE"

_PROJECT_SELECTION_MODE = "projectSelectionMode"
_PROJECT_SELECTION_REGEXP = "projectSelectionRegexp"
_PROJECT_SELECTION_TAGS = "projectSelectionTags"


class Portfolio(aggregations.Aggregation):
    def __init__(self, key, endpoint, data=None):
        super().__init__(key, endpoint)
        self._selection_mode = None
        self._qualifier = None
        self._projects = None
        self._tags = None
        self._regexp = None
        self._sub_portfolios = None
        self._load(data)
        _OBJECTS[key] = self

    def __str__(self):
        return f"portfolio key '{self.key}'"

    def _load(self, data=None, api=None, key_name="key"):
        """Loads a portfolio object with contents of data"""
        super()._load(data=data, api=GET_API, key_name="key")
        self._selection_mode = self._json.get("selectionMode", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", None)
        self._qualifier = self._json.get("qualifier", None)

    def _load_full(self):
        if self._qualifier == "VW":
            self._json = None
            self._load(data=None)

    def url(self):
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def selection_mode(self):
        if self._selection_mode is None:
            self._load()
        return self._selection_mode

    def projects(self):
        if self._selection_mode != SELECTION_MODE_MANUAL:
            self._projects = None
        elif self._projects is None:
            if "selectedProjects" not in self._json:
                self._load_full()
            self._projects = {}
            if self.endpoint.version() >= (9, 3, 0):
                for p in self._json["selectedProjects"]:
                    if "selectedBranches" in p:
                        self._projects[p["projectKey"]] = ", ".join(p["selectedBranches"])
                    else:
                        self._projects[p["projectKey"]] = options.DEFAULT
            else:
                for p in self._json["projects"]:
                    self._projects[p] = options.DEFAULT
        return self._projects

    def sub_portfolios(self):
        self._sub_portfolios = _sub_portfolios(self._json, self.endpoint.version())
        return self._sub_portfolios

    def regexp(self):
        if self.selection_mode() != SELECTION_MODE_REGEXP:
            self._regexp = None
        elif self._regexp is None:
            self._regexp = self._json["regexp"]
        return self._regexp

    def tags(self):
        if self.selection_mode() != SELECTION_MODE_TAGS:
            self._tags = None
        elif self._tags is None:
            self._tags = ", ".join(self._json["tags"])
        return self._tags

    def get_components(self):
        resp = env.get(
            "measures/component_tree",
            ctxt=self.endpoint,
            params={
                "component": self.key,
                "metricKeys": "ncloc",
                "strategy": "children",
                "ps": 500,
            },
        )
        comp_list = {}
        for c in json.loads(resp.text)["components"]:
            comp_list[c["key"]] = c
        return comp_list

    def delete(self, api="views/delete", params=None):
        _ = env.post("views/delete", ctxt=self.endpoint, params={"key": self.key})
        return True

    def _audit_empty(self, audit_settings):
        if not audit_settings["audit.portfolios.empty"]:
            util.logger.debug("Auditing empty portfolios is disabled, skipping...")
            return []
        return self._audit_empty_aggregation(broken_rule=rules.RuleId.PORTFOLIO_EMPTY)

    def _audit_singleton(self, audit_settings):
        if not audit_settings["audit.portfolios.singleton"]:
            util.logger.debug("Auditing singleton portfolios is disabled, skipping...")
            return []
        return self._audit_singleton_aggregation(broken_rule=rules.RuleId.PORTFOLIO_SINGLETON)

    def audit(self, audit_settings):
        util.logger.info("Auditing %s", str(self))
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings)

    def get_measures(self, metrics_list):
        m = measures.get(self.key, metrics_list, endpoint=self.endpoint)
        if "ncloc" in m:
            self._ncloc = 0 if m["ncloc"] is None else int(m["ncloc"])
        return m

    def dump_data(self, **opts):
        self._load_full()
        data = {
            "type": "portfolio",
            "key": self.key,
            "name": self.name,
            "ncloc": self.ncloc(),
        }
        if opts.get(options.WITH_URL, False):
            data["url"] = self.url()
        if opts.get(options.WITH_LAST_ANALYSIS, False):
            data["lastAnalysis"] = self.last_analysis()
        return data

    def export(self):
        util.logger.info("Exporting %s", str(self))
        self._load_full()
        json_data = {
            "key": self.key,
            "name": self.name,
            "description": self._description,
            _PROJECT_SELECTION_MODE: self.selection_mode(),
            "visibility": self.visibility(),
            # 'projects': self.projects(),
            _PROJECT_SELECTION_REGEXP: self.regexp(),
            _PROJECT_SELECTION_TAGS: self.tags(),
            "permissions": permissions.export(self.endpoint, self.key),
        }
        json_data.update(self.sub_portfolios())
        if self.selection_mode() != "MANUAL":
            json_data["branch"] = self._json.get("branch", None)

        return util.remove_nones(json_data)


def count(endpoint=None):
    return aggregations.count(api=SEARCH_API, endpoint=endpoint)


def search(endpoint=None, params=None):
    portfolio_list = {}
    edition = env.edition(ctxt=endpoint)
    if edition not in ("enterprise", "datacenter"):
        util.logger.info("No portfolios in %s edition", edition)
    else:
        if params is None:
            params = {"qualifiers": "VW"}
        portfolio_list = sq.search_objects(
            api="views/search",
            params=params,
            returned_field="components",
            key_field="key",
            object_class=Portfolio,
            endpoint=endpoint,
        )
    return portfolio_list


def get(key, sqenv=None):
    if key not in _OBJECTS:
        _ = Portfolio(key=key, endpoint=sqenv)
    return _OBJECTS[key]


def audit(audit_settings, endpoint=None):
    if not audit_settings["audit.portfolios"]:
        util.logger.debug("Auditing portfolios is disabled, skipping...")
        return []
    util.logger.info("--- Auditing portfolios ---")
    plist = search(endpoint)
    problems = []
    for _, p in plist.items():
        problems += p.audit(audit_settings)
    return problems


def loc_csv_header(**kwargs):
    arr = ["# Portfolio Key"]
    if kwargs[options.WITH_NAME]:
        arr.append("Portfolio name")
    arr.append("LoC")
    if kwargs[options.WITH_LAST_ANALYSIS]:
        arr.append("Last Recomputation")
    if kwargs[options.WITH_URL]:
        arr.append("URL")
    return arr


def __cleanup_portfolio_json(p):
    for k in (
        "visibility",
        "qualifier",
        "branch",
        "referencedBy",
        "subViews",
        "selectedProjects",
    ):
        p.pop(k, None)
    if "branch" in p:
        p["projectBranch"] = p.pop("branch")
    if "selectionMode" in p:
        if p["selectionMode"] == SELECTION_MODE_REGEXP:
            p[_PROJECT_SELECTION_REGEXP] = p.pop("regexp")
        elif p["selectionMode"] == SELECTION_MODE_TAGS:
            p[_PROJECT_SELECTION_REGEXP] = ", ".join(p.pop("tags"))
        p[_PROJECT_SELECTION_MODE] = p.pop("selectionMode")


def _sub_portfolios(json_data, version):
    subport = []
    if "subViews" in json_data and len(json_data["subViews"]) > 0:
        for p in json_data["subViews"]:
            qual = p.pop("qualifier", "SVW")
            p["byReference"] = qual == "VW"
            if qual == "VW":
                p["key"] = p.pop("originalKey")
                for k in ("name", "desc"):
                    p.pop(k, None)
            p.update(_sub_portfolios(p, version))
            __cleanup_portfolio_json(p)
            subport.append(p)
    projects = _projects(json_data, version)
    ret = {}
    if projects is not None and len(projects) > 0:
        ret["projects"] = projects
    if len(subport) > 0:
        ret["subPortfolios"] = subport
    return ret


def _projects(json_data, version):
    if "selectionMode" not in json_data or json_data["selectionMode"] != SELECTION_MODE_MANUAL:
        return None
    projects = {}
    if version >= (9, 3, 0):
        for p in json_data["selectedProjects"]:
            if "selectedBranches" in p:
                projects[p["projectKey"]] = ", ".join(p["selectedBranches"])
            else:
                projects[p["projectKey"]] = options.DEFAULT
    else:
        for p in json_data["projects"]:
            projects[p] = options.DEFAULT
    return projects
