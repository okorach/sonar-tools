#
# sonar-tools
# Copyright (C) 2026 Olivier Korach
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

"""Changelog adapter for SCA dependency risk changelog format"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

import re

import sonar.logging as log
import sonar.util.misc as util

if TYPE_CHECKING:
    from datetime import datetime
    from sonar.util.types import ApiPayload

# SCA timestamps include milliseconds (e.g. "2026-03-27T08:42:12.993Z")
# which util.to_datetime() does not handle - strip them before parsing
_MILLIS_RE = re.compile(r"\.\d+Z$")

# SCA changelog fieldName -> changelog type mapping
_FIELD_TO_TYPE = {
    "status": "STATUS",
    "severity": "SEVERITY",
    "assignee": "ASSIGN",
}


class DependencyRiskChangelog:
    """Adapter for SCA changelog entries to match the interface expected by syncer.

    SCA changelogs use ``changeData`` (list of ``{fieldName, oldValue, newValue}``)
    instead of the issue/hotspot ``diffs`` (list of ``{key, oldValue, newValue}``),
    and ``createdAt`` instead of ``creationDate``.
    """

    def __init__(self, jsonlog: ApiPayload) -> None:
        """Constructor"""
        self.sq_json = jsonlog

    def __str__(self) -> str:
        """String representation"""
        return str(self.sq_json)

    def date_str(self) -> str:
        """Returns the changelog entry date as string"""
        return self.sq_json["createdAt"]

    def date_time(self) -> datetime:
        """Returns the changelog entry date as datetime"""
        date_str = _MILLIS_RE.sub("+0000", self.sq_json["createdAt"])
        return util.to_datetime(date_str)

    def author(self) -> Optional[str]:
        """Returns the changelog entry author login"""
        user = self.sq_json.get("user", None)
        if user is None:
            return None
        if isinstance(user, dict):
            return user.get("login") or user.get("name")
        return user

    def is_comment(self) -> bool:
        """Returns whether this entry is a comment (no changeData, has markdownComment)"""
        return "markdownComment" in self.sq_json and not self.sq_json.get("changeData")

    def comment_text(self) -> Optional[str]:
        """Returns the comment text if this is a comment entry"""
        if self.is_comment():
            return self.sq_json["markdownComment"]
        return None

    def changelog_type(self) -> tuple[Optional[str], Optional[str]]:
        """Returns the changelog type and associated data.

        Maps SCA ``fieldName`` values to types understood by the syncer.
        """
        change_data = self.sq_json.get("changeData", [])
        if not change_data:
            if self.is_comment():
                return ("COMMENT", self.comment_text())
            return (None, None)

        for change in change_data:
            field = change.get("fieldName", "")
            new_value = change.get("newValue")
            ctype = _FIELD_TO_TYPE.get(field)
            if ctype:
                return (ctype, new_value)

        log.warning("Could not determine changelog type for SCA changelog %s", str(self))
        return (None, None)

    def is_manual_change(self) -> bool:
        """SCA changelogs from the API are always manual changes."""
        return True

    def is_technical_change(self) -> bool:
        """Returns whether the changelog item is a technical (non-manual) change.

        Status changes from or to FIXED are automatic (triggered by analysis), not manual user actions.
        """
        for change in self.sq_json.get("changeData", []):
            if change.get("fieldName") == "status" and ("FIXED" in (change.get("oldValue"), change.get("newValue"))):
                return True
        return False
