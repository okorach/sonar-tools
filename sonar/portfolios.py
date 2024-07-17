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

    Abstraction of the SonarQube "portfolio" concept

"""

from __future__ import annotations
from typing import Union
import time
import json
import datetime
from http import HTTPStatus
from threading import Lock
from requests.exceptions import HTTPError

import sonar.logging as log
import sonar.platform as pf

from sonar import aggregations, exceptions, settings
import sonar.permissions.permissions as perms
import sonar.permissions.portfolio_permissions as pperms
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules, problem

_OBJECTS = {}
_CLASS_LOCK = Lock()
_NOT_SUPPORTED = "Portfolios not supported in Community and Developer Edition"

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

_PROJECT_SELECTION_MODE = "selectionMode"
_PROJECT_SELECTION_BRANCH = "projectSelectionBranch"
_PROJECT_SELECTION_REGEXP = "projectSelectionRegexp"
_PROJECT_SELECTION_TAGS = "projectSelectionTags"

_IMPORTABLE_PROPERTIES = (
    "key",
    "name",
    "description",
    _PROJECT_SELECTION_MODE,
    "visibility",
    "permissions",
    "subPortfolios",
    "projects",
)


class Portfolio(aggregations.Aggregation):
    """
    Abstraction of the Sonar portfolio concept
    """

    def __init__(self, endpoint: pf.Platform, name: str, key: str = None) -> None:
        """Constructor, don't use - use class methods instead"""
        if not key:
            key = name.replace(" ", "_")
        super().__init__(endpoint=endpoint, key=key)
        self.name = name
        self._selection_mode = {"mode": SELECTION_MODE_NONE}  #: Portfolio project selection mode
        self._tags = []  #: Portfolio tags when selection mode is TAGS
        self._description = None  #: Portfolio description
        self.is_sub_portfolio = False  #: Whether the portfolio is a subportfolio
        self._visibility = None  #: Portfolio visibility
        self._sub_portfolios = None  #: Subportfolios
        self._permissions = None  #: Permissions
        self.parent = None  #: Ref to parent portfolio object, if any
        self._root_portfolio = None  #: Ref to root portfolio, if any
        _OBJECTS[self.uuid()] = self
        log.debug("Created portfolio object name '%s'", name)
        log.debug("PORTFOLIOS = %s", str([p.key for p in _OBJECTS.values()]))

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Portfolio:
        """Gets a portfolio object from its key"""
        check_supported(endpoint)
        log.info("Getting portfolio object key '%s'", key)
        # if root_key is None:
        # data = search_by_name(endpoint=endpoint, name=name)
        # else:
        #    data = _find_sub_portfolio_by_name(name=name, data=_OBJECTS[root_key]._json)
        # if data is None:
        #    return None
        # key = data["key"]
        uu = sq.uuid(key, endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        data = search_by_key(endpoint, key)
        if data is None:
            raise exceptions.ObjectNotFound(key, f"Portfolio key '{key}' not found")
        return Portfolio.load(endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, name: str, **kwargs) -> Portfolio:
        """Creates a portfolio object"""
        check_supported(endpoint)
        log.debug("Creating portfolio name '%s', key '%s', parent = %s", name, str(kwargs.get("key", None)), str(kwargs.get("parent", None)))
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
    def load(cls, endpoint: pf.Platform, data: dict[str, str]) -> Portfolio:
        """Creates and load a Portfolio object with returned API data"""
        log.debug("Loading portfolio '%s' with data %s", data["name"], util.json_dump(data))
        o = cls(endpoint=endpoint, name=data["name"], key=data["key"])
        o.reload(data)
        if not o.is_sub_portfolio:
            try:
                o.refresh()
            except HTTPError as e:
                log.warning("HTTP Error %s when refreshing %s", str(e), str(o))
        return o

    def reload(self, data: dict[str, str]) -> None:
        """Reloads a portfolio with returned API data"""
        log.debug("Reloading %s with %s", str(self), util.json_dump(data))
        super().reload(data)
        if "name" in data:
            self.name = data["name"]
        if "selectionMode" in self._json:
            mode = self._json["selectionMode"]
            self._selection_mode = {"mode": mode}
            branch = self._json.get("branch", settings.DEFAULT_BRANCH)
            if mode == SELECTION_MODE_MANUAL:
                self._selection_mode["projects"] = {}
                for projdata in self._json.get("selectedProjects", {}):
                    branch_list = projdata.get("selectedBranches", [settings.DEFAULT_BRANCH])
                    self._selection_mode["projects"].update({projdata["projectKey"]: branch_list})
            elif mode == SELECTION_MODE_REGEXP:
                self._selection_mode.update({"regexp": self._json["regexp"], "branch": branch})
            elif mode == SELECTION_MODE_TAGS:
                self._selection_mode.update({"tags": self._json["tags"], "branch": branch})
            elif mode == SELECTION_MODE_OTHERS:
                self._selection_mode.update({"branch": branch})
        self.is_sub_portfolio = self._json.get("qualifier", _PORTFOLIO_QUALIFIER) == _SUBPORTFOLIO_QUALIFIER
        if "visibility" in self._json:
            self._visibility = self._json["visibility"]
        parent = data.get("parentKey", data.get("parent", None))
        if parent:
            self.set_parent(Portfolio.get_object(self.endpoint, parent))

    def __str__(self) -> str:
        """Returns string representation of object"""
        return f"subportfolio '{self.key}'" if self.is_sub_portfolio else f"portfolio '{self.key}'"

    def refresh(self) -> None:
        """Refreshes a portfolio data from the Sonar instance"""
        log.debug("Updating details for %s root key %s", str(self), self._root_portfolio)
        data = json.loads(self.get(_GET_API, params={"key": self.root_portfolio().key}).text)
        if not self.is_sub_portfolio:
            self.reload(data)
        self.root_portfolio().create_sub_portfolios()
        self.projects()

    def last_analysis(self) -> datetime.datetime:
        """Returns the portfolio last computation date"""
        if self._last_analysis is None:
            super().refresh()
        return self._last_analysis

    def set_parent(self, parent_portfolio: Portfolio) -> None:
        """Sets the parent portfolio of a subportfolio"""
        self.parent = parent_portfolio
        self._root_portfolio = self.root_portfolio()
        log.debug("%s: Parent = %s, Root = %s", str(self), str(self.parent), str(self._root_portfolio))

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def root_portfolio(self) -> Portfolio:
        """Returns the root portfolio of a portfolio in a hierarchy"""
        if self.parent is None or self.parent.key == self.key:
            log.debug("Found root for %s, parent = %s", self.key, str(self.parent))
            self._root_portfolio = self
        else:
            log.debug("recursing root for %s, parent = %s", self.key, str(self.parent))
            self._root_portfolio = self.parent.root_portfolio()
        return self._root_portfolio

    def projects(self) -> Union[dict[str, str], None]:
        """Returns list of projects and their branches if selection mode is manual, None otherwise"""
        if self._selection_mode["mode"] != SELECTION_MODE_MANUAL:
            log.debug("%s: Not manual mode, no projects", str(self))
            return None
        if self._selection_mode["projects"] is not None:
            log.debug("%s: Projects already set, returning %s", str(self), str(self._selection_mode["projects"]))
            return self._selection_mode["projects"]
        if self._json is None or "selectedProjects" not in self._json:
            self.refresh()
        if self.endpoint.version() < (9, 3, 0):
            self._selection_mode["projects"] = {p: settings.DEFAULT_BRANCH for p in self._json.get("projects", {})}
            return self._selection_mode["projects"]
        for p in self._json.get("selectedProjects", {}):
            if "selectedBranches" in p:
                self._selection_mode["projects"][p["projectKey"]] = util.list_to_csv(p["selectedBranches"], ", ", True)
            else:
                self._selection_mode["projects"][p["projectKey"]] = settings.DEFAULT_BRANCH
        log.debug("%s projects = %s", str(self), util.json_dump(self._selection_mode["projects"]))
        return self._selection_mode["projects"]

    def sub_portfolios(self, full: bool = False) -> dict[str, Portfolio]:
        """Returns the list of sub portfolios as dict"""
        self.refresh()
        # self._sub_portfolios = _sub_portfolios(self._json, self.endpoint.version(), full=full)
        self.create_sub_portfolios()
        return self._sub_portfolios

    def create_sub_portfolios(self) -> None:
        """Creates Portfolio objects for subportfolios of a (parent) Portfolio"""
        log.debug("Creating subportfolios for %s with JSON %s", str(self), str(self._json))
        if "subViews" not in self._json or len(self._json["subViews"]) == 0:
            return

        log.debug("Inspecting %s subportfolios data = %s", str(self), util.json_dump(self._json["subViews"]))
        self._sub_portfolios = {}
        for oldp in self._json["subViews"]:
            p = oldp.copy()
            log.debug("Found subport data = %s", util.json_dump(p))
            key = p.pop("key")
            if p["qualifier"] == _PORTFOLIO_QUALIFIER:
                key = p.get("originalKey", key.split(":")[-1])
            try:
                subp = Portfolio.get_object(self.endpoint, key)
                if p["qualifier"] == _SUBPORTFOLIO_QUALIFIER:
                    subp.set_parent(self)
            except exceptions.ObjectNotFound:
                subp = Portfolio.create(self.endpoint, name=p.pop("name"), key=key, parent=self.key, description=p.pop("desc", None), **p)
            log.debug("%s Subp = %s", str(self), str(subp))
            subp.reload(oldp)
            self._sub_portfolios[subp.key] = subp
            subp.create_sub_portfolios()
            subp.projects()

    def regexp(self) -> Union[str, None]:
        """Returns the regexp if selection mode is regexp, None otherwise"""
        if self.selection_mode()["mode"] != SELECTION_MODE_REGEXP:
            return None
        return self.selection_mode()["regexp"]

    def tags(self) -> Union[list[str], None]:
        """Returns the list of tags if selection mode is tags, None otherwise"""
        if self.selection_mode()["mode"] != SELECTION_MODE_TAGS:
            self._tags = None
        return self.selection_mode()["tags"]

    def get_components(self) -> dict[str, dict[str, str]]:
        """Returns subcomponents of a Portfolio"""
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

    def delete(self) -> bool:
        """Deletes a portfolio, returns whether the operation succeeded"""
        return sq.delete_object(self, "views/delete", {"key": self.key}, _OBJECTS)

    def _audit_empty(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        """Audits if a portfolio is empty (no projects)"""
        if not audit_settings.get("audit.portfolios.empty", True):
            log.debug("Auditing empty portfolios is disabled, skipping...")
            return []
        return self._audit_empty_aggregation(broken_rule=rules.RuleId.PORTFOLIO_EMPTY)

    def _audit_singleton(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        """Audits if a portfolio contains a single project"""
        if not audit_settings.get("audit.portfolios.singleton", True):
            log.debug("Auditing singleton portfolios is disabled, skipping...")
            return []
        return self._audit_singleton_aggregation(broken_rule=rules.RuleId.PORTFOLIO_SINGLETON)

    def audit(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        """Audits a portfolio"""
        log.info("Auditing %s", str(self))
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings) + self._audit_bg_task(audit_settings)

    def to_json(self, export_settings: dict[str, str]) -> dict[str, str]:
        """Returns the portfolio representation as JSON"""
        self.refresh()
        json_data = self._json
        subportfolios = self.sub_portfolios()
        if subportfolios:
            json_data["subPortfolios"] = {}
            for s in subportfolios.values():
                json_data["subPortfolios"][s.key] = s.to_json(export_settings)
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": None if self._description == "" else self._description,
                _PROJECT_SELECTION_MODE: self.selection_mode(export_settings),
                "visibility": self._visibility,
                "permissions": self.permissions().export(export_settings=export_settings),
            }
        )
        return json_data

    def export(self, export_settings: dict[str, str]) -> dict[str, str]:
        """Exports a portfolio (for sonar-config)"""
        log.info("Exporting %s", str(self))
        return util.remove_nones(util.filter_export(self.to_json(export_settings), _IMPORTABLE_PROPERTIES, export_settings["FULL_EXPORT"]))

    def permissions(self) -> pperms.PortfolioPermissions:
        """Returns a portfolio permissions (if toplevel) or None if sub-portfolio"""
        if self._permissions is None and not self.is_sub_portfolio:
            # No permissions for sub portfolios
            self._permissions = pperms.PortfolioPermissions(self)
        return self._permissions

    def set_permissions(self, portfolio_perms: dict[str, str]) -> None:
        """Sets a portfolio permissions described as JSON"""
        if not self.is_sub_portfolio:
            # No permissions for SVW
            self.permissions().set(portfolio_perms)

    def selection_mode(self, export_settings: dict[str, str] = None) -> dict[str, str]:
        """Returns a portfolio selection mode"""
        if self._selection_mode is None:
            self.reload(json.loads(self.get(_GET_API, params={"key": self.root_portfolio().key}).text))
        if export_settings and export_settings.get("INLINE_LISTS", True):
            if self._selection_mode["mode"] == SELECTION_MODE_TAGS:
                log.debug("Inlining portfolio tags")
                selection_mode = self._selection_mode.copy()
                selection_mode["tags"] = util.list_to_csv(selection_mode["tags"], separator=", ", check_for_separator=True)
                return selection_mode
            elif self._selection_mode["mode"] == SELECTION_MODE_MANUAL:
                selection_mode = self._selection_mode.copy()
                selection_mode["projects"] = {
                    pkey: util.list_to_csv(branches, separator=", ", check_for_separator=True)
                    for pkey, branches in selection_mode["projects"].items()
                }
                return selection_mode
        return self._selection_mode

    def add_projects(self, project_list: list[Union[str, object]]) -> Portfolio:
        """Adds projects main branch to a portfolio"""
        if not project_list or len(project_list) == 0:
            return self
        self.set_manual_mode()
        branch_dict = {}
        for p in project_list:
            key = p if isinstance(p, str) else p.key
            branch_dict[key] = None
        return self.add_project_branches(branch_dict)

    def add_project_branches(self, branch_dict: dict[str, Union[str, object]]) -> Portfolio:
        """Adds projects branches to a portfolio"""
        if not branch_dict:
            return self
        self.set_manual_mode()
        proj_dict = {}
        for proj, branch in branch_dict.items():
            key = proj if isinstance(proj, str) else proj.key
            try:
                if branch and branch != settings.DEFAULT_BRANCH:
                    self.post("views/add_project_branch", params={"key": self.key, "project": key, "branch": branch})
                else:
                    self.post("views/add_project", params={"key": self.key, "project": key})
                proj_dict[key] = branch
                self._selection_mode["projects"] = proj_dict
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.key, f"Project '{key}' or branch '{branch}' not found, can't be added to {str(self)}")
                raise
        return self

    def set_manual_mode(self) -> Portfolio:
        """Sets a portfolio to manual mode"""
        if not self._selection_mode or self._selection_mode["mode"] != SELECTION_MODE_MANUAL:
            self.post("views/set_manual_mode", params={"portfolio": self.key})
        self._selection_mode = {"mode": SELECTION_MODE_MANUAL, "projects": {}}
        return self

    def set_tags_mode(self, tags: list[str], branch: str = None) -> Portfolio:
        """Sets a portfolio to tags mode"""
        mode = self._selection_mode
        if not mode or mode["mode"] != SELECTION_MODE_TAGS or mode["branch"] != branch:
            self.post("views/set_tags_mode", params={"portfolio": self.key, "tags": util.list_to_csv(tags), "branch": branch})
            self._selection_mode = {"mode": SELECTION_MODE_TAGS, "tags": tags, "branch": branch}
        return self

    def set_regexp_mode(self, regexp: str, branch: str = None) -> Portfolio:
        """Sets a portfolio to regexp mode"""
        mode = self._selection_mode
        if not mode or mode["mode"] != SELECTION_MODE_REGEXP or mode["branch"] != branch:
            self.post("views/set_regexp_mode", params={"portfolio": self.key, "regexp": regexp, "branch": branch})
            self._selection_mode = {"mode": SELECTION_MODE_REGEXP, "regexp": regexp, "branch": branch}
        return self

    def set_remaining_projects_mode(self, branch: str = None) -> Portfolio:
        """Sets a portfolio to remaining projects mode"""
        mode = self._selection_mode
        if not mode or mode["mode"] != SELECTION_MODE_OTHERS or mode["branch"] != branch:
            self.post("views/set_remaining_projects_mode", params={"portfolio": self.key, "branch": branch})
            self._selection_mode = {"mode": SELECTION_MODE_OTHERS, "branch": branch}
        return self

    def set_none_mode(self) -> Portfolio:
        """Sets a portfolio to none mode"""
        # Hack: API change between 9.0 and 9.1
        mode = self._selection_mode
        if not mode or mode["mode"] != SELECTION_MODE_NONE:
            if self.endpoint.version() < (9, 1, 0):
                self.post("views/mode", params={"key": self.key, "selectionMode": "NONE"})
            else:
                self.post("views/set_none_mode", params={"portfolio": self.key})
            self._selection_mode = {"mode": SELECTION_MODE_NONE}
        return self

    def set_selection_mode(
        self, selection_mode: str, projects: dict[str, str] = None, regexp: str = None, tags: list[str] = None, branch: str = None
    ) -> Portfolio:
        """Sets a portfolio selection mode"""
        log.debug("Setting selection mode %s for %s", str(selection_mode), str(self))
        if selection_mode == SELECTION_MODE_MANUAL:
            self.set_manual_mode().add_project_branches(projects)
        elif selection_mode == SELECTION_MODE_TAGS:
            self.set_tags_mode(tags=tags, branch=branch)
        elif selection_mode == SELECTION_MODE_REGEXP:
            self.set_regexp_mode(regexp=regexp, branch=branch)
        elif selection_mode == SELECTION_MODE_OTHERS:
            self.set_remaining_projects_mode(branch)
        elif selection_mode == SELECTION_MODE_NONE:
            self.set_none_mode()
        else:
            log.error("Invalid portfolio project selection mode %s during import, skipped...", selection_mode)

        return self

    def add_subportfolio(self, key: str, name: str = None, by_ref: bool = False) -> bool:
        """Adds a subportfolio to a portfolio, defined by key, name and by reference option"""
        # if not exists(key, self.endpoint):
        #    log.warning("Can't add in %s the subportfolio key '%s' by reference, it does not exists", str(self), key)
        #    return False

        log.debug("Adding sub-portfolios to %s", str(self))
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

    def recompute(self) -> bool:
        """Triggers portfolio recomputation, return whether operation REQUEST succeeded"""
        log.debug("Recomputing %s", str(self))
        key = self._root_portfolio.key if self._root_portfolio else self.key
        return self.post("views/refresh", params={"key": key}).ok

    def update(self, data: dict[str, str]) -> None:
        """Updates a portfolio with sonar-config JSON data"""
        log.debug("Updating %s with %s", str(self), util.json_dump(data))
        if "byReference" not in data or not data["byReference"]:
            if "permissions" in data:
                decoded_perms = {}
                for ptype in perms.PERMISSION_TYPES:
                    if ptype not in data["permissions"]:
                        continue
                    decoded_perms[ptype] = {u: perms.decode(v) for u, v in data["permissions"][ptype].items()}
                self.set_permissions(decoded_perms)
                # self.set_permissions(data.get("permissions", {}))
            selection_mode = data.get("selectionMode", "NONE")
            branch, regexp, tags, projects = None, None, None, None
            if isinstance(selection_mode, str):
                sel_mode = selection_mode
                branch = data.get(_PROJECT_SELECTION_BRANCH, None)
                regexp = data.get(_PROJECT_SELECTION_REGEXP, None)
                tags = data.get(_PROJECT_SELECTION_TAGS, None)
                projects = data.get("projects", None)
            else:
                sel_mode = selection_mode["mode"]
                if sel_mode == SELECTION_MODE_MANUAL:
                    projects = selection_mode["projects"]
                elif sel_mode == SELECTION_MODE_REGEXP:
                    regexp = selection_mode["regexp"]
                elif sel_mode == SELECTION_MODE_TAGS:
                    tags = selection_mode["tags"]
            self._root_portfolio = self.root_portfolio()
            log.debug("1.Setting root of %s is %s", str(self), str(self._root_portfolio))
            self.set_selection_mode(selection_mode=sel_mode, projects=projects, branch=branch, regexp=regexp, tags=tags)
        else:
            log.debug("Skipping setting portfolio details, it's a reference")

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
                    log.info("%s: Creating subportfolio from %s", str(self), util.json_dump(subp))
                    # o = Portfolio.create(endpoint=self.endpoint, name=name, parent=self.key, **subp)
                    self.add_subportfolio(key=key, name=subp["name"], by_ref=False)
                o.set_parent(self)
                o.update(subp)

    def search_params(self) -> dict[str, str]:
        """Return params used to search/create/delete for that object"""
        return {"portfolio": self.key}


def count(endpoint: pf.Platform) -> int:
    """Counts number of portfolios"""
    return aggregations.count(api=_SEARCH_API, endpoint=endpoint)


def get_list(endpoint: pf.Platform, key_list: list[str] = None, use_cache: bool = True) -> dict[str, Portfolio]:
    """
    :return: List of Portfolios (all of them if key_list is None or empty)
    :param key_list: List of portfolios keys to get, if None or empty all portfolios are returned
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :rtype: dict{<branchName>: <Branch>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            log.info("Listing portfolios")
            return search(endpoint=endpoint)
        object_list = {}
        for key in util.csv_to_list(key_list):
            object_list[key] = Portfolio.get_object(endpoint, key)
    return object_list


def search(endpoint: pf.Platform, params: dict[str, str] = None) -> dict[str, Portfolio]:
    """Search all portfolios of a platform and returns as dict"""
    portfolio_list = {}
    check_supported(endpoint)
    portfolio_list = sq.search_objects(
        api=_SEARCH_API,
        params=params,
        returned_field="components",
        key_field="key",
        object_class=Portfolio,
        endpoint=endpoint,
    )
    return portfolio_list


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    if endpoint.edition() not in ("enterprise", "datacenter"):
        errmsg = f"No portfolios in {endpoint.edition()} edition"
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)


def audit(endpoint: pf.Platform, audit_settings: dict[str, str], key_list: list[str, str] = None) -> list[object]:
    """Audits all portfolios"""
    if not audit_settings.get("audit.portfolios", True):
        log.debug("Auditing portfolios is disabled, skipping...")
        return []
    log.info("--- Auditing portfolios ---")
    problems = []
    for p in get_list(endpoint=endpoint, key_list=key_list).values():
        problems += p.audit(audit_settings)
    return problems


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


def exists(key: str, endpoint: pf.Platform) -> bool:
    """Tells whether a portfolio with a given key exists"""
    try:
        Portfolio.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


def import_config(endpoint: pf.Platform, config_data: dict[str, str], key_list: list[str] = None) -> None:
    """Imports portfolio configuration described in a JSON"""
    if "portfolios" not in config_data:
        log.info("No portfolios to import")
        return
    if endpoint.edition() in ("community", "developer"):
        log.warning("Can't import portfolios on a %s edition", endpoint.edition())
        return

    log.info("Importing portfolios - pass 1: Create all top level portfolios")
    search(endpoint=endpoint)
    # First pass to create all top level porfolios that may be referenced
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["portfolios"].items():
        if new_key_list and key not in new_key_list:
            continue
        log.info("Importing portfolio key '%s'", key)
        try:
            o = Portfolio.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            log.debug("Portfolio not found, creating it")
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
    log.info("Importing portfolios - pass 2: Creating sub-portfolios")
    for key, data in config_data["portfolios"].items():
        if new_key_list and key not in new_key_list:
            continue
        try:
            o = Portfolio.get_object(endpoint, key)
            o.update(data)
        except exceptions.ObjectNotFound:
            log.error("Can't find portfolio key '%s', name '%s'", key, data["name"])


def search_by_name(endpoint: pf.Platform, name: str) -> dict[str, str]:
    """Searches portfolio by nmame and and, if found, returns data as JSON"""
    return util.search_by_name(endpoint, name, _SEARCH_API, "components")


def search_by_key(endpoint: pf.Platform, key: str) -> dict[str, str]:
    """Searches portfolio by key and and, if found, returns data as JSON"""
    return util.search_by_key(endpoint, key, _SEARCH_API, "components")


def export(endpoint: pf.Platform, export_settings: dict[str, str], key_list: list[str] = None) -> dict[str, str]:
    """Exports portfolios as JSON

    :param Platform endpoint: Reference to the SonarQube platform
    :param key_list: list of portfoliios keys to export as csv or list, defaults to all if None
    :type key_list: list, optional
    :param full: Whether to export all attributes, including those that can't be set, defaults to False
    :type full: bool
    :return: Dict of applications settings
    :rtype: dict
    """
    check_supported(endpoint)
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Portfolios do not exist in SonarCloud, export skipped")

    log.info("Exporting portfolios")
    if key_list:
        nb_portfolios = len(key_list)
    else:
        nb_portfolios = count(endpoint=endpoint)
    i = 0
    exported_portfolios = {}
    for k, p in get_list(endpoint=endpoint, key_list=key_list).items():
        if not p.is_sub_portfolio:
            exported_portfolios[k] = p.export(export_settings)
            exported_portfolios[k].pop("key")
        else:
            log.debug("Skipping export of %s, it's a standard sub-portfolio", str(p))
        i += 1
        if i % 50 == 0 or i == nb_portfolios:
            log.info("Exported %d/%d portfolios (%d%%)", i, nb_portfolios, (i * 100) // nb_portfolios)
    return exported_portfolios


def recompute(endpoint: pf.Platform) -> None:
    """Triggers recomputation of all portfolios"""
    endpoint.post("views/refresh")


def _find_sub_portfolio(key: str, data: dict[str, str]) -> dict[str, str]:
    """Finds a subportfolio in a JSON hierarchy"""
    for subp in data.get("subViews", []):
        if subp["key"] == key:
            return subp
        child = _find_sub_portfolio(key, subp)
        if child is not None:
            return child
    return {}


def __create_portfolio_hierarchy(endpoint: pf.Platform, data: dict[str, str], parent_key: str) -> int:
    """Creates the hierarchy of portfolios that are new defined by reference"""
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
            log.debug("Object not found, creating portfolio name '%s'", name)
            o = Portfolio.create(endpoint, name, key=key, parent=o_parent.key, **newdata)
            o.reload(subp)
            nbr_creations += 1
        o.set_parent(o_parent)
        nbr_creations += __create_portfolio_hierarchy(endpoint, subp, parent_key=key)
    return nbr_creations
