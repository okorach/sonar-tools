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
"""

    Abstraction of the DCE Node concept

"""

from sonar.util import types

HEALTH_GREEN = "GREEN"
HEALTH_YELLOW = "YELLOW"
HEALTH_RED = "RED"


class DceNode(object):
    """Abstraction of a DCE platform node"""

    def __init__(self, data: dict[str, any], sif: object) -> None:
        """Constructor"""
        self.json = data
        self.sif = sif

    def audit(self, audit_settings: types.ConfigSettings) -> list[object]:
        """Audits a node, implementation should be in subclasses"""
        return []
