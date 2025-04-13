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

"""sonar-config utils"""

import pathlib
import datetime
import json
from typing import Optional

_CONFIG_DATA = None
_ISSUES_SECTION = "issuesSearch"
_MAPS = "maps"


def load_config_data() -> None:
    global _CONFIG_DATA
    config_data_file = pathlib.Path(__file__).parent / "config.json"
    with open(config_data_file, "r", encoding="utf-8") as fh:
        text = fh.read()
    _CONFIG_DATA = json.loads(text)

    i_map = _CONFIG_DATA[_ISSUES_SECTION]
    i_map["allowedValues"] = {}
    new_fields_map = {}
    for old_field_name, new_field_name in i_map[_MAPS]["fields"].items():
        i_map["allowedValues"][old_field_name] = list(set(i_map[_MAPS][old_field_name].keys()))
        if new_field_name != "":
            i_map["allowedValues"][new_field_name] = list(set(i_map[_MAPS][old_field_name].values()))
            new_fields_map[new_field_name] = {v: k for k, v in i_map[_MAPS][old_field_name].items()}
    i_map[_MAPS].update(new_fields_map)


def get_java_compatibility() -> dict[int, list[tuple[int, int, int]]]:
    return {int(k): [tuple(v[0]), tuple(v[1])] for k, v in _CONFIG_DATA["javaCompatibility"].items()}


def get_scanners_versions() -> dict[int, list[tuple[int, int, int]]]:
    data = {}
    for scanner, release_info in _CONFIG_DATA["scannerVersions"].items():
        data[scanner] = {k: datetime.datetime(v[0], v[1], v[2]) for k, v in release_info.items()}
    return data


def get_issues_map(section: str) -> Optional[dict[str, str]]:
    return _CONFIG_DATA[_ISSUES_SECTION][_MAPS].get(section, None)


def get_issue_search_allowed_values(field: str) -> Optional[set[str]]:
    return _CONFIG_DATA[_ISSUES_SECTION]["allowedValues"].get(field, None)
