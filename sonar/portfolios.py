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

from sonar import aggregations, measures, options
from sonar.permissions import portfolio_permissions
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

_IMPORTABLE_PROPERTIES = (
    "key",
    "name",
    "description",
    _PROJECT_SELECTION_MODE,
    "visibility",
    _PROJECT_SELECTION_REGEXP,
    _PROJECT_SELECTION_BRANCH,
    _PROJECT_SELECTION_TAGS,
    "permissions",
    "subPortfolios",
    "projects",
)


class Portfolio(aggregations.Aggregation):
    @classmethod
    def read(cls, name, endpoint, root_key=None):
        util.logger.debug("Reading portfolio name '%s'", name)
        # if root_key is None:
        data = search_by_name(endpoint=endpoint, name=name)
        # else:
        #    data = _find_sub_portfolio_by_name(name=name, data=_OBJECTS[root_key]._json)
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
        self._selection_mode = self._json.pop("selectionMode", None)
        self._selection_branch = self._json.pop("branch", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", self._json.get("description", None))
        self.portfolio_type = self._json.get("qualifier", None)
        self._projects = None
        self._tags = self._json.pop("tags", [])
        self._visibility = self._json.get("visibility")
        self._sub_portfolios = None
        self._permissions = None
        self.parent_key = data.get("parentKey")
        self.root_key = self.key if root_key is None else root_key
        _OBJECTS[self.key] = self

    def __str__(self):
        return f"subportfolio '{self.key}'" if self.portfolio_type == "SVW" else f"portfolio '{self.key}'"

    def get_details(self):
        util.logger.debug("Updating details for %s root key %s", str(self), self.root_key)
        data = json.loads(self.get(_GET_API, params={"key": self.root_key}).text)
        if self.root_key == self.key:
            self._json.update(data)
        else:
            self._json.update(_find_sub_portfolio(self.key, data))
        self._selection_mode = self._json.pop("selectionMode", None)
        self._selection_branch = self._json.pop("branch", None)
        self._regexp = self._json.get("regexp", None)
        self._description = self._json.get("desc", self._json.get("description", None))
        self._tags = self._json.pop("tags", [])
        self.portfolio_type = self._json.get("qualifier", None)
        # self._visibility = self._json.get("visibility")

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
            util.logger.debug("%s: Not manual mode, no projects", str(self))
            self._projects = {}
            return self._projects
        if self._projects is not None:
            util.logger.debug("%s: Projects already set, returning %s", str(self), str(self._projects))
            return self._projects
        if "selectedProjects" not in self._json:
            self.get_details()
        self._projects = {}
        util.logger.debug("%s: Read projects %s", str(self), str(self._projects))
        if self.endpoint.version() < (9, 3, 0):
            for p in self._json.get("projects", {}):
                self._projects[p] = options.DEFAULT
            return self._projects
        for p in self._json.get("selectedProjects", {}):
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
            self._tags = self._json.pop("tags", [])
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
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings) + self._audit_bg_task(audit_settings)

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

    def export(self, full=False):
        util.logger.info("Exporting %s", str(self))
        self.get_details()
        json_data = self._json
        json_data.update(self.sub_portfolios())
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": None if self._description == "" else self._description,
                _PROJECT_SELECTION_MODE: self.selection_mode(),
                "visibility": self._visibility,
                _PROJECT_SELECTION_REGEXP: self.regexp(),
                _PROJECT_SELECTION_BRANCH: self._selection_branch,
                _PROJECT_SELECTION_TAGS: util.list_to_csv(self.tags(), separator=", "),
                "permissions": self.permissions().export(),
            }
        )
        if self.selection_mode() == SELECTION_MODE_MANUAL:
            json_data["projects"] = self.projects()

        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def permissions(self):
        if self._permissions is None and self.portfolio_type == "VW":
            # No permissions for SVW
            self._permissions = portfolio_permissions.PortfolioPermissions(self)
        return self._permissions

    def set_permissions(self, portfolio_perms):
        if self.portfolio_type == "VW":
            # No permissions for SVW)
            self.permissions().set(portfolio_perms)

    def set_component_tags(self, tags, api):
        util.logger.warning("Can't set tags on portfolios, operation skipped...")

    def set_projects(self, project_list):
        self.post("views/set_manual_mode", params={"portfolio": self.key})
        self._selection_mode = SELECTION_MODE_MANUAL
        current_projects = self.projects()
        current_project_keys = list(current_projects.keys())
        util.logger.debug("Project list = %s", str(project_list))
        if project_list is None:
            return False
        util.logger.debug("Current Project list = %s", str(current_projects))
        ok = True
        for proj, branches in project_list.items():
            if proj not in current_project_keys:
                r = self.post("views/add_project", params={"key": self.key, "project": proj}, exit_on_error=False)
                ok = ok and r.ok
                current_projects[proj] = options.DEFAULT
            else:
                util.logger.debug("Won't add project '%s' branch '%s' to %s, it's already added", proj, project_list[proj], str(self))
            for branch in util.csv_to_list(branches):
                if branch != options.DEFAULT and branch not in util.csv_to_list(current_projects[proj]):
                    if self.endpoint.version() >= (9, 2, 0):
                        util.logger.debug("Adding project '%s' branch '%s' to %s", proj, str(branch), str(self))
                        r = self.post("views/add_project_branch", params={"key": self.key, "project": proj, "branch": branch}, exit_on_error=False)
                        ok = ok and r.ok
                    else:
                        util.logger.warning("Can't add branch '%s' of project '%s' in a portfolio on SonarQube < 9.2", branch, proj)
                else:
                    util.logger.debug("Won't add project '%s' branch '%s' to %s, it's already added", proj, project_list[proj], str(self))
        return ok

    def set_tag_mode(self, tags, branch):
        self.post("views/set_tags_mode", params={"portfolio": self.key, "tags": util.list_to_csv(tags), "branch": branch})

    def set_regexp_mode(self, regexp, branch):
        self.post("views/set_regexp_mode", params={"portfolio": self.key, "regexp": regexp, "branch": branch})

    def set_remaining_projects_mode(self, branch):
        self.post("views/set_remaining_projects_mode", params={"portfolio": self.key, "branch": branch})

    def none(self):
        # Hack: API change between 9.0 and 9.1
        if self.endpoint.version() < (9, 1, 0):
            self.post("views/mode", params={"key": self.key, "selectionMode": "NONE"})
        else:
            self.post("views/set_none_mode", params={"portfolio": self.key})

    def set_selection_mode(self, selection_mode, projects=None, regexp=None, tags=None, branch=None):
        util.logger.debug("Setting selection mode %s for %s", str(selection_mode), str(self))
        if selection_mode == SELECTION_MODE_MANUAL:
            self.set_projects(projects)
        elif selection_mode == SELECTION_MODE_TAGS:
            self.set_tag_mode(tags=tags, branch=branch)
        elif selection_mode == SELECTION_MODE_REGEXP:
            self.set_regexp_mode(regexp=regexp, branch=branch)
        elif selection_mode == SELECTION_MODE_OTHERS:
            self.set_remaining_projects_mode(branch)
        elif selection_mode == SELECTION_MODE_NONE:
            self.none()
        else:
            util.logger.error("Invalid portfolio project selection mode %s during import, skipped...", selection_mode)
            return self
        self._selection_mode = selection_mode
        return self

    def add_subportfolio(self, key, name=None, by_ref=False):
        if not exists(key, self.endpoint):
            util.logger.warning("Can't add in %s the subportfolio key '%s' by reference, it does not exists", str(self), key)
            return False
        if self.endpoint.version() >= (9, 3, 0):
            r = self.post("views/add_portfolio", params={"portfolio": self.key, "reference": key})
        elif by_ref:
            r = self.post("views/add_local_view", params={"key": self.key, "ref_key": key})
        else:
            r = self.post("views/add_sub_view", params={"key": self.key, "name": key, "subKey": key})
        if not by_ref:
            self.recompute()
            time.sleep(0.5)
        return r.ok

    def recompute(self):
        util.logger.debug("Recomputing %s", str(self))
        self.post("views/refresh", params={"key": self.root_key})

    def update(self, data, root_key):
        util.logger.debug("Updating %s with %s", str(self), util.json_dump(data))
        if "byReference" not in data or not data["byReference"]:
            self.set_permissions(data.get("permissions", {}))
            selection_mode = data.get(_PROJECT_SELECTION_MODE, "NONE")
            branch = data.get(_PROJECT_SELECTION_BRANCH, None)
            regexp = data.get(_PROJECT_SELECTION_REGEXP, None)
            tags = data.get(_PROJECT_SELECTION_TAGS, None)
            projects = data.get("projects", None)
            self.root_key = root_key
            self.set_selection_mode(selection_mode=selection_mode, projects=projects, branch=branch, regexp=regexp, tags=tags)
        else:
            util.logger.debug("Skipping setting portfolio details, it's a reference")

        for key, subp in data.get("subPortfolios", {}).items():
            key_list = list(self.sub_portfolios().get("subPortfolios", {}).keys())
            if subp.get("byReference", False):
                o_subp = get_object(key=key, endpoint=self.endpoint)
                if o_subp is not None:
                    if o_subp.key not in key_list:
                        self.add_subportfolio(o_subp.key, name=o_subp.name, by_ref=True)
                    o_subp.update(subp, root_key)
            else:
                name = subp.pop("name")
                get_list(endpoint=self.endpoint)
                o = get_object(key=key, endpoint=self.endpoint)
                if o is None:
                    util.logger.info("Creating subportfolio %s from %s", name, util.json_dump(subp))
                    o = Portfolio.create(name=name, endpoint=self.endpoint, parent=self.key, root_key=root_key, **subp)
                    if o is None:
                        util.logger.info("Can't create sub-portfolio '%s' to parent %s", name, self.key)
                o.set_parent(self.key)
                o.update(subp, root_key)


def count(endpoint=None):
    return aggregations.count(api=_SEARCH_API, endpoint=endpoint)


def get_list(endpoint, key_list=None):
    if key_list is None or len(key_list) == 0:
        util.logger.info("Listing portfolios")
        return search(endpoint=endpoint)
    object_list = {}
    for key in util.csv_to_list(key_list):
        object_list[key] = get_object(key, endpoint=endpoint)
        if object_list[key] is None:
            raise options.NonExistingObjectError(key, f"Portfolio key '{key}' does not exist")
    return object_list


def search(endpoint, params=None):
    portfolio_list = {}
    if endpoint.edition() not in ("enterprise", "datacenter"):
        util.logger.info("No portfolios in %s edition", endpoint.edition())
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


def audit(audit_settings, endpoint=None, key_list=None):
    if not audit_settings["audit.portfolios"]:
        util.logger.debug("Auditing portfolios is disabled, skipping...")
        return []
    util.logger.info("--- Auditing portfolios ---")
    problems = []
    for p in get_list(endpoint=endpoint, key_list=key_list).values():
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
            p[_PROJECT_SELECTION_TAGS] = util.list_to_csv(p.pop("tags"), ", ")
        p[_PROJECT_SELECTION_MODE] = p.pop("selectionMode")


def _sub_portfolios(json_data, version):
    subport = {}
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
            subport[p.pop("key")] = p
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


def get_object(key, endpoint=None):
    if key in _OBJECTS:
        return _OBJECTS.get(key, None)
    data = search_by_key(endpoint=endpoint, key=key)
    if data is not None:
        return Portfolio.load(name=data["name"], endpoint=endpoint, data=data)
    return None


def exists(key, endpoint):
    return get_object(key, endpoint) is not None


def import_config(endpoint, config_data, key_list=None):
    if "portfolios" not in config_data:
        util.logger.info("No portfolios to import")
        return
    if endpoint.edition() in ("community", "developer"):
        util.logger.warning("Can't import portfolios on a %s edition", endpoint.edition())
        return

    util.logger.info("Importing portfolios - pass 1: Create all top level portfolios")
    search(endpoint=endpoint)
    # First pass to create all top level porfolios that may be referenced
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["portfolios"].items():
        if new_key_list and key not in new_key_list:
            continue
        util.logger.info("Importing portfolio key '%s'", key)
        o = get_object(key, endpoint)
        if o is None:
            newdata = data.copy()
            name = newdata.pop("name")
            o = Portfolio.create(name=name, endpoint=endpoint, key=key, root_key=key, **newdata)
        nbr_creations = __create_portfolio_hierarchy(endpoint=endpoint, data=data, parent_key=key)
        # Hack: When subportfolios are created, recompute is needed to get them in the
        # api/views/search results
        if nbr_creations > 0:
            o.recompute()
            # Sleep 500ms per created portfolio
            time.sleep(nbr_creations * 500 / 1000)
    # Second pass to define hierarchies
    util.logger.info("Importing portfolios - pass 2: Creating sub-portfolios")
    for key, data in config_data["portfolios"].items():
        if new_key_list and key not in new_key_list:
            continue
        o = get_object(key, endpoint)
        if o is None:
            util.logger.error("Can't find portfolio key '%s', name '%s'", key, data["name"])
        else:
            o.update(data, root_key=key)


def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, _SEARCH_API, "components")


def search_by_key(endpoint, key):
    return util.search_by_key(endpoint, key, _SEARCH_API, "components")


def export(endpoint, key_list=None, full=False):
    if endpoint.edition() in ("community", "developer"):
        util.logger.info("No portfolios in community and developer editions")
        return None
    util.logger.info("Exporting portfolios")
    if key_list:
        nb_portfolios = len(key_list)
    else:
        nb_portfolios = count(endpoint=endpoint)
    i = 0
    exported_portfolios = {}
    for k, p in get_list(endpoint=endpoint, key_list=key_list).items():
        if not p.is_sub_portfolio():
            exported_portfolios[k] = p.export(full)
            exported_portfolios[k].pop("key")
        else:
            util.logger.debug("Skipping export of %s, it's a standard sub-portfolio", str(p))
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
    return []


def __create_portfolio_hierarchy(endpoint, data, parent_key):
    nbr_creations = 0
    for key, subp in data.get("subPortfolios", {}).items():
        if subp.get("byReference", False):
            continue
        params = {"parent": parent_key, "key": key}
        for p in ("name", "description", "visibility"):
            params[p] = subp.get(p, None)
        util.logger.debug("Creating portfolio name '%s'", subp["name"])
        r = endpoint.post(_CREATE_API, params=params, exit_on_error=False)
        if r.ok:
            nbr_creations += 1
        nbr_creations += __create_portfolio_hierarchy(endpoint, subp, parent_key=key)
    return nbr_creations
