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

import time
import json
from sonar import aggregations, env, measures, options, permissions
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}

_LIST_API = "views/list"
_SEARCH_API = "views/search"
_CREATE_API = "views/create"
_GET_API = "views/show"

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


class Portfolio(aggregations.Aggregation):
    @classmethod
    def read(cls, name, endpoint, root_key=None):
        util.logger.debug("Reading portfolio name '%s'", name)
        if root_key is None:
            data = search_by_name(endpoint=endpoint, name=name)
        else:
            data = _find_sub_portfolio_by_name(name=name, data=_OBJECTS[root_key]._json)
        if data is None:
            return None
        key = data["key"]
        if key in _OBJECTS:
            return _OBJECTS[key]
        return cls(key=key, endpoint=endpoint, data=data, root_key=root_key)

    @classmethod
    def create(cls, name, endpoint, **kwargs):
        params = {"name": name}
        for p in ("description", "parent", "key", "visibility"):
            params[p] = kwargs.get(p, None)
        util.logger.debug("Creating portfolio name '%s'", name)
        r = endpoint.post(_CREATE_API, params=params)
        if not r.ok:
            return None
        o = cls.read(name=name, endpoint=endpoint, root_key=kwargs.get("root_key", None))
        o.set_parent(kwargs.get("parent", None))
        # TODO - Allow on the fly selection mode
        return o

    @classmethod
    def load(cls, name, endpoint, data, root_key=None):
        util.logger.debug("Loading portfolio '%s'", name)
        o = cls(key=data["key"], endpoint=endpoint, data=data, root_key=root_key)
        return o

    def __init__(self, key, endpoint, data, root_key=None):
        super().__init__(key, endpoint)
        self._json = data
        self.name = data.get("name")
        self._selection_mode = self._json.get("selectionMode", None)
        self._selection_branch = self._json.get("branch", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", self._json.get("description", None))
        self.portfolio_type = self._json.get("qualifier", None)
        self._projects = None
        self._tags = None
        self._sub_portfolios = None
        self.parent_key = data.get("parentKey")
        self.root_key = self.key if root_key is None else root_key
        _OBJECTS[self.key] = self

    def __str__(self):
        if self.portfolio_type == "SVW":
            return f"subportfolio name '{self.name}'"
        return f"portfolio name '{self.name}'"

    def get_details(self):
        if self.root_key is None:
            util.logger.debug("%s has no root key, skipping details", str(self))
            return
        data = json.loads(self.get(_GET_API, params={"key": self.root_key}).text)
        if self.root_key == self.key:
            self._json.update(data)
        else:
            self._json.update(_find_sub_portfolio(self.key, data))
        self._selection_mode = self._json.get("selectionMode", None)
        self._selection_branch = self._json.get("branch", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", self._json.get("description", None))
        self.portfolio_type = self._json.get("qualifier", None)

    def set_parent(self, parent_key):
        util.logger.debug("Setting parent of %s to '%s'", str(self), parent_key)
        self.parent_key = parent_key

    def url(self):
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def is_sub_portfolio(self):
        return self.portfolio_type == "SVW"

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
        self.get_details()
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
        if current_projects is None or project_list is None:
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

    def set_selection_mode(self, selection_mode, projects=None, regexp=None, tags=None, branch=None):
        if selection_mode == SELECTION_MODE_MANUAL:
            self.set_projects(projects)
        elif selection_mode == SELECTION_MODE_TAGS:
            self.set_tag_mode(tags=tags, branch=branch)
        elif selection_mode == SELECTION_MODE_REGEXP:
            self.set_regexp_mode(regexp=regexp, branch=branch)
        elif selection_mode == SELECTION_MODE_OTHERS:
            self.set_remaining_projects_mode(branch)
        elif selection_mode == SELECTION_MODE_NONE:
            self.set_node_mode()
        else:
            util.logger.error("Invalid portfolio project selection mode %s during import, skipped...", selection_mode)

    def add_subportfolio(self, key):
        if not exists(key, self.endpoint):
            util.logger.warning("Can't add in %s the subportfolio key '%s' by reference, it does not exists", str(self), key)
            return False
        r = self.post("views/add_portfolio", params={"portfolio": self.key, "reference": key})
        self.recompute()
        time.sleep(1)
        return r.ok

    def recompute(self):
        self.post("views/refresh", params={"key": self.root_key})

    def update(self, data, root_key):
        util.logger.info("Updating %s", str(self))
        self.set_permissions(data.get("permissions", {}))
        selection_mode = data.get(_PROJECT_SELECTION_MODE, "NONE")
        branch = data.get(_PROJECT_SELECTION_BRANCH, None)
        regexp = data.get(_PROJECT_SELECTION_REGEXP, None)
        tags = data.get(_PROJECT_SELECTION_TAGS, None)
        projects = data.get("projects", None)
        self.root_key = root_key
        self.set_selection_mode(selection_mode=selection_mode, projects=projects, branch=branch, regexp=regexp, tags=tags)
        for subp in data.get("subPortfolios", []):
            key_list = [p["key"] for p in self.sub_portfolios().get("subPortfolios", [])]
            util.logger.debug("%s subport list = %s", str(self), str(key_list))
            if subp.get("byReference", False):
                o_subp = get_object(key=subp["key"], endpoint=self.endpoint)
                if o_subp is not None:
                    if o_subp.key not in key_list:
                        self.add_subportfolio(o_subp.key)
                    o_subp.update(subp, root_key)
            else:
                name = subp.pop("name")
                get_list(endpoint=self.endpoint)
                o = get_object(key=subp["key"], endpoint=self.endpoint)
                if o is None:
                    util.logger.info("Creating subportfolio %s from %s", name, util.json_dump(subp))
                    o = Portfolio.create(name=name, endpoint=self.endpoint, parent=self.key, root_key=root_key, **subp)
                    if o is None:
                        util.logger.info("Can't create subport %s to parent %s", name, self.key)
                o.set_parent(self.key)
                o.update(subp, root_key)


def count(endpoint=None):
    return aggregations.count(api=_SEARCH_API, endpoint=endpoint)


def search(endpoint, params=None):
    portfolio_list = {}
    edition = env.edition(ctxt=endpoint)
    if edition not in ("enterprise", "datacenter"):
        util.logger.info("No portfolios in %s edition", edition)
    else:
        portfolio_list = sq.search_objects(
            api=_SEARCH_API,
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
    problems = []
    for _, p in search(endpoint, params={"qualifiers": "VW"}).items():
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
    for k in ("visibility", "qualifier", "branch", "referencedBy", "subViews", "selectedProjects"):
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
    util.logger.debug("Getting subpotofolo from %s", util.json_dump(json_data))
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
    util.logger.debug("Reading portfolio list")
    return search(endpoint=endpoint)


def get_object(key, endpoint=None):
    if key in _OBJECTS:
        return _OBJECTS.get(key, None)
    data = search_by_key(endpoint=endpoint, key=key)
    if data is not None:
        return Portfolio.load(name=data["name"], endpoint=endpoint, data=data)
    return None


def exists(key, endpoint):
    return get_object(key, endpoint) is not None


def import_config(endpoint, config_data):
    if "portfolios" not in config_data:
        util.logger.info("No portfolios to import")
        return
    util.logger.info("Importing portfolios - pass 1: Create all top level portfolios")
    search(endpoint=endpoint)
    # First pass to create all top level porfolios that may be referenced
    for key, data in config_data["portfolios"].items():
        util.logger.info("Importing portfolios key '%s'", key)
        o = get_object(key, endpoint)
        if o is None:
            newdata = data.copy()
            name = newdata.pop("name")
            o = Portfolio.create(name=name, endpoint=endpoint, key=key, root_key=key, **newdata)
    # recompute(endpoint=endpoint)
    #time.sleep(10)
    # Second pass to define hierarchies
    util.logger.info("Importing portfolios - pass 2: Creating sub-portfolios")
    for key, data in config_data["portfolios"].items():
        o = get_object(key, endpoint)
        if o is None:
            util.logger.warning("Can't find portfolio key '%s', name '%s'", key, data["name"])
        o.update(data, root_key=key)


def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, _SEARCH_API, "components")


def search_by_key(endpoint, key):
    return util.search_by_key(endpoint, key, _SEARCH_API, "components")


def export(endpoint):
    if endpoint.edition() in ("community", "developer"):
        util.logger.info("No portfolios in community and developer editions")
        return None
    util.logger.info("Exporting portfolios")
    nb_portfolios = count(endpoint=endpoint)
    i = 0
    exported_portfolios = {}
    for k, p in search(endpoint).items():
        if not p.is_sub_portfolio():
            exported_portfolios[k] = p.export()
            exported_portfolios[k].pop("key")
        else:
            util.logger.info("Skipping export of %s", str(p))
        i += 1
        if i % 50 == 0 or i == nb_portfolios:
            util.logger.info("Exported %d/%d portfolios (%d%%)", i, nb_portfolios, (i * 100) // nb_portfolios)
    return exported_portfolios


def recompute(endpoint):
    endpoint.post("views/refresh")

def _find_sub_portfolio(key, data):
    for subp in data.get("subViews", []):
        if subp["key"] == key:
            return subp
        child = _find_sub_portfolio(key, subp)
        if child is not None:
            return child
    return None


def _find_sub_portfolio_by_name(name, data):
    for subp in data.get("subViews", []):
        if subp["name"] == name:
            return subp
        child = _find_sub_portfolio(name, subp)
        if child is not None:
            return child
    return None
