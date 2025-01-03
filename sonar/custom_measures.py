#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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
import sonar.platform as pf


class CustomMeasure(sq.SqObject):
    API_ROOT = "api/custom_measures/"

    def __init__(
        self, key: str, endpoint: pf.Platform, uuid: str = None, project_key: str = None, value: any = None, description: str = None
    ) -> None:
        super().__init__(endpoint=endpoint, key=key)
        self.uuid = uuid
        self.projectKey = project_key
        self.value = value
        self.description = description

    def create(self, project_key: str, metric_key: str, value: any, description: str = None) -> bool:
        return self.post(
            CustomMeasure.API_ROOT + "create",
            {
                "component": project_key,
                "metricKeys": metric_key,
                "value": value,
                "description": description,
            },
        ).ok

    def update(self, value: any, description: str = None) -> bool:
        """Updates a custom measure"""
        return self.post(
            CustomMeasure.API_ROOT + "update",
            {"id": self.uuid, "value": value, "description": description},
        ).ok

    def delete(self) -> bool:
        """Deletes a custom measure"""
        return self.post(CustomMeasure.API_ROOT + "delete", {"id": self.uuid}).ok


def search(endpoint: pf.Platform, project_key):
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


def update(project_key, metric_key, value, description=None, endpoint: pf.Platform = None):
    for m in search(endpoint, project_key):
        if m.key == metric_key:
            m.update(value, description)
            break


def delete(id, endpoint: pf.Platform):
    return endpoint.post(CustomMeasure.API_ROOT + "delete", {"id": id})
