#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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
from http import HTTPStatus
from threading import Lock
from requests.exceptions import HTTPError

from sonar import aggregations, options, exceptions
import sonar.permissions.permissions as perms
import sonar.permissions.portfolio_permissions as pperms
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}
_CLASS_LOCK = Lock()

_LIST_API = "views/list"
_SEARCH_API = "views/search"
_CREATE_API = "views/create"
_GET_API = "views/show"

MAX_PAGE_SIZE = 500
_PORTFOLIO_QUALIFIER = "VW"
_SUBPORTFOLIO_QUALIFIER = "SVW"

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
    def get_object(cls, endpoint, key):
        util.logger.debug("Getting object '%s'", key)
        # if root_key is None:
        # data = search_by_name(endpoint=endpoint, name=name)
        # else:
        #    data = _find_sub_portfolio_by_name(name=name, data=_OBJECTS[root_key]._json)
        # if data is None:
        #    return None
        # key = data["key"]
        if key in _OBJECTS:
            return _OBJECTS[key]
        data = search_by_key(endpoint, key)
        if data is None:
            raise exceptions.ObjectNotFound(key, f"Portfolios '{key}' not found")
        return Portfolio.load(endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint, name, **kwargs):
        util.logger.debug("Creating portfolio name '%s', key '%s', parent = %s", name, str(kwargs.get("key", None)), str(kwargs.get("parent", None)))
        params = {"name": name}
        for p in ("description", "parent", "key", "visibility"):
            params[p] = kwargs.get(p, None)
        endpoint.post(_CREATE_API, params=params)
        o = cls(endpoint=endpoint, name=name, key=kwargs.get("key", None))
        if "parent" in kwargs:
            o.set_parent(Portfolio.get_object(endpoint, kwargs["parent"]))
        # TODO - Allow on the fly selection mode
        return o

    @classmethod
    def load(cls, endpoint, data):
        util.logger.debug("Loading portfolio '%s' with data %s", data["name"], util.json_dump(data))
        o = cls(endpoint=endpoint, name=data["name"], key=data["key"])
        o.reload(data)
        if not o.is_sub_portfolio:
            o.refresh()
        return o

    def __init__(self, endpoint, name, key=None):
        super().__init__(key if key else name, endpoint)
        self.name = name
        self._selection_mode = None  #: Portfolio project selection mode
        self._selection_branch = None  #: project branches on SonarQube 9.2+
        self._projects = None  #: Portfolio list of projects when selection mode is MANUAL
        self._regexp = None  #: Project selection regexp is selection mode is REGEXP
        self._tags = []  #: Portfolio tags when selection mode is TAGS
        self._description = None  #: Portfolio description
        self.is_sub_portfolio = False  #: Whether the portfolio is a subportfolio
        self._visibility = None  #: Portfolio visibility
        self._sub_portfolios = None  #: Subportfolios
        self._permissions = None  #: Permissions
        self.parent = None  #: Ref to parent portfolio object, if any
        self._root_portfolio = None  #: Ref to root portfolio, if any
        _OBJECTS[self.uuid()] = self
        util.logger.debug("Created portfolio object name '%s'", name)
        util.logger.debug("PORTFOLIOS = %s", str([p.key for p in _OBJECTS.values()]))

    def reload(self, data):
        util.logger.debug("Reloading %s with %s", str(self), util.json_dump(data))
        super().reload(data)
        if "name" in data:
            self.name = data["name"]
        if "selectionMode" in self._json:
            self._selection_mode = self._json["selectionMode"]
        if "branch" in self._json:
            self._selection_branch = self._json["branch"]
        if "regexp" in self._json:
            self._regexp = self._json["regexp"]
        self.is_sub_portfolio = self._json.get("qualifier", _PORTFOLIO_QUALIFIER) == _SUBPORTFOLIO_QUALIFIER
        if "tags" in self._json:
            self._tags = self._json["tags"]
        if "visibility" in self._json:
            self._visibility = self._json["visibility"]
        parent = data.get("parentKey", data.get("parent", None))
        if parent:
            self.set_parent(Portfolio.get_object(self.endpoint, parent))

    def __str__(self):
        return f"subportfolio '{self.key}'" if self.is_sub_portfolio else f"portfolio '{self.key}'"

    def refresh(self):
        util.logger.debug("Updating details for %s root key %s", str(self), self._root_portfolio)
        data = json.loads(self.get(_GET_API, params={"key": self.root_portfolio().key}).text)
        if not self.is_sub_portfolio:
            self.reload(data)
        self.root_portfolio().create_sub_portfolios()
        self.projects()

    def set_parent(self, parent_portfolio):
        self.parent = parent_portfolio
        self._root_portfolio = self.root_portfolio()
        util.logger.debug("%s: Parent = %s, Root = %s", str(self), str(self.parent), str(self._root_portfolio))

    def url(self):
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def selection_mode(self):
        return self._selection_mode

    def root_portfolio(self):
        if self.parent is None:
            util.logger.debug("Found root for %s, parent = %s", self.key, str(self.parent))
            self._root_portfolio = self
        else:
            util.logger.debug("recursing root for %s, parent = %s", self.key, str(self.parent))
            self._root_portfolio = self.parent.root_portfolio()
        return self._root_portfolio

    def projects(self):
        if self._selection_mode != SELECTION_MODE_MANUAL:
            util.logger.debug("%s: Not manual mode, no projects", str(self))
            self._projects = {}
            return self._projects
        if self._projects is not None:
            util.logger.debug("%s: Projects already set, returning %s", str(self), str(self._projects))
            return self._projects
        if "selectedProjects" not in self._json:
            self.refresh()
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
        util.logger.debug("%s: PROJ4 Read projects %s", str(self), str(self._projects))
        util.logger.debug("%s projects = %s", str(self), util.json_dump(self._projects))
        return self._projects

    def sub_portfolios(self, full=False):
        self.refresh()
        # self._sub_portfolios = _sub_portfolios(self._json, self.endpoint.version(), full=full)
        self.create_sub_portfolios()
        return self._sub_portfolios

    def create_sub_portfolios(self):
        if "subViews" in self._json and len(self._json["subViews"]) > 0:
            util.logger.debug("Inspecting %s subportfolios data = %s", str(self), util.json_dump(self._json["subViews"]))
            self._sub_portfolios = {}
            for oldp in self._json["subViews"]:
                p = oldp.copy()
                util.logger.debug("Found subport data = %s", util.json_dump(p))
                if p["qualifier"] == _PORTFOLIO_QUALIFIER:
                    key = p.get("originalKey", None)
                    if key is None:
                        key = p.pop("key").split(":")[-1]
                else:
                    key = p.pop("key")
                try:
                    subp = Portfolio.get_object(self.endpoint, key)
                    subp.set_parent(self)
                except exceptions.ObjectNotFound:
                    subp = Portfolio.create(self.endpoint, name=p.pop("name"), key=key, parent=self.key, description=p.pop("desc", None), **p)
                util.logger.debug("Subp = %s", str(subp))
                subp.reload(oldp)
                self._sub_portfolios[subp.key] = subp
                subp.create_sub_portfolios()
                subp.projects()

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

    def delete(self):
        return sq.delete_object(self, "views/delete", {"key": self.key}, _OBJECTS)

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

    def export(self, full=False):
        util.logger.info("Exporting %s", str(self))
        self.refresh()
        json_data = self._json
        json_data.update(self.sub_portfolios(full=full))
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
        if self._permissions is None and not self.is_sub_portfolio:
            # No permissions for sub portfolios
            self._permissions = pperms.PortfolioPermissions(self)
        return self._permissions

    def set_permissions(self, portfolio_perms):
        if not self.is_sub_portfolio:
            # No permissions for SVW
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
        util.logger.debug("Current Project list = %s", str(current_project_keys))
        ok = True
        for proj, branches in project_list.items():
            if proj in current_project_keys:
                util.logger.debug("Won't add project '%s' branch '%s' to %s, it's already added", proj, project_list[proj], str(self))
                continue
            try:
                r = self.post("views/add_project", params={"key": self.key, "project": proj})
                ok = ok and r.ok
                current_projects[proj] = options.DEFAULT
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.key, f"Project '{proj}' not found, can't be added to portfolio '{self.key}'")
                raise

            for branch in util.csv_to_list(branches):
                if branch == options.DEFAULT or branch in util.csv_to_list(current_projects[proj]):
                    util.logger.debug("Won't add project '%s' branch '%s' to %s, it's already added", proj, project_list[proj], str(self))
                    continue
                if self.endpoint.version() < (9, 2, 0):
                    util.logger.warning("Can't add a project branch '%s / %s' in a %s on SonarQube < 9.2", proj, branch, str(self))
                    ok = False
                    continue
                util.logger.debug("Adding project '%s' branch '%s' to %s", proj, str(branch), str(self))
                try:
                    ok = ok and self.post("views/add_project_branch", params={"key": self.key, "project": proj, "branch": branch}).ok
                except HTTPError as e:
                    if e.response.status_code == HTTPStatus.NOT_FOUND:
                        util.logger.warning("Branch '%s' of project '%s' not found, can't be added to portfolio '%s'", branch, proj, self.key)
                        ok = False
                    else:
                        raise
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
        # if not exists(key, self.endpoint):
        #    util.logger.warning("Can't add in %s the subportfolio key '%s' by reference, it does not exists", str(self), key)
        #    return False

        util.logger.debug("Adding sub-portfolios to %s", str(self))
        if self.endpoint.version() >= (9, 3, 0):
            if not by_ref:
                try:
                    Portfolio.get_object(self.endpoint, key)
                except exceptions.ObjectNotFound:
                    Portfolio.create(self.endpoint, name, key=key, parent=self.key)
            r = self.post("views/add_portfolio", params={"portfolio": self.key, "reference": key})
        elif by_ref:
            r = self.post("views/add_local_view", params={"key": self.key, "ref_key": key})
        else:
            r = self.post("views/add_sub_view", params={"key": self.key, "name": name, "subKey": key})
        if not by_ref:
            self.recompute()
            time.sleep(0.5)
        return r.ok

    def recompute(self):
        util.logger.debug("Recomputing %s", str(self))
        key = self._root_portfolio.key if self._root_portfolio else self.key
        self.post("views/refresh", params={"key": key})

    def update(self, data):
        util.logger.debug("Updating %s with %s", str(self), util.json_dump(data))
        if "byReference" not in data or not data["byReference"]:
            if "permissions" in data:
                decoded_perms = {}
                for ptype in perms.PERMISSION_TYPES:
                    if ptype not in data["permissions"]:
                        continue
                    decoded_perms[ptype] = {u: perms.decode(v) for u, v in data["permissions"][ptype].items()}
                self.set_permissions(decoded_perms)
                # self.set_permissions(data.get("permissions", {}))
            selection_mode = data.get(_PROJECT_SELECTION_MODE, "NONE")
            branch = data.get(_PROJECT_SELECTION_BRANCH, None)
            regexp = data.get(_PROJECT_SELECTION_REGEXP, None)
            tags = data.get(_PROJECT_SELECTION_TAGS, None)
            projects = data.get("projects", None)
            self._root_portfolio = self.root_portfolio()
            util.logger.debug("1.Setting root of %s is %s", str(self), str(self._root_portfolio))
            self.set_selection_mode(selection_mode=selection_mode, projects=projects, branch=branch, regexp=regexp, tags=tags)
        else:
            util.logger.debug("Skipping setting portfolio details, it's a reference")

        for key, subp in data.get("subPortfolios", {}).items():
            key_list = list(self.sub_portfolios(full=True).keys())
            if subp.get("byReference", False):
                o_subp = Portfolio.get_object(self.endpoint, key)
                if o_subp.key not in key_list:
                    self.add_subportfolio(o_subp.key, name=o_subp.name, by_ref=True)
                o_subp.update(subp)
            else:
                # get_list(endpoint=self.endpoint)
                try:
                    o = Portfolio.get_object(self.endpoint, key)
                except exceptions.ObjectNotFound:
                    util.logger.info("%s: Creating subportfolio from %s", str(self), util.json_dump(subp))
                    # o = Portfolio.create(endpoint=self.endpoint, name=name, parent=self.key, **subp)
                    self.add_subportfolio(key=key, name=subp["name"], by_ref=False)
                o.set_parent(self)
                o.update(subp)

    def search_params(self):
        """Return params used to search for that object

        :meta private:
        """
        return {"portfolio": self.key}


def count(endpoint=None):
    return aggregations.count(api=_SEARCH_API, endpoint=endpoint)


def get_list(endpoint, key_list=None, use_cache=True):
    """
    :return: List of Portfolios (all of them if key_list is None or empty)
    :param key_list: List of portfolios keys to get, if None or empty all portfolios are returned
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :rtype: dict{<branchName>: <Branch>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            util.logger.info("Listing portfolios")
            return search(endpoint=endpoint)
        object_list = {}
        for key in util.csv_to_list(key_list):
            object_list[key] = Portfolio.get_object(endpoint, key)
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


"""
def _sub_portfolios(json_data, version, full=False):
    subport = {}
    if "subViews" in json_data and len(json_data["subViews"]) > 0:
        for p in json_data["subViews"]:
            qual = p.pop("qualifier", _SUBPORTFOLIO_QUALIFIER)
            p["byReference"] = qual == _PORTFOLIO_QUALIFIER
            if qual == _PORTFOLIO_QUALIFIER:
                p["key"] = p["originalKey"] if full else p.pop("originalKey")
                if not full:
                    for k in ("name", "desc"):
                        p.pop(k, None)
            p.update(_sub_portfolios(p, version, full))
            __cleanup_portfolio_json(p)
            if full:
                subport[p["key"]] = p
            else:
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
"""


def exists(key, endpoint):
    try:
        Portfolio.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


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
        try:
            o = Portfolio.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            util.logger.debug("Portfolio not found, creating it")
            newdata = data.copy()
            name = newdata.pop("name")
            o = Portfolio.create(endpoint=endpoint, name=name, key=key, **newdata)
            o.reload(data)
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
        try:
            o = Portfolio.get_object(endpoint, key)
            o.update(data)
        except exceptions.ObjectNotFound:
            util.logger.error("Can't find portfolio key '%s', name '%s'", key, data["name"])


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
        if not p.is_sub_portfolio:
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
    o_parent = Portfolio.get_object(endpoint, parent_key)
    for key, subp in data.get("subPortfolios", {}).items():
        if subp.get("byReference", False):
            continue
        try:
            o = Portfolio.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            newdata = subp.copy()
            name = newdata.pop("name")
            util.logger.debug("Object not found, creating portfolio name '%s'", name)
            o = Portfolio.create(endpoint, name, key=key, parent=o_parent.key, **newdata)
            o.reload(subp)
            nbr_creations += 1
        o.set_parent(o_parent)
        nbr_creations += __create_portfolio_hierarchy(endpoint, subp, parent_key=key)
    return nbr_creations
