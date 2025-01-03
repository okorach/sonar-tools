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

""" Sonar Custom Types for type hints """

from typing import Union, Optional

ConfigSettings = dict[str, str]

ObjectFilter = dict[str, str]

ObjectJsonRepr = dict[str, any]

ApiParams = Optional[dict[str, str]]

ApiPayload = Optional[dict[str, any]]

KeyList = Optional[list[str]]

ObjectDict = Optional[dict[str, object]]

CliParams = Optional[dict[str, Union[str, int, float, list[str]]]]

JsonPermissions = dict[str, dict[str, list[str]]]
