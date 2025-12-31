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

from typing import Any

from pathlib import Path
import json
from collections import defaultdict

from sonar.util import misc
import sonar.logging as log

API_DEF = {}


def load():
    """Loads the API definitions"""
    global API_DEF
    with misc.open_file(Path(__file__).parent / "api.json", "r") as f:
        api_data = json.load(f)
    log.debug("API data: %s", misc.json_dump(api_data))
    API_DEF = api_data
    return api_data


def get_api_def(obj_name: str, op: str, sonar_version: tuple[int, int, int]) -> dict[str, Any]:
    """Gets the API definition for a given object and Sonar version"""
    global API_DEF
    if obj_name not in API_DEF:
        raise ValueError(f"Object {obj_name} not found in API definitions")
    data = next(v for k, v in API_DEF[obj_name].items() if sonar_version >= tuple(int(s) for s in k.split(".")))
    if op not in data:
        raise ValueError(f"Operation {op} not found in API definitions for {obj_name}")
    return data[op]


def prep_params(api_def: dict[str, Any], **kwargs: Any) -> tuple[str, str, dict[str, Any]]:
    """Prepares the parameters for the API call"""
    api = api_def["api"].format(**kwargs)
    params = api_def.get("params", {})
    if isinstance(params, list):
        params = {p: "{" + p + "}" for p in api_def.get("params", [])}
    params = {k: v.format_map(defaultdict(str, **kwargs)) for k, v in params.items()}
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    return api, api_def["method"], params
