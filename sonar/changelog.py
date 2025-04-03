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

"""Abstraction of SonarQube finding (issue or hotspot) changelog"""

from typing import Optional

import sonar.logging as log
from sonar.util import types


class Changelog(object):
    """Abstraction of SonarQube finding (issue or hotspot) changelog"""

    def __init__(self, jsonlog: types.ApiPayload) -> None:
        self.sq_json = jsonlog
        self._change_type = None

    def __str__(self) -> str:
        """str() implementation"""
        return str(self.sq_json)

    def __is_resolve_as(self, resolve_reason: str) -> bool:
        cond1 = False
        cond2 = False
        for diff in self.sq_json["diffs"]:
            if diff["key"] == "resolution" and "newValue" in diff and diff["newValue"] == resolve_reason:
                cond1 = True
            if diff["key"] == "status" and "newValue" in diff and diff["newValue"] == "RESOLVED":
                cond2 = True
        return cond1 and cond2

    def is_resolve_as_fixed(self) -> bool:
        """Returns whether the changelog item is an issue resolved as fixed"""
        return self.__is_resolve_as("FIXED")

    def is_resolve_as_fp(self) -> bool:
        """Returns whether the changelog item is an issue resolved as false positive"""
        return self.__is_resolve_as("FALSE-POSITIVE")

    def is_resolve_as_wf(self) -> bool:
        """Returns whether the changelog item is an issue resolved as won't fix"""
        return self.__is_resolve_as("WONTFIX")

    def is_resolve_as_accept(self) -> bool:
        """Returns whether the changelog item is an issue resolved as accepted"""
        return self.__is_resolve_as("ACCEPTED")

    def is_closed(self) -> bool:
        """{'creationDate': '2022-02-01T19:15:24+0100', 'diffs': [
        {'key': 'resolution', 'newValue': 'FIXED'},
        {'key': 'status', 'newValue': 'CLOSED', 'oldValue': 'OPEN'}]}"""
        for diff in self.sq_json["diffs"]:
            if diff["key"] == "status" and "newValue" in diff and diff["newValue"] == "CLOSED":
                return True
        return False

    def __is_status(self, status: str) -> bool:
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "status" and d.get("newValue", "") == status:
                return True
        return False

    def is_reopen(self) -> bool:
        """Returns whether the changelog item is an issue re-open"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "status" and (
                (d.get("newValue", "") == "REOPENED" and d.get("oldValue", "") != "CONFIRMED")
                or (d.get("newValue", "") == "OPEN" and d.get("oldValue", "") == "CLOSED")
            ):
                return True
        return False

    def is_confirm(self) -> bool:
        """Returns whether the changelog item is an issue confirm"""
        return self.__is_status("CONFIRMED")

    def is_unconfirm(self) -> bool:
        """Returns whether the changelog item is an issue unconfirm"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "status" and d.get("newValue", "") == "REOPENED" and d.get("oldValue", "") == "CONFIRMED":
                return True
        return False

    def is_mark_as_safe(self) -> bool:
        """Returns whether the changelog item is a hotspot marked as safe"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "resolution" and d.get("newValue", "") == "SAFE":
                return True
        return False

    def is_mark_as_to_review(self) -> bool:
        """Returns whether the changelog item is a hotspot to review"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "status" and d.get("newValue", "") == "TO_REVIEW":
                return True
        return False

    def is_mark_as_fixed(self) -> bool:
        """Returns whether the changelog item is an issue marked as fixed"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "resolution" and d.get("newValue", "") == "FIXED":
                return True
        return False

    def is_mark_as_acknowledged(self) -> bool:
        """Returns whether the changelog item is a hotspot acknowledge"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "resolution" and d.get("newValue", "") == "ACKNOWLEDGED":
                return True
        return False

    def is_change_severity(self) -> bool:
        """Returns whether the changelog item is a change of issue severity"""
        d = self.sq_json["diffs"][0]
        return d.get("key", "") == "severity"

    def new_severity(self) -> Optional[str]:
        """Returns the new severity of a change issue severity changelog"""
        if self.is_change_severity():
            d = self.sq_json["diffs"][0]
            return d.get("newValue", None)
        return None

    def is_change_type(self) -> bool:
        """Returns whether the changelog item is a change of issue type"""
        d = self.sq_json["diffs"][0]
        return d.get("key", "") == "type"

    def new_type(self) -> Optional[str]:
        """Returns the new type of a change issue type changelog"""
        if self.is_change_type():
            d = self.sq_json["diffs"][0]
            return d.get("newValue", None)
        return None

    def is_technical_change(self) -> bool:
        """Returns whether the changelog item is a technical change"""
        d = self.sq_json["diffs"][0]
        key = d.get("key", "")
        return key in ("from_short_branch", "from_branch", "effort")

    def is_assignment(self) -> bool:
        """Returns whether the changelog item is an assignment"""
        d = self.sq_json["diffs"][0]
        return d.get("key", "") == "assignee"

    def new_assignee(self) -> Optional[str]:
        """Returns the new assignee of a change assignment changelog"""
        if not self.is_assignment():
            return None
        d = self.sq_json["diffs"][0]
        return d.get("newValue", None)

    def old_assignee(self) -> Optional[str]:
        """Returns the old assignee of a change assignment changelog"""
        if not self.is_assignment():
            return None
        d = self.sq_json["diffs"][0]
        return d.get("oldValue", None)

    def previous_state(self) -> str:
        """Returns the previous state of a state change changelog"""
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == "status":
                return d.get("oldValue", "")
        return ""

    def date(self) -> str:
        """Returns the changelog item date"""
        return self.sq_json["creationDate"]

    def author(self) -> Optional[str]:
        """Returns the changelog item author"""
        return self.sq_json.get("user", None)

    def is_tag(self) -> bool:
        """Returns whether the changelog item is an issue tagging"""
        d = self.sq_json["diffs"][0]
        return d.get("key", "") == "tag"

    def get_tags(self) -> Optional[str]:
        """Returns the changelog tags for issue tagging items"""
        if not self.is_tag():
            return None
        d = self.sq_json["diffs"][0]
        return d.get("newValue", "").replace(" ", ",")

    def changelog_type(self) -> tuple[str, Optional[str]]:
        ctype = (None, None)
        if self.is_assignment():
            ctype = ("ASSIGN", self.new_assignee())
        elif self.is_reopen():
            ctype = ("REOPEN", None)
        elif self.is_confirm():
            ctype = ("CONFIRM", None)
        elif self.is_unconfirm():
            ctype = ("UNCONFIRM", None)
        elif self.is_change_severity():
            ctype = ("SEVERITY", self.new_severity())
        elif self.is_change_type():
            ctype = ("TYPE", self.new_type())
        elif self.is_resolve_as_fixed():
            ctype = ("FIXED", None)
        elif self.is_resolve_as_fp():
            ctype = ("FALSE-POSITIVE", None)
        elif self.is_resolve_as_wf():
            ctype = ("WONT-FIX", None)
        elif self.is_resolve_as_accept():
            ctype = ("ACCEPT", None)
        elif self.is_tag():
            ctype = ("TAG", self.get_tags())
        elif self.is_closed():
            ctype = ("CLOSED", None)
        elif self.is_mark_as_safe():
            ctype = ("HOTSPOT_SAFE", None)
        elif self.is_mark_as_fixed():
            ctype = ("HOTSPOT_FIXED", None)
        elif self.is_mark_as_to_review():
            ctype = ("HOTSPOT_TO_REVIEW", None)
        elif self.is_mark_as_acknowledged():
            ctype = ("HOTSPOT_ACKNOWLEDGED", None)
        elif self.is_technical_change():
            ctype = ("INTERNAL", None)
        else:
            log.warning("Could not determine changelog type for %s", str(self))
        return ctype
