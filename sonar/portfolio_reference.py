#
# sonar-tools
# Copyright (C) 2024 Olivier Korach
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
from http import HTTPStatus
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types

from sonar import exceptions, utilities
import sonar.sqobject as sq

_OBJECTS = {}


class PortfolioReference(sq.SqObject):
    """
    Abstraction of the Sonar portfolio reference concept
    """

    def __init__(self, reference: object, parent: object) -> None:
        """Constructor, don't use - use class methods instead"""
        self.key = f"{parent.key}:{reference.key}"
        super().__init__(endpoint=parent.endpoint, key=self.key)
        self.reference = reference
        self.parent = parent
        uid = self.uuid()
        _OBJECTS[uid] = self
        log.debug("Created subportfolio by reference key '%s'", self.key)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str, parent_key: str) -> PortfolioReference:
        """Gets a subportfolio by reference object from its key and parent"""
        check_supported(endpoint)
        log.info("Getting subportfolio by ref key '%s:%s'", parent_key, key)
        uid = sq.uuid(f"{parent_key}:{key}", endpoint.url)
        if uid not in _OBJECTS:
            raise exceptions.ObjectNotFound
        return _OBJECTS[uid]

    @classmethod
    def load(cls, reference: object, parent: object) -> PortfolioReference:
        """Constructor, don't use - use class methods instead"""
        return PortfolioReference(reference=reference, parent=parent)

    @classmethod
    def create(cls, reference: object, parent: object, params: types.ApiParams = None) -> PortfolioReference:
        """Constructor, don't use - use class methods instead"""

        try:
            parent.endpoint.post("views/add_portfolio", params={"portfolio": parent.key, "reference": reference.key})
        except (ConnectionError, RequestException) as e:
            if isinstance(e, HTTPError) and e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists
            log.critical("%s while creating portfolio reference to %s in %s", utilities.error_msg(e), str(reference), str(parent))
            raise e
        return PortfolioReference(reference=reference, parent=parent)

    def __str__(self) -> str:
        return f"Portfolio reference '{self.key}'"

    def uuid(self) -> str:
        """Returns the object unique id in its class"""
        return f"{self.key}@{self.endpoint.url}"

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Returns the object JSON representation for sonar-config"""
        return {"key": self.reference.key, "byReference": True}


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    errmsg = ""
    if endpoint.edition() not in ("enterprise", "datacenter"):
        errmsg = f"No portfolios in {endpoint.edition()} edition"
    if endpoint.is_sonarcloud():
        errmsg = "No portfolios in SonarCloud"
    if errmsg != "":
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)
