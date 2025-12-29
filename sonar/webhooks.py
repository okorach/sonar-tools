#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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

"""Abstraction of the SonarQube webhook concept"""

from __future__ import annotations
from typing import Optional, ClassVar, TYPE_CHECKING

import json

import sonar.logging as log
from sonar import exceptions
from sonar.util import cache, constants as c
import sonar.util.misc as util
import sonar.sqobject as sq

from sonar.audit import rules, problem

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr

_IMPORTABLE_PROPERTIES = ("name", "url", "secret")


class WebHook(sq.SqObject):
    """
    Abstraction of the SonarQube "webhook" concept
    """

    CACHE: ClassVar[cache.Cache] = cache.Cache()
    API: ClassVar[dict[str, str]] = {
        c.CREATE: "webhooks/create",
        c.READ: "webhooks/list",
        c.UPDATE: "webhooks/update",
        c.LIST: "webhooks/list",
        c.DELETE: "webhooks/delete",
    }
    SEARCH_KEY_FIELD: ClassVar[str] = "key"
    SEARCH_RETURN_FIELD: ClassVar[str] = "webhooks"

    def __init__(self, endpoint: Platform, name: str, url: str, secret: Optional[str] = None, project: Optional[str] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=name)
        self.name = name  #: Webhook name
        self.webhook_url = url  #: Webhook key
        self.secret = secret  #: Webhook secret
        self.project = project  #: Webhook project, optional
        self.last_delivery: Optional[str] = None  #: Webhook last delivery timestamp
        self.project = project  #: Webhook project if project specific webhook
        WebHook.CACHE.put(self)

    @classmethod
    def create(cls, endpoint: Platform, name: str, url: str, secret: Optional[str] = None, project: Optional[str] = None) -> WebHook:
        """Creates a WebHook object in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Webhook name
        :param str url: Webhook URL
        :param str secret: Webhook secret, optional
        :param str project: Webhook project key, optional
        :return: The created WebHook
        """
        log.info("Creating webhook name %s, url %s project %s", name, url, str(project))
        params = util.remove_nones({"name": name, "url": url, "secret": secret, "project": project})
        endpoint.post(WebHook.API[c.CREATE], params=params)
        o = cls(endpoint, name=name, url=url, secret=secret, project=project)
        o.refresh()
        return o

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> WebHook:
        """Creates and loads a local WebHook object with data payload received from API

        :param Platform endpoint: Reference to the SonarQube platform
        :param ApiPayload data: The webhook data received from the API
        :return: The created WebHook
        """
        log.debug("Loading Webhook with %s", data)
        name, project = data["name"], data.get("project", None)
        if (o := WebHook.CACHE.get(name, project, endpoint.local_url)) is None:
            o = WebHook(endpoint, name, data["url"], data.get("secret", None), project)
        o.reload(data)
        return o

    @classmethod
    def get_object(cls, endpoint: Platform, name: str, project_key: Optional[str] = None) -> WebHook:
        """Gets a WebHook object from its name and an eventual project key"""
        log.debug("Getting webhook name %s project key %s", name, str(project_key))
        if o := WebHook.CACHE.get(name, project_key, endpoint.local_url):
            return o
        try:
            whs = list(get_list(endpoint, project_key).values())
            return next(wh for wh in whs if wh.name == name)
        except StopIteration as e:
            raise exceptions.ObjectNotFound(project_key, f"Webhook '{name}' of project '{project_key}' not found") from e

    def __str__(self) -> str:
        return f"webhook '{self.name}'"

    def __hash__(self) -> int:
        """
        Returns an object unique Id
        :meta private:
        """
        return hash((self.name, self.project, self.endpoint.local_url))

    def refresh(self) -> None:
        """Reads the Webhook data on the SonarQube platform and updates the local object"""
        log.debug("Refreshing %s with proj %s", str(self), str(self.project))
        data = json.loads(self.get(WebHook.API[c.LIST], params=None if not self.project else {"project": self.project}).text)
        log.debug("Refreshing %s with data %s", str(self), str(data))
        wh_data = next((wh for wh in data["webhooks"] if wh["name"] == self.name), None)
        if wh_data is None:
            wh_name = str(self)
            name = self.name
            WebHook.CACHE.pop(self)
            raise exceptions.ObjectNotFound(name, f"{wh_name} not found")
        self.reload(wh_data)

    def reload(self, data: ApiPayload) -> None:
        """Reloads a WebHook from the payload gotten from SonarQube"""
        log.debug("Loading %s with %s", str(self), str(data))
        self.sq_json = self.sq_json or {} | data
        self.name = data["name"]
        self.key = data["key"]
        self.webhook_url = data["url"]
        self.secret = data.get("secret", None) or self.secret
        self.last_delivery = data.get("latestDelivery", None)

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.base_url(local=False)}/admin/webhooks"

    def update(self, **kwargs: str) -> bool:
        """Updates a webhook with new properties (name, url, secret)

        :param kwargs: dict - "url", "name", "secret" are the looked up keys
        :return: Whether the operation succeeded
        """
        log.info("Updating %s with %s", str(self), str(self.project))
        params = {"webhook": self.key, "name": self.name, "url": self.webhook_url} | util.remove_nones(kwargs)
        ok = self.post(WebHook.API[c.UPDATE], params=params).ok
        self.refresh()
        return ok

    def audit(self) -> list[problem.Problem]:
        """
        :meta private:
        """
        if "latestDelivery" not in self.sq_json or self.sq_json["latestDelivery"]["success"]:
            return []
        return [problem.Problem(rules.get_rule(rules.RuleId.FAILED_WEBHOOK), self, str(self))]

    def to_json(self, full: bool = False) -> dict[str, any]:
        """Exports a Webhook configuration in JSON format

        :param full: Whether to export all properties, including those that can't be set, or not, defaults to False
        :type full: bool, optional
        :return: The configuration of the DevOps platform (except secrets)
        :rtype: dict
        """
        return util.filter_export(self.sq_json, _IMPORTABLE_PROPERTIES, full)

    def api_params(self, op: str) -> ApiParams:
        """Returns the std api params to pass for a given webhook"""
        ops = {c.READ: {"webhook": self.key}}
        return ops[op] if op and op in ops else ops[c.READ]


def search(endpoint: Platform, params: ApiParams = None) -> dict[str, WebHook]:
    """Searches webhooks

    :param ApiParams params: Filters to narrow down the search, can only be "project"
    :return: List of webhooks
    """
    return WebHook.search_objects(endpoint=endpoint, params=params)


def get_list(endpoint: Platform, project_key: Optional[str] = None) -> dict[str, WebHook]:
    """Returns the list of web hooks, global ones or for a project if project key is given"""
    log.debug("Getting webhooks for project key %s", str(project_key))
    wh_list = search(endpoint, {"project": project_key} if project_key else None)
    for wh in wh_list.values():
        wh.project = project_key
    return wh_list


def export(endpoint: Platform, project_key: Optional[str] = None, full: bool = False) -> ObjectJsonRepr:
    """Export webhooks of a project as JSON"""
    json_data = {}
    for wb in get_list(endpoint, project_key).values():
        j = wb.to_json(full)
        j.pop("name", None)
        json_data[wb.name] = util.remove_nones(j)
    return json_data if len(json_data) > 0 else None


def import_config(endpoint: Platform, data: list[dict[str, str]], project_key: Optional[str] = None) -> None:
    """Imports a set of webhooks defined from a JSON description"""
    log.info("Importing webhooks %s for %s", str(data), str(project_key))
    current_wh = get_list(endpoint, project_key=project_key)
    existing_webhooks = {wh.name: k for k, wh in current_wh.items()}

    # FIXME: Handle several webhooks with same name
    for wh_data in data:
        wh_name = wh_data["name"]
        if wh_name in existing_webhooks:
            current_wh[existing_webhooks[wh_name]].update(**wh_data)
        else:
            hook = WebHook.create(endpoint=endpoint, name=wh_name, url=wh_data.get("url", "https://to.be.defined"), project=project_key)
            hook.update(**wh_data)


def audit(endpoint: Platform) -> list[problem.Problem]:
    """Audits web hooks and returns list of found problems"""
    log.info("Auditing webhooks")
    problems = []
    for wh in search(endpoint=endpoint).values():
        problems += wh.audit()
    return problems
