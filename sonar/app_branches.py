#
# sonar-tools
# Copyright (C) 2024-2025 Olivier Korach
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
from typing import Optional, TYPE_CHECKING

import json
from http import HTTPStatus
from requests import RequestException
from requests.utils import quote

import sonar.logging as log
from sonar.util import types, cache

from sonar.components import Component

from sonar.branches import Branch
from sonar import exceptions, projects, utilities
import sonar.util.constants as c

if TYPE_CHECKING:
    from sonar.applications import Application

_NOT_SUPPORTED = "Applications not supported in community edition"


class ApplicationBranch(Component):
    """
    Abstraction of the SonarQube "application branch" concept
    """

    CACHE = cache.Cache() # :type: cache.Cache
    API = { # :type: dict[str, str]
        c.CREATE: "applications/create_branch", # :type: str
        c.GET: "applications/show", # :type: str
        c.UPDATE: "applications/update_branch", # :type: str
        c.DELETE: "applications/delete_branch", # :type: str
    }

    def __init__(
        self, app: Application, name: str, project_branches: list[Branch], is_main: bool = False, branch_data: Optional[types.ApiPayload] = None
    ) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=app.endpoint, key=f"{app.key} BRANCH {name}")
        self.concerned_object = app # :type: Application
        self.name = name # :type: str
        self.sq_json = branch_data # :type: types.ApiPayload
        self._is_main = is_main # :type: bool
        self._project_branches = project_branches # :type: list[Branch]
        self._last_analysis = None # :type: Optional[datetime]
        log.debug("Created %s with uuid %d id %x", str(self), hash(self), id(self))
        ApplicationBranch.CACHE.put(self)

    @classmethod
    def get_object(cls, app: Application, branch_name: str) -> ApplicationBranch:
        """Gets an Application object from SonarQube

        :param Application app: Reference to the Application holding that branch
        :param str branch_name: Name of the application branch
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application or Brnach not found
        :return: The found ApplicationBranch
        :rtype: ApplicationBranch
        """
        if app.endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        o = ApplicationBranch.CACHE.get(app.key, branch_name, app.base_url())
        if o:
            return o
        app.refresh()
        app.branches()
        o = ApplicationBranch.CACHE.get(app.key, branch_name, app.base_url())
        if o:
            return o
        raise exceptions.ObjectNotFound(app.key, f"Application key '{app.key}' branch '{branch_name}' not found")

    @classmethod
    def create(cls, app: Application, name: str, project_branches: list[Branch]) -> ApplicationBranch:
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
        params = {"application": app.key, "branch": name, "project": [], "projectBranch": []}
        for obj in project_branches:
            if isinstance(obj, Branch):
                params["project"].append(obj.concerned_object.key)
                params["projectBranch"].append(obj.name)
            else:  # Default main branch of project
                params["project"].append(obj.key)
                params["projectBranch"].append("")
        try:
            app.endpoint.post(ApplicationBranch.API[c.CREATE], params=params)
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"creating branch {name} of {str(app)}", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(f"{str(app)} branch '{name}", e.response.text)
        return ApplicationBranch(app=app, name=name, project_branches=project_branches)

    @classmethod
    def load(cls, app: Application, branch_data: types.ApiPayload) -> ApplicationBranch:
        project_branches = []
        for proj_data in branch_data["projects"]:
            proj = projects.Project.get_object(app.endpoint, proj_data["key"])
            project_branches.append(Branch.get_object(concerned_object=proj, branch_name=proj_data["branch"]))
        return ApplicationBranch(
            app=app, name=branch_data["branch"], project_branches=project_branches, is_main=branch_data.get("isMain", False), branch_data=branch_data
        )

    def __str__(self) -> str:
        return f"application '{self.concerned_object.key}' branch '{self.name}'"

    def __hash__(self) -> int:
        """Returns the object UUID"""
        return hash((self.concerned_object.key, self.name, self.base_url()))

    def is_main(self) -> bool:
        """Returns whether app branch is main"""
        return self._is_main

    def get_tags(self, **kwargs) -> list[str]:
        """
        :return: The tags of the project corresponding to the branch
        """
        return self.concerned_object.get_tags(**kwargs)

    def projects_branches(self) -> list[Branch]:
        """
        :return: The list of project branches included in the application branch
        :rtype: list[Branch]
        """
        return self._project_branches

    def delete(self) -> bool:
        """Deletes an ApplicationBranch

        :return: Whether the delete succeeded
        :rtype: bool
        """
        if self.is_main():
            log.warning("Can't delete main %s, simply delete the application for that", str(self))
            return False
        return super().delete()

    def reload(self, data: types.ApiPayload) -> None:
        """Reloads an App Branch from JSON data coming from Sonar"""
        super().reload(data)
        self.name = data.get("branch", "")

    def export(self) -> types.ObjectJsonRepr:
        """Exports an application branch

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
        log.info("Exporting %s from %s", self, self.sq_json)
        jsondata = {"projects": {b["key"]: b["branch"] if b["selected"] else utilities.DEFAULT for b in self.sq_json["projects"]}}
        if self.is_main():
            jsondata["isMain"] = True
        return jsondata

    def update(self, name: str, project_branches: list[Branch]) -> bool:
        """Updates an ApplicationBranch name and project branches

        :param str name: New application branch name
        :param list[Branch] project_branches: New application project branches
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        if not name:
            name = self.name
        if not project_branches or len(project_branches) == 0:
            return False
        params = self.api_params()
        params.update({"name": name, "project": [], "projectBranch": []})
        for branch in project_branches:
            params["project"].append(branch.concerned_object.key)
            br_name = "" if branch.is_main() else branch.name
            params["projectBranch"].append(br_name)
        try:
            ok = self.post(ApplicationBranch.API[c.UPDATE], params=params).ok
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"updating {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            ApplicationBranch.CACHE.pop(self)
            raise exceptions.ObjectNotFound(str(self), e.response.text)

        self.name = name
        self._project_branches = project_branches
        return ok

    def rename(self, new_name: str) -> bool:
        """Updates an Application Branch name

        :param str name: New application branch name
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        return self.update(name=new_name, project_branches=self._project_branches)

    def update_project_branches(self, new_project_branches: list[Branch]) -> bool:
        """Updates an Application list of project branches

        :param list[Branch] project_branches: New application project branches
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        return self.update(name=self.name, project_branches=new_project_branches)

    def api_params(self, op: Optional[str] = None) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.READ: {"application": self.concerned_object.key, "branch": self.name}}
        return ops[op] if op and op in ops else ops[c.READ]

    def component_data(self) -> types.Obj:
        """Returns key data"""
        return {
            "key": self.concerned_object.key,
            "name": self.concerned_object.name,
            "type": utilities.class_name(self.concerned_object).upper(),
            "branch": self.name,
            "url": self.url(),
        }

    def url(self) -> str:
        """Returns the URL of the Application Branch"""
        return f"{self.base_url(local=False)}/dashboard?id={self.concerned_object.key}&branch={quote(self.name)}"


def exists(app: Application, branch: str) -> bool:
    """Returns whether an application branch exists"""
    try:
        ApplicationBranch.get_object(app, branch)
        return True
    except exceptions.ObjectNotFound:
        return False


def list_from(app: Application, data: types.ApiPayload) -> dict[str, ApplicationBranch]:
    """Returns a dict of application branches from the pure App JSON"""
    if not data or "branches" not in data:
        return {}
    branch_list = {}
    for br in data["branches"]:
        branch_data = json.loads(app.get(ApplicationBranch.API[c.GET], params={"application": app.key, "branch": br["name"]}).text)["application"]
        branch_list[branch_data["branch"]] = ApplicationBranch.load(app, branch_data)
    log.debug("Returning Application branch list %s", str(list(branch_list.keys())))
    return branch_list
