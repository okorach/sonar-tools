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
"""

Abstraction of the Sonar sub-portfolio by reference concept

"""

from __future__ import annotations
from typing import TYPE_CHECKING

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache

from sonar import exceptions
import sonar.util.constants as c

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ObjectJsonRepr, ConfigSettings


class PortfolioReference(SqObject):
    """
    Abstraction of the Sonar portfolio reference concept
    """

    CACHE = cache.Cache()

    def __init__(self, reference: object, parent: object) -> None:
        """Constructor, don't use - use class methods instead"""
        self.key = f"{parent.key}:{reference.key}"
        super().__init__(endpoint=parent.endpoint, key=self.key)
        self.reference = reference
        self.parent = parent
        PortfolioReference.CACHE.put(self)
        log.debug("Created subportfolio by reference key '%s'", self.key)

    @classmethod
    def get_object(cls, endpoint: Platform, key: str, parent_key: str) -> PortfolioReference:
        """Gets a subportfolio by reference object from its key and parent"""
        check_supported(endpoint)
        log.info("Getting subportfolio by ref key '%s:%s'", parent_key, key)
        o = PortfolioReference.CACHE.get(f"{parent_key}:{key}", endpoint.local_url)
        if not o:
            raise exceptions.ObjectNotFound(f"{parent_key}:{key}", f"Portfolio reference key '{parent_key}:{key}' not found")
        return o

    @classmethod
    def load(cls, reference: object, parent: object) -> PortfolioReference:
        """Constructor, don't use - use class methods instead"""
        return PortfolioReference(reference=reference, parent=parent)

    @classmethod
    def create(cls, reference: object, parent: object, params: ApiParams = None) -> PortfolioReference:
        """Constructor, don't use - use class methods instead"""
        check_supported(parent.endpoint)
        parent.endpoint.post("views/add_portfolio", params={"portfolio": parent.key, "reference": reference.key})
        return PortfolioReference(reference=reference, parent=parent)

    def __str__(self) -> str:
        return f"Portfolio reference '{self.key}'"

    def to_json(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """Returns the object JSON representation for sonar-config"""
        return {"key": self.reference.key, "byReference": True}


def check_supported(endpoint: Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    errmsg = ""
    if endpoint.edition() not in (c.EE, c.DCE):
        errmsg = f"No portfolios in {endpoint.edition()} edition"
    if endpoint.is_sonarcloud():
        errmsg = "No portfolios in SonarQube Cloud"
    if errmsg != "":
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)
