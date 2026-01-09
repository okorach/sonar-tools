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

"""Sonar Custom Types for type hints"""

from typing import Union, Optional, Any

ConfigSettings = dict[str, Any]

AuditSettings = dict[str, Union[str, int, float, bool]]

ObjectFilter = dict[str, str]

ObjectJsonRepr = dict[str, Any]

ApiParams = Union[dict[str, Any], list[tuple[str, Any]]]
SearchParams = dict[str, Any]

ApiPayload = dict[str, Any]

KeyList = Optional[list[str]]

KeySet = Optional[set[str]]

ObjectDict = Optional[dict[str, object]]

CliParams = Optional[dict[str, Union[str, int, float, list[str]]]]

JsonPermissions = dict[str, dict[str, list[str]]]
PermissionDef = dict[str, Any]

AppBranchDef = dict[str, Any]
AppBranchProjectDef = dict[str, str]
