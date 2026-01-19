#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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
from typing import Any, Optional, TYPE_CHECKING

from sonar.sqobject import SqObject

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload


class CustomMeasure(SqObject):
    """Abstraction of the SonarQube customer measure concept"""

    API_ROOT = "api/custom_measures/"

    def __init__(
        self,
        endpoint: Platform,
        data: ApiPayload,
        uuid: Optional[str] = None,
        project_key: Optional[str] = None,
        value: Any = None,
        description: Optional[str] = None,
    ) -> None:
        super().__init__(endpoint, data)
        self.uuid = uuid
        self.projectKey = project_key
        self.value = value
        self.description = description

    @classmethod
    def search(cls, endpoint: Platform, project_key: str) -> list[CustomMeasure]:
        """Searches custom measures of a project"""
        data = json.loads(endpoint.get(cls.API_ROOT + "search", params={"projectKey": project_key, "ps": 500}).text)
        # nbr_measures = data['total'] if > 500, we're screwed...
        return [
            cls(
                uuid=m["id"],
                key=m["metric"]["key"],
                project_key=m["projectKey"],
                value=m["value"],
                description=m["description"],
                endpoint=endpoint,
            )
            for m in data["customMeasures"]
        ]

    def create(self, project_key: str, metric_key: str, value: Any, description: Optional[str] = None) -> bool:
        return self.post(
            CustomMeasure.API_ROOT + "create",
            {
                "component": project_key,
                "metricKeys": metric_key,
                "value": value,
                "description": description,
            },
        ).ok

    def update(self, value: Any, description: Optional[str] = None) -> bool:
        """Updates a custom measure"""
        return self.post(
            CustomMeasure.API_ROOT + "update",
            {"id": self.uuid, "value": value, "description": description},
        ).ok

    def delete(self) -> bool:
        """Deletes a custom measure"""
        return self.post(CustomMeasure.API_ROOT + "delete", {"id": self.uuid}).ok


def update(project_key: str, metric_key: str, value: Any, description: Optional[str] = None, endpoint: Optional[Platform] = None) -> None:
    """Update custom measure of a project"""
    c_meas = next(m for m in CustomMeasure.search(endpoint, project_key) if m.key == metric_key)
    c_meas.update(value, description)


def delete(id: str, endpoint: Platform) -> bool:
    """Delects a custom measure, returns whether the operation succeeded"""
    return endpoint.post(CustomMeasure.API_ROOT + "delete", {"id": id})
