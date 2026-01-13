#
# sonar-tools
# Copyright (C) 2024-2026 Olivier Korach
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

"""Abstraction of Sonar Application Branch"""

from __future__ import annotations
from typing import Optional, Union, Any, TYPE_CHECKING
import json
from requests.utils import quote

import sonar.logging as log
from sonar.util import cache

from sonar.components import Component

from sonar.branches import Branch
from sonar.projects import Project
from sonar import exceptions
import sonar.utilities as sutil
from sonar.api.manager import ApiOperation as Oper
import sonar.util.constants as c
from sonar import applications as apps

if TYPE_CHECKING:
    from sonar.issues import Issue
    from sonar.hotspots import Hotspot
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr


_NOT_SUPPORTED = "Applications not supported in community edition"


class ApplicationBranch(Component):
    """Abstraction of the SonarQube "application branch" concept"""

    CACHE = cache.Cache()

    def __init__(
        self,
        app: apps.Application,
        name: str,
        project_branches: list[Union[Project, Branch]],
        is_main: bool = False,
        branch_data: Optional[ApiPayload] = None,
    ) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=app.endpoint, key=f"{app.key} BRANCH {name}")
        self.concerned_object: apps.Application = app
        self.name = name
        self.sq_json = branch_data
        self._is_main = is_main
        self._project_branches = project_branches
        log.debug("Constructed object %s with uuid %d id %x", str(self), hash(self), id(self))
        self.__class__.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: Platform, app: Union[str, apps.Application], branch_name: str) -> ApplicationBranch:
        """Gets an Application object from SonarQube

        :param str | Application app: Reference to the Application holding that branch
        :param branch_name: Name of the application branch
        :raises ObjectNotFound: If Application or Brnach not found
        :return: The found ApplicationBranch object
        """
        if endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        if isinstance(app, str):
            app = apps.Application.get_object(endpoint, app)
        if o := cls.CACHE.get(endpoint.local_url, app.key, branch_name):
            return o
        app.refresh()
        app.branches()
        if o := cls.CACHE.get(endpoint.local_url, app.key, branch_name):
            return o
        raise exceptions.ObjectNotFound(app.key, f"Application key '{app.key}' branch '{branch_name}' not found")

    @classmethod
    def create(cls, app: apps.Application, name: str, projects_or_branches: list[Union[Project, Branch]]) -> ApplicationBranch:
        """Creates an ApplicationBranch object in SonarQube

        :param Application app: Reference to the Application holding that branch
        :param str name: Name of the application branch
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectAlreadyExists: If a branch of that name already exist
        :return: The created ApplicationBranch object
        :rtype: ApplicationBranch
        """
        if app.endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        custom_branches = [e for e in projects_or_branches if isinstance(e, Branch)]
        if len(custom_branches) == 0:
            raise exceptions.UnsupportedOperation("No custom branch defined in during creation")
        params = [("application", app.key), ("branch", name)]
        for branch in custom_branches:
            params.append(("project", branch.concerned_object.key))
            params.append(("projectBranch", branch.name))
        api, _, _, _ = app.endpoint.api.get_details(cls, Oper.CREATE)
        string_params = "&".join([f"{p[0]}={quote(str(p[1]))}" for p in params])
        app.endpoint.post(api, params=string_params)
        return cls(app=app, name=name, project_branches=projects_or_branches)

    @classmethod
    def load(cls, app: apps.Application, branch_data: ApiPayload) -> ApplicationBranch:
        """Loads an ApplicationBranch object from JSON data

        :param Application app: Reference to the Application holding that branch
        :param ApiPayload branch_data: Data coming from api/applications/show
        :return: The found ApplicationBranch object
        :rtype: ApplicationBranch
        """
        project_branches = []
        for proj_data in branch_data["projects"]:
            proj = Project.get_object(app.endpoint, proj_data["key"])
            project_branches.append(Branch.get_object(proj.endpoint, project=proj, branch_name=proj_data["branch"]))
        return cls(
            app=app, name=branch_data["branch"], project_branches=project_branches, is_main=branch_data.get("isMain", False), branch_data=branch_data
        )

    def __str__(self) -> str:
        return f"application '{self.concerned_object.key}' branch '{self.name}'"

    def __hash__(self) -> int:
        """Returns the object UUID"""
        return hash((self.concerned_object.key, self.name, self.base_url()))

    def get_issues(self, **search_params: Any) -> dict[str, Issue]:
        """Returns a branch list of issues"""
        from sonar.issues import Issue

        return Issue.search(self.endpoint, **(search_params | {"project": self.concerned_object.key, "branch": self.name}))

    def get_hotspots(self, **search_params: Any) -> dict[str, Hotspot]:
        """Returns a branch list of hotspots"""
        from sonar.hotspots import Hotspot

        return Hotspot.search(self.endpoint, **(search_params | {"project": self.concerned_object.key, "branch": self.name}))

    def api_params(self, operation: Optional[str] = None) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {Oper.GET: {"application": self.concerned_object.key, "branch": self.name}}
        return ops[operation] if operation and operation in ops else ops[Oper.GET]

    def is_main(self) -> bool:
        """Returns whether app branch is main"""
        return self._is_main

    def get_tags(self, **kwargs) -> list[str]:
        """
        :return: The tags of the project corresponding to the branch
        """
        return self.concerned_object.get_tags(**kwargs)

    def projects_branches(self) -> list[Union[Project, Branch]]:
        """The list of project or project branches included in the application branch"""
        return self._project_branches

    def delete(self) -> bool:
        """Deletes an ApplicationBranch

        :return: Whether the delete succeeded
        :rtype: bool
        """
        if self.is_main():
            log.warning("Can't delete main %s, simply delete the application for that", str(self))
            return False
        return self.delete_object(application=self.concerned_object.key, branch=self.name)

    def reload(self, data: ApiPayload) -> ApplicationBranch:
        """Reloads an App Branch from JSON data coming from Sonar"""
        super().reload(data)
        self.name = data.get("branch", "")
        return self

    def export(self) -> ObjectJsonRepr:
        """Exports an application branch

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
        log.info("Exporting %s from %s", self, self.sq_json)
        jsondata = {"projects": {b["key"]: b["branch"] if b["selected"] else sutil.DEFAULT for b in self.sq_json["projects"]}}
        if self.is_main():
            jsondata["isMain"] = True
        return jsondata

    def update(self, name: Optional[str] = None, projects_or_branches: Optional[list[Union[Project, Branch]]] = None) -> bool:
        """Updates an ApplicationBranch name and project branches

        :param name: New application branch name
        :param projects_or_branches: Updated application project branches
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :raises UnsupportedOperation: If no custom branch defined in Application Branch
        :return: whether the operation succeeded
        """
        name = name or self.name
        projects_or_branches = projects_or_branches or self._project_branches
        custom_branches = [e for e in projects_or_branches if isinstance(e, Branch)]
        if len(custom_branches) == 0:
            raise exceptions.UnsupportedOperation("No custom branch defined in Application Branch during update")
        params = [("name", name)] + [(k, v) for k, v in self.api_params().items()]
        for branch in custom_branches:
            params.append(("project", branch.concerned_object.key))
            params.append(("projectBranch", branch.name))
        string_params = "&".join([f"{p[0]}={quote(str(p[1]))}" for p in params])
        api, _, _, _ = self.endpoint.api.get_details(self, Oper.UPDATE, application=self.concerned_object.key, branch=self.name)
        try:
            ok = self.post(api, params=string_params).ok
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.pop(self)
            raise

        self.name = name
        self._project_branches = projects_or_branches
        return ok

    def rename(self, new_name: str) -> bool:
        """Updates an Application Branch name

        :param str name: New application branch name
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        log.info("Renaming %s with %s", self, new_name)
        try:
            return self.update(name=new_name, projects_or_branches=self._project_branches)
        except exceptions.UnsupportedOperation as e:
            log.error("Error renaming %s: %s", self, e.message)
            return False

    def update_project_branches(self, new_project_branches: list[Union[Project, Branch]]) -> bool:
        """Updates an Application list of project branches

        :param project_branches: New application project branches
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        try:
            return self.update(name=self.name, projects_or_branches=new_project_branches)
        except exceptions.UnsupportedOperation as e:
            log.error("Error updating project branches %s: %s", self, e.message)
            return False

    def component_data(self) -> ObjectJsonRepr:
        """Returns key data"""
        return {
            "key": self.concerned_object.key,
            "name": self.concerned_object.name,
            "type": type(self.concerned_object).__name__.upper(),
            "branch": self.name,
            "url": self.url(),
        }

    def url(self) -> str:
        """Returns the URL of the Application Branch"""
        return f"{self.base_url(local=False)}/dashboard?id={self.concerned_object.key}&branch={quote(self.name)}"


def list_from(app: apps.Application, data: ApiPayload) -> dict[str, ApplicationBranch]:
    """Returns a dict of application branches form the pure App JSON"""
    if not data or "branches" not in data:
        return {}
    branch_list = {}
    for br in data["branches"]:
        api, _, params, ret = app.endpoint.api.get_details(ApplicationBranch, Oper.SEARCH, application=app.key, branch=br["name"])
        branch_data = json.loads(app.endpoint.get(api, params=params).text)[ret]
        branch_list[branch_data["branch"]] = ApplicationBranch.load(app, branch_data)
    log.debug("Returning Application branch list %s", list(branch_list.keys()))
    return branch_list
