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
SELECTION_MODES = (SELECTION_MODE_MANUAL, SELECTION_MODE_REGEXP, SELECTION_MODE_TAGS, SELECTION_MODE_OTHERS, SELECTION_MODE_NONE)

_PROJECT_SELECTION_MODE = "projectSelectionMode"
_PROJECT_SELECTION_BRANCH = "projectSelectionBranch"
_PROJECT_SELECTION_REGEXP = "projectSelectionRegexp"
_PROJECT_SELECTION_TAGS = "projectSelectionTags"

_CREATE_API = "views/create"
_GET_API = "views/show"


class Portfolio(aggregations.Aggregation):
    @classmethod
    def read(cls, name, endpoint):
        util.logger.debug("Reading portfolio name '%s'", name)
        data = search_by_name(endpoint=endpoint, name=name)
        if data is None:
            return None
        key = data["key"]
        if key in _OBJECTS:
            return _OBJECTS[key]
        return cls(key=key, endpoint=endpoint, data=data)

    @classmethod
    def create(cls, name, endpoint, **kwargs):
        params = {"name": name}
        for p in ("description", "parent", "key", "visibility"):
            params[p] = kwargs.get(p, None)
        util.logger.debug("Creating portfolio name '%s'", name)
        r = endpoint.post(_CREATE_API, params=params)
        if not r.ok:
            return None
        o = cls.read(name=name, endpoint=endpoint)
        # TODO - Allow on the fly selection mode
        return o

    @classmethod
    def load(cls, name, endpoint, data):
        util.logger.debug("Loading portfolio '%s'", name)
        return cls(key=data["key"], endpoint=endpoint, data=data)

    def __init__(self, key, endpoint, data):
        super().__init__(key, endpoint)
        self._json = data
        self.name = data.get("name")
        self._selection_mode = self._json.get("selectionMode", None)
        self._selection_branch = self._json.get("branch", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", self._json.get("description", None))
        self._qualifier = self._json.get("qualifier", None)
        self._projects = None
        self._tags = None
        self._sub_portfolios = None
        _OBJECTS[self.key] = self

    def __str__(self):
        return f"portfolio name '{self.name}'"

    def get_details(self):
        data = json.loads(self.get("views/show", params={"key": self.key}).text)
        self._json.update(data)
        self._selection_mode = self._json.get("selectionMode", None)
        self._selection_branch = self._json.get("branch", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", self._json.get("description", None))
        self._qualifier = self._json.get("qualifier", None)

    def url(self):
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def selection_mode(self):
        return self._selection_mode

    def projects(self):
        if self._selection_mode != SELECTION_MODE_MANUAL:
            self._projects = None
            return self._projects
        if self._projects is not None:
            return self._projects
        if "selectedProjects" not in self._json:
            self.get_details()
        self._projects = {}
        if self.endpoint.version() < (9, 3, 0):
            for p in self._json["projects"]:
                self._projects[p] = options.DEFAULT
            return self._projects
        for p in self._json["selectedProjects"]:
            if "selectedBranches" in p:
                self._projects[p["projectKey"]] = util.list_to_csv(p["selectedBranches"], ", ", True)
            else:
                self._projects[p["projectKey"]] = options.DEFAULT
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
            self._tags = util.list_to_csv(self._json["tags"], ", ")
        return self._tags

    def get_components(self):
        data = json.loads(
            self.get(
                "measures/component_tree",
                params={
                    "component": self.key,
                    "metricKeys": "ncloc",
                    "strategy": "children",
                    "ps": 500,
                },
            ).text
        )
        comp_list = {}
        for c in data["components"]:
            comp_list[c["key"]] = c
        return comp_list

    def delete(self, api="views/delete", params=None):
        _ = self.post("views/delete", params={"key": self.key})
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
        self.get_details()
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
        self.get_details()
        json_data = {
            "key": self.key,
            "name": self.name,
            "description": self._description,
            _PROJECT_SELECTION_MODE: self.selection_mode(),
            "visibility": self.visibility(),
            # 'projects': self.projects(),
            _PROJECT_SELECTION_REGEXP: self.regexp(),
            _PROJECT_SELECTION_BRANCH: self._selection_branch,
            _PROJECT_SELECTION_TAGS: util.list_to_csv(self.tags(), separator=", "),
            "permissions": permissions.export(self.endpoint, self.key),
        }
        json_data.update(self.sub_portfolios())

        return util.remove_nones(json_data)

    def set_permissions(self, portfolio_perms):
        if portfolio_perms is None or len(portfolio_perms) == 0:
            return
        permissions.set_permissions(self.endpoint, portfolio_perms, project_key=self.key)

    def set_component_tags(self, tags, api):
        util.logger.warning("Can't set tags on portfolios, operation skipped...")

    def set_projects(self, project_list):
        current_projects = self.projects()
        self.post("views/set_manual_mode", params={"portfolio": self.key})
        if current_projects is None:
            return
        current_projects = current_projects.keys()
        for proj in project_list:
            params = {"key": self.key, "project": proj}
            # FIXME: Handle portfolios with several branches of same project
            if proj not in current_projects:
                util.logger.info("Adding project '%s' to %s", proj, str(self))
                self.post("views/add_project", params=params)
                if project_list[proj] != options.DEFAULT:
                    util.logger.info("Adding project '%s' branch '%s' to %s", proj, project_list[proj], str(self))
                    params["branch"] = project_list["proj"]
                    self.post("views/add_project_branch", params=params)
            elif project_list[proj] != current_projects[proj]:
                util.logger.info("Adding project '%s' branch '%s' to %s", proj, project_list[proj], str(self))
                params["branch"] = project_list["proj"]
                self.post("views/add_project_branch", params=params)
            else:
                util.logger.info("Won't add project '%s' branch '%s' to %s, it's already added", proj, project_list[proj], str(self))
            self.post("views/add_project", params={"application": self.key, "project": proj})

    def set_tag_mode(self, tags, branch):
        self.post("views/set_tags_mode", params={"portfolio": self.key, "tags": util.list_to_csv(tags), "branch": branch})

    def set_regexp_mode(self, regexp, branch):
        self.post("views/set_regexp_mode", params={"portfolio": self.key, "regexp": regexp, "branch": branch})

    def set_remaining_projects_mode(self, branch):
        self.post("views/set_remaining_projects_mode", params={"portfolio": self.key, "branch": branch})

    def set_node_mode(self):
        self.post("views/set_none_mode", params={"portfolio": self.key})

    def update(self, data):
        self.set_permissions(data.get("permissions", {}))
        selection_mode = data[_PROJECT_SELECTION_MODE]
        if selection_mode == SELECTION_MODE_MANUAL:
            self.set_projects(data.get("projects", {}))
        elif selection_mode == SELECTION_MODE_TAGS:
            self.set_tag_mode(data[_PROJECT_SELECTION_TAGS], data.get(_PROJECT_SELECTION_BRANCH, None))
        elif selection_mode == SELECTION_MODE_REGEXP:
            self.set_regexp_mode(data[_PROJECT_SELECTION_REGEXP], data.get(_PROJECT_SELECTION_BRANCH, None))
        elif selection_mode == SELECTION_MODE_OTHERS:
            self.set_remaining_projects_mode(data.get(_PROJECT_SELECTION_BRANCH, None))
        elif selection_mode == SELECTION_MODE_NONE:
            self.set_node_mode()
        else:
            util.logger.error("Invalid portfolio project selection mode %s during import, skipped...", selection_mode)


def count(endpoint=None):
    return aggregations.count(api=SEARCH_API, endpoint=endpoint)


def search(endpoint, params=None):
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
            p[_PROJECT_SELECTION_REGEXP] = util.list_to_csv(p.pop("tags"), ", ")
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
                projects[p["projectKey"]] = util.list_to_csv(p["selectedBranches"], ", ", True)
            else:
                projects[p["projectKey"]] = options.DEFAULT
    else:
        for p in json_data["projects"]:
            projects[p] = options.DEFAULT
    return projects


def get_list(endpoint):
    return search(endpoint=endpoint)


def get_object(key, endpoint=None):
    if key not in _OBJECTS:
        get_list(endpoint)
    return _OBJECTS.get(key, None)


def import_config(endpoint, config_data):
    if "portfolios" not in config_data:
        util.logger.info("No portfolios to import")
        return
    util.logger.info("Importing portfolios")
    search(endpoint=endpoint)
    for key, data in config_data["portfolios"].items():
        util.logger.info("Importing portfolios key '%s'", key)
        o = get_object(key, endpoint)
        if o is None:
            Portfolio.create(name=data.pop("name"), endpoint=endpoint, **data)
        o.update(data)

def search_by_name(endpoint, name):
    for data in json.load(endpoint.get("views/list").text):
        if data["name"] == name:
            return data
    return None
