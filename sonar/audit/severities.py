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

"""Sonar Audit severities"""
import enum
from typing import Optional


class Severity(enum.Enum):
    """Abstraction of severity"""

    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

    def __str__(self) -> str:
        """str() implementation"""
        return repr(self.name)[1:-1]


def to_severity(val: str) -> Optional[Severity]:
    """Converts a string to a Severity enum"""
    for enum_val in Severity:
        if repr(enum_val.name)[1:-1] == val:
            return enum_val
    return None
