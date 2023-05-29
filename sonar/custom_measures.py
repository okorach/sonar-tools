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

    Abstraction of the SonarQube "custom measure" concept

"""
import json
import sonar.sqobject as sq


class CustomMeasure(sq.SqObject):
    API_ROOT = "api/custom_measures/"

    def __init__(
        self,
        key=None,
        endpoint=None,
        uuid=None,
        project_key=None,
        value=None,
        description=None,
    ):
        super().__init__(key, endpoint)
        self.uuid = uuid
        self.projectKey = project_key
        self.value = value
        self.description = description

    def create(self, project_key, metric_key, value, description=None):
        return self.post(
            CustomMeasure.API_ROOT + "create",
            {
                "component": project_key,
                "metricKeys": metric_key,
                "value": value,
                "description": description,
            },
        )

    def update(self, value, description=None):
        return self.post(
            CustomMeasure.API_ROOT + "update",
            {"id": self.uuid, "value": value, "description": description},
        )

    def delete(self):
        return self.post(CustomMeasure.API_ROOT + "delete", {"id": self.uuid})


def search(endpoint, project_key):
    data = json.loads(endpoint.get(CustomMeasure.API_ROOT + "search", params={"projectKey": project_key, "ps": 500}).text)
    # nbr_measures = data['total'] if > 500, we're screwed...
    measures = []
    for m in data["customMeasures"]:
        measures.append(
            CustomMeasure(
                uuid=m["id"],
                key=m["metric"]["key"],
                project_key=m["projectKey"],
                value=m["value"],
                description=m["description"],
                endpoint=endpoint,
            )
        )
    return measures


def update(project_key, metric_key, value, description=None, endpoint=None):
    for m in search(endpoint, project_key):
        if m.key == metric_key:
            m.update(value, description)
            break


def delete(id, endpoint):
    return endpoint.post(CustomMeasure.API_ROOT + "delete", {"id": id})
