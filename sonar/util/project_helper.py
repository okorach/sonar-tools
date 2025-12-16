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
"""Helper tools for the Project object"""

from typing import Any
from sonar import utilities as util
from sonar.util import common_json_helper
from sonar import logging as log

UNNEEDED_TASK_DATA = (
    "analysisId",
    "componentId",
    "hasScannerContext",
    "id",
    "warningCount",
    "componentQualifier",
    "nodeName",
    "componentName",
    "componentKey",
    "submittedAt",
    "executedAt",
    "type",
)

UNNEEDED_CONTEXT_DATA = (
    "sonar.announcement.message",
    "sonar.auth.github.allowUsersToSignUp",
    "sonar.auth.github.apiUrl",
    "sonar.auth.github.appId",
    "sonar.auth.github.enabled",
    "sonar.auth.github.groupsSync",
    "sonar.auth.github.organizations",
    "sonar.auth.github.webUrl",
    "sonar.builtInQualityProfiles.disableNotificationOnUpdate",
    "sonar.core.id",
    "sonar.core.serverBaseURL",
    "sonar.core.startTime",
    "sonar.dbcleaner.branchesToKeepWhenInactive",
    "sonar.forceAuthentication",
    "sonar.host.url",
    "sonar.java.jdkHome",
    "sonar.links.ci",
    "sonar.links.homepage",
    "sonar.links.issue",
    "sonar.links.scm",
    "sonar.links.scm_dev",
    "sonar.plugins.risk.consent",
)

AI_CODE_FIX = "aiCodeFix"

_JSON_KEY_ORDER = (
    "key",
    "name",
    "tags",
    "visibility",
    "newCodePeriod",
    "settings",
    "binding",
    "branches",
    "permissions",
    "qualityGate",
    "qualityProfiles",
    "links",
    "webhooks",
    "migrationData",
)


def convert_project_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config projects old JSON report format for a single project to the new one"""
    new_json = old_json.copy()
    if "qualityProfiles" in old_json:
        new_json["qualityProfiles"] = util.dict_to_list(old_json["qualityProfiles"], "language", "name")
    if "branches" in old_json:
        new_json["branches"] = util.dict_to_list(old_json["branches"], "name")
    if "webhooks" in old_json:
        new_json["webhooks"] = util.dict_to_list(old_json["webhooks"], "name")
    if "binding" in old_json:
        # If that's an ADO binding (recognized by the inlineAnnotationsEnabled element), we need to rename the slug to projectName
        if "inlineAnnotationsEnabled" in new_json["binding"] and "slug" in new_json["binding"]:
            new_json["binding"]["projectName"] = new_json["binding"].pop("slug")
            new_json["binding"] = util.order_dict(new_json["binding"], "key", "repository", "projectName", "monorepo", "inlineAnnotationsEnabled")
    for k, v in old_json.items():
        if k not in _JSON_KEY_ORDER:
            new_json.pop(k, None)
            new_json["settings"] = new_json.get("settings", None) or {}
            new_json["settings"][k] = v

    if "settings" in new_json:
        if AI_CODE_FIX in new_json["settings"] and not new_json["settings"][AI_CODE_FIX]:
            new_json["settings"].pop(AI_CODE_FIX)
        new_json["settings"] = util.dict_to_list(dict(sorted(new_json["settings"].items())), "key", "value")
    new_json = common_json_helper.convert_common_fields(new_json)
    return util.order_dict(new_json, *_JSON_KEY_ORDER)


def convert_projects_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config projects old JSON report format to the new one"""
    new_json = old_json.copy()
    for k, v in new_json.items():
        new_json[k] = convert_project_json(v)
    return util.dict_to_list(new_json, "key")
