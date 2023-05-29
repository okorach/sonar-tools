#
# sonar-tools
# Copyright (C) 2022-2023 Olivier Korach
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
import sonar.utilities as util
import sonar.sqobject as sq

from sonar.audit import rules, problem

_IMPORTABLE_PROPERTIES = ("name", "url", "secret")

_OBJECTS = {}


class WebHook(sq.SqObject):
    """
    Abstraction of the SonarQube "webhook" concept
    """

    def __init__(self, name, endpoint, url=None, secret=None, project=None, data=None):
        super().__init__(name, endpoint)
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

    def __str__(self):
        return f"webhook '{self.name}'"

    def url(self):
        return f"{self.endpoint.url}/admin/webhooks"

    def uuid(self):
        """
        :meta private:
        """
        return _uuid(self.name, self.project)

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
        return [problem.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]

    def to_json(self, full=False):
        """Exports a Webhook configuration in JSON format

        :param full: Whether to export all properties, including those that can't be set, or not, defaults to False
        :type full: bool, optional
        :return: The configuration of the DevOps platform (except secrets)
        :rtype: dict
        """
        return util.filter_export(self._json, _IMPORTABLE_PROPERTIES, full)


def search(endpoint, params=None):
    """Searches webhooks

    :param params: Filters to narrow down the search, can only be "project"
    :return: List of webhooks
    :rtype: dict{<key>: <WebHook>}
    """
    return sq.search_objects(api="webhooks/list", params=params, returned_field="webhooks", key_field="key", object_class=WebHook, endpoint=endpoint)


def get_list(endpoint, project_key=None):
    util.logger.debug("Getting webhooks for project key %s", str(project_key))
    params = None
    if project_key is not None:
        params = {"project": project_key}
    return search(endpoint, params)


def export(endpoint, project_key=None, full=False):
    json_data = {}
    for wb in get_list(endpoint, project_key).values():
        j = wb.to_json(full)
        j.pop("name", None)
        json_data[wb.name] = util.remove_nones(j)
    return json_data if len(json_data) > 0 else None


def create(endpoint, name, url, secret=None, project=None):
    return WebHook(name, endpoint, url=url, secret=secret, project=project)


def update(endpoint, name, **kwargs):
    project_key = kwargs.pop("project", None)
    get_list(endpoint, project_key)
    if _uuid(name, project_key) not in _OBJECTS:
        create(endpoint, name, kwargs["url"], kwargs["secret"], project=project_key)
    else:
        get_object(name, endpoint, project_key=project_key, data=kwargs).update(**kwargs)


def get_object(name, endpoint, project_key=None, data=None):
    util.logger.debug("Getting webhook name %s project key %s data = %s", name, str(project_key), str(data))
    u = _uuid(name, project_key)
    if u not in _OBJECTS:
        _ = WebHook(name=name, endpoint=endpoint, data=data)
    return _OBJECTS[u]


def _uuid(name, project_key):
    # FIXME: Make UUID really unique
    p = "" if project_key is None else f":PROJECT:{project_key}"
    return f"{name}{p}"


def audit(endpoint):
    """
    :meta private:
    """
    util.logger.info("Auditing webhooks")
    problems = []
    for wh in search(endpoint=endpoint).values():
        problems += wh.audit()
    return problems
