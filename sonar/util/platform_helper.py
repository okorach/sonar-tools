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
"""Helper tools for the Platform object"""

from typing import Any
from sonar import settings
from sonar import utilities as util
from sonar.util import common_json_helper

_PERM_TPL_IMPORTABLE_PROPERTIES = ("name", "description", "pattern", "defaultFor", "permissions")


def normalize_api(api: str) -> str:
    """Normalizes an API based on its multiple original forms"""
    if api.startswith("/api/"):
        pass
    elif api.startswith("api/"):
        api = "/" + api
    elif api.startswith("/"):
        api = "/api" + api
    else:
        api = "/api/" + api
    return api


def convert_basics_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts sonar-config "plaform" section old JSON report format to new format"""
    if "plugins" in old_json:
        old_json["plugins"] = util.dict_to_list(old_json["plugins"], "key")
    return old_json


def convert_template_json(json_data: dict[str, Any], full: bool = False) -> dict[str, Any]:
    """Converts a Perm Template JSON from old to new format"""
    json_data = common_json_helper.convert_common_fields(json_data)
    return util.remove_nones(util.filter_export(json_data, _PERM_TPL_IMPORTABLE_PROPERTIES, full))


def convert_global_settings_json(old_json: dict[str, Any], full: bool = False) -> dict[str, Any]:
    """Converts sonar-config "globalSettings" section old JSON report format to new format"""
    new_json = old_json.copy()
    special_categories = (settings.LANGUAGES_SETTINGS, settings.DEVOPS_INTEGRATION, "permissions", "permissionTemplates")
    for categ in [cat for cat in settings.CATEGORIES if cat not in special_categories]:
        new_json[categ] = util.sort_list_by_key(util.dict_to_list(dict(sorted(old_json[categ].items())), "key"), "key")
    for k, v in old_json[settings.LANGUAGES_SETTINGS].items():
        new_json[settings.LANGUAGES_SETTINGS] = new_json.get(settings.LANGUAGES_SETTINGS, None) or {}
        new_json[settings.LANGUAGES_SETTINGS][k] = util.sort_list_by_key(util.dict_to_list(v, "key"), "key")
    new_json[settings.LANGUAGES_SETTINGS] = util.dict_to_list(dict(sorted(new_json[settings.LANGUAGES_SETTINGS].items())), "language", "settings")
    new_json[settings.DEVOPS_INTEGRATION] = util.dict_to_list(dict(sorted(old_json[settings.DEVOPS_INTEGRATION].items())), "key")
    for k in new_json["permissionTemplates"]:
        new_json["permissionTemplates"][k] = convert_template_json(new_json["permissionTemplates"][k], full)
    new_json["permissionTemplates"] = util.dict_to_list(new_json["permissionTemplates"], "key")
    new_json["webhooks"] = util.dict_to_list(new_json["webhooks"], "name")
    new_json = common_json_helper.convert_common_fields(new_json)

    return util.order_dict(new_json, [*settings.CATEGORIES, "permissions", "permissionTemplates"])
