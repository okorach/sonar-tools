#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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

import json
from typing import Union

import sonar.logging as log
from sonar import platform as pf

import sonar.utilities as util
import sonar.sqobject as sq

from sonar.audit import rules, problem

_IMPORTABLE_PROPERTIES = ("name", "url", "secret")

_OBJECTS = {}


class WebHook(sq.SqObject):
    """
    Abstraction of the SonarQube "webhook" concept
    """

    def __init__(
        self, endpoint: pf.Platform, name: str, url: str = None, secret: str = None, project: str = None, data: dict[str, str] = None
    ) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=name)
        if data is None:
            params = util.remove_nones({"name": name, "url": url, "secret": secret, "project": project})
            data = json.loads(self.post("webhooks/create", params=params).text)["webhook"]
        self._json = data
        self.name = data["name"]  #: Webhook name
        self.key = data["key"]  #: Webhook key
        self.webhook_url = data["url"]  #: Webhook URL
        self.secret = data.get("secret", None)  #: Webhook secret
        self.project = project  #: Webhook project if project specific webhook
        self.last_delivery = data.get("latestDelivery", None)
        _OBJECTS[self.uuid()] = self

    def __str__(self) -> str:
        return f"webhook '{self.name}'"

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.endpoint.url}/admin/webhooks"

    def uuid(self) -> str:
        """
        :meta private:
        """
        return uuid(self.name, self.project, self.endpoint.url)

    def update(self, **kwargs):
        """Updates a webhook with new properties (name, url, secret)

        :param kwargs: dict - "url", "name", "secret" are the looked up keys
        :return: Nothing
        """
        params = util.remove_nones(kwargs)
        params.update({"webhook": self.key})
        self.post("webhooks/update", params=params)

    def audit(self):
        """
        :meta private:
        """
        if self._json["latestDelivery"]["success"]:
            return []
        rule = rules.get_rule(rules.RuleId.FAILED_WEBHOOK)
        return [problem.Problem(broken_rule=rule, msg=rule.msg.format(str(self)), concerned_object=self)]

    def to_json(self, full=False):
        """Exports a Webhook configuration in JSON format

        :param full: Whether to export all properties, including those that can't be set, or not, defaults to False
        :type full: bool, optional
        :return: The configuration of the DevOps platform (except secrets)
        :rtype: dict
        """
        return util.filter_export(self._json, _IMPORTABLE_PROPERTIES, full)


def search(endpoint: pf.Platform, params: dict[str, str] = None) -> dict[str, WebHook]:
    """Searches webhooks

    :param params: Filters to narrow down the search, can only be "project"
    :return: List of webhooks
    :rtype: dict{<key>: <WebHook>}
    """
    return sq.search_objects(api="webhooks/list", params=params, returned_field="webhooks", key_field="key", object_class=WebHook, endpoint=endpoint)


def get_list(endpoint: pf.Platform, project_key: str = None) -> dict[str, WebHook]:
    """Returns the list of web hooks, global ones or for a project if project key is given"""
    log.debug("Getting webhooks for project key %s", str(project_key))
    params = None
    if project_key is not None:
        params = {"project": project_key}
    return search(endpoint, params)


def export(endpoint: pf.Platform, project_key: str = None, full: bool = False) -> Union[dict[str, str], None]:
    """Export webhooks of a project as JSON"""
    json_data = {}
    for wb in get_list(endpoint, project_key).values():
        j = wb.to_json(full)
        j.pop("name", None)
        json_data[wb.name] = util.remove_nones(j)
    return json_data if len(json_data) > 0 else None


def create(endpoint: pf.Platform, name: str, url: str, secret: str = None, project: str = None) -> WebHook:
    """Creates a webhook, global if project key is None, othewise project specific"""
    return WebHook(endpoint=endpoint, name=name, url=url, secret=secret, project=project)


def update(endpoint: pf.Platform, name: str, **kwargs) -> None:
    """Updates a webhook with data in kwargs"""
    project_key = kwargs.pop("project", None)
    get_list(endpoint, project_key)
    if uuid(name, project_key, endpoint.url) not in _OBJECTS:
        create(endpoint, name, kwargs["url"], kwargs["secret"], project=project_key)
    else:
        get_object(endpoint, name, project_key=project_key, data=kwargs).update(**kwargs)


def get_object(endpoint: pf.Platform, name: str, project_key: str = None, data: dict[str, str] = None) -> WebHook:
    """Gets a WebHook object from name a project key"""
    log.debug("Getting webhook name %s project key %s data = %s", name, str(project_key), str(data))
    uid = uuid(name, project_key, endpoint.url)
    if uid not in _OBJECTS:
        _ = WebHook(endpoint=endpoint, name=name, project=project_key, data=data)
    return _OBJECTS[uid]


def uuid(name: str, project_key: str, url: str) -> str:
    """Returns object unique id"""
    # FIXME: Make uuid really unique between global and project
    if not project_key:
        return f"{name}@{url}"
    else:
        return f"{name}#{project_key}@{url}"


def audit(endpoint: pf.Platform) -> list[problem.Problem]:
    """Audits web hooks and returns list of found problems"""
    log.info("Auditing webhooks")
    problems = []
    for wh in search(endpoint=endpoint).values():
        problems += wh.audit()
    return problems
