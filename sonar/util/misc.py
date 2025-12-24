#
# sonar-tools
# Copyright (C) 2025 Olivier Korach
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
"""Miscellaneous utilities"""

from typing import Union, Any


def convert_string(value: str) -> Union[str, int, float, bool]:
    """Converts strings to corresponding types"""
    new_val: Any = value
    if not isinstance(value, str):
        return value
    if value.lower() in ("yes", "true", "on"):
        new_val = True
    elif value.lower() in ("no", "false", "off"):
        new_val = False
    else:
        try:
            new_val = int(value)
        except ValueError:
            try:
                new_val = float(value)
            except ValueError:
                pass
    return new_val


def convert_types(data: Any) -> Any:
    """Converts strings to corresponding types in a dictionary"""
    if isinstance(data, str):
        return convert_string(data)
    elif isinstance(data, dict):
        data = {k: convert_types(v) for k, v in data.items()}
    elif isinstance(data, list):
        data = [convert_types(elem) for elem in data]
    elif isinstance(data, tuple):
        data = tuple(convert_types(elem) for elem in data)
    elif isinstance(data, set):
        data = {convert_types(elem) for elem in data}
    return data
