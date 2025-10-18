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
"""

Abstraction of the Sonar sub-portfolio by reference concept

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from http import HTTPStatus
from requests import RequestException

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types, cache

from sonar import exceptions, utilities
import sonar.sqobject as sq
import sonar.util.constants as c

if TYPE_CHECKING:
    from sonar.portfolios import Portfolio


class PortfolioReference(sq.SqObject):
    """
    Abstraction of the Sonar portfolio reference concept
    """

    CACHE = cache.Cache()

    def __init__(self, reference: Portfolio, parent: Portfolio) -> None:
        """Constructor, don't use - use class methods instead"""
        self.key = f"{parent.key}:{reference.key}"
        super().__init__(endpoint=parent.endpoint, key=self.key)
        self.reference = reference
        self.parent = parent
        PortfolioReference.CACHE.put(self)
        log.debug("Created subportfolio by reference key '%s'", self.key)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str, parent_key: str) -> PortfolioReference:
        """Gets a subportfolio by reference object from its key and parent"""
        check_supported(endpoint)
        log.info("Getting subportfolio by ref key '%s:%s'", parent_key, key)
        o = PortfolioReference.CACHE.get(f"{parent_key}:{key}", endpoint.local_url)
        if not o:
            raise exceptions.ObjectNotFound
        return o

    @classmethod
    def load(cls, reference: Portfolio, parent: Portfolio) -> PortfolioReference:
        """Constructor, don't use - use class methods instead"""
        return PortfolioReference(reference=reference, parent=parent)

    @classmethod
    def create(cls, reference: Portfolio, parent: Portfolio, params: types.ApiParams = None) -> PortfolioReference:
        """Constructor, don't use - use class methods instead"""

        try:
            parent.endpoint.post("views/add_portfolio", params={"portfolio": parent.key, "reference": reference.key})
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(
                e, f"creating portfolio reference to {str(reference)} in {str(parent)}", catch_http_statuses=(HTTPStatus.BAD_REQUEST,)
            )
            raise exceptions.ObjectAlreadyExists("reference", "reference portfolioalready exists")
        return PortfolioReference(reference=reference, parent=parent)

    def __str__(self) -> str:
        return f"Portfolio reference '{self.key}'"

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Returns the object JSON representation for sonar-config"""
        return {"key": self.reference.key, "byReference": True}


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    errmsg = ""
    if endpoint.edition() not in (c.EE, c.DCE):
        errmsg = f"No portfolios in {endpoint.edition()} edition"
    if endpoint.is_sonarcloud():
        errmsg = "No portfolios in SonarQube Cloud"
    if errmsg != "":
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)
