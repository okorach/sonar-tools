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

    def __is_issue_status_diff(self) -> bool:
        """Returns whether the changelog item contains an object with the key 'issueStatus'"""
        return any(d.get("key", "") == "issueStatus" for d in self.sq_json["diffs"])

    def __is_resolve_as(self, resolve_reason: str) -> bool:
        """Returns whether the changelog item is an issue resolved as a specific reason"""
        # The 'issueStatus' field has been available since SonarQube Server 10.4 and is the preferred
        # method for retrieving information about issue changes.
        # Starting with SonarQube Server 10.4, the "resolution" and "status" keys are deprecated in
        # issue changelogs but remain relevant for security hotspot changelogs.
        # These conditions are retained for backward compatibility to support versions from SQS 9.9 to 10.3,
        # where "resolution" and "status" are the only way to detect status changes. They are also still
        # applicable for security hotspot changelogs.
        if self.__is_issue_status_diff():
            return any(diff["key"] == "issueStatus" and diff.get("newValue", "") == resolve_reason for diff in self.sq_json["diffs"])
        else:
            cond1 = any(diff["key"] == "resolution" and diff.get("newValue", "") == resolve_reason for diff in self.sq_json["diffs"])
            cond2 = any(diff["key"] == "status" and diff.get("newValue", "") == "RESOLVED" for diff in self.sq_json["diffs"])
            return cond1 and cond2

    def is_resolve_as_fixed(self) -> bool:
        """Returns whether the changelog item is an issue resolved as fixed"""
        return self.__is_resolve_as("FIXED")

    def is_resolve_as_fp(self) -> bool:
        """Returns whether the changelog item is an issue resolved as false positive"""
        # Finding "is resolve as false positive" requires "FALSE-POSITIVE" on SonarQube
        # Server 9.9 and "FALSE_POSITIVE" on SonarQube Server 2025.1 and SonarQube Cloud.
        return self.__is_resolve_as("FALSE-POSITIVE") or self.__is_resolve_as("FALSE_POSITIVE")

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
        status_key = "issueStatus" if self.__is_issue_status_diff() else "status"
        return any(diff["key"] == status_key and diff.get("newValue", "") == "CLOSED" for diff in self.sq_json["diffs"])

    def __is_status(self, status: str) -> bool:
        status_key = "issueStatus" if self.__is_issue_status_diff() else "status"
        return any(diff["key"] == status_key and diff.get("newValue", "") == status for diff in self.sq_json["diffs"])

    def is_reopen(self) -> bool:
        """Returns whether the changelog item is an issue re-open"""
        if self.__is_issue_status_diff():
            return any(
                d.get("key", "") == "issueStatus" and d.get("newValue", "") == "OPEN" and d.get("oldValue", "") != "CONFIRMED"
                for d in self.sq_json["diffs"]
            )
        else:
            return any(
                d.get("key", "") == "status"
                and (
                    (d.get("newValue", "") == "REOPENED" and d.get("oldValue", "") != "CONFIRMED")
                    or (d.get("newValue", "") == "OPEN" and d.get("oldValue", "") == "CLOSED")
                )
                for d in self.sq_json["diffs"]
            )

    def is_confirm(self) -> bool:
        """Returns whether the changelog item is an issue confirm"""
        return self.__is_status("CONFIRMED")

    def is_unconfirm(self) -> bool:
        """Returns whether the changelog item is an issue unconfirm"""
        if self.__is_issue_status_diff():
            return any(
                d.get("key", "") == "issueStatus" and d.get("newValue", "") == "OPEN" and d.get("oldValue", "") == "CONFIRMED"
                for d in self.sq_json["diffs"]
            )
        else:
            return any(
                d.get("key", "") == "status" and d.get("newValue", "") == "REOPENED" and d.get("oldValue", "") == "CONFIRMED"
                for d in self.sq_json["diffs"]
            )

    def is_mark_as_safe(self) -> bool:
        """Returns whether the changelog item is a hotspot marked as safe"""
        return any(d.get("key", "") == "resolution" and d.get("newValue", "") == "SAFE" for d in self.sq_json["diffs"])

    def is_mark_as_to_review(self) -> bool:
        """Returns whether the changelog item is a hotspot to review"""
        return any(d.get("key", "") == "status" and d.get("newValue", "") == "TO_REVIEW" for d in self.sq_json["diffs"])

    def is_mark_as_fixed(self) -> bool:
        """Returns whether the changelog item is an issue marked as fixed"""
        return any(d.get("key", "") == "resolution" and d.get("newValue", "") == "FIXED" for d in self.sq_json["diffs"])

    def is_mark_as_acknowledged(self) -> bool:
        """Returns whether the changelog item is a hotspot acknowledge"""
        return any(d.get("key", "") == "resolution" and d.get("newValue", "") == "ACKNOWLEDGED" for d in self.sq_json["diffs"])

    def is_change_severity(self) -> bool:
        """Returns whether the changelog item is a change of issue severity"""
        return any(d.get("key", "") in ("severity", "impactSeverity") for d in self.sq_json["diffs"])

    def new_severity(self) -> Optional[str]:
        """Returns the new severity of a change issue severity changelog"""
        if self.is_change_severity():
            try:
                d = next(d for d in self.sq_json["diffs"] if d.get("key", "") == "type")
                return d.get("newValue", None)
            except StopIteration:
                log.warning("No severity change found in changelog %s", str(self))
        return None

    def is_change_type(self) -> bool:
        """Returns whether the changelog item is a change of issue type"""
        return any(d.get("key", "") == "type" and "newValue" in d for d in self.sq_json["diffs"])

    def new_type(self) -> Optional[str]:
        """Returns the new type of a change issue type changelog"""
        if self.is_change_type():
            try:
                d = next(d for d in self.sq_json["diffs"] if d.get("key", "") == "type")
                return d.get("newValue", None)
            except StopIteration:
                log.warning("No type change found in changelog %s", str(self))
        return None

    def is_technical_change(self) -> bool:
        """Returns whether the changelog item is a technical change"""
        d = self.sq_json["diffs"][0]
        key = d.get("key", "")
        return key in ("from_short_branch", "from_branch", "effort")

    def is_manual_change(self) -> bool:
        """Returns whether the changelog item is a manual change"""
        status_key, closed_state = "issueStatus", "FIXED"
        if not self.__is_issue_status_diff():
            status_key, closed_state = "status", "CLOSED"
        return not any(
            d.get("key", "") == status_key and closed_state in (d.get("oldValue", ""), d.get("newValue", "")) for d in self.sq_json["diffs"]
        )

    def is_assignment(self) -> bool:
        """Returns whether the changelog item is an assignment"""
        return any(d.get("key", "") == "assignee" and "newValue" in d for d in self.sq_json["diffs"])

    def is_unassign(self) -> bool:
        """Returns whether the changelog item is an unassign"""
        return any(d.get("key", "") == "assignee" and "newValue" not in d for d in self.sq_json["diffs"])

    def assignee(self, new: bool = True) -> Optional[str]:
        """Returns the new assignee of a change assignment changelog"""
        if self.is_assignment():
            try:
                d = next(d for d in self.sq_json["diffs"] if d.get("key", "") == "assignee")
                return d.get("newValue" if new else "oldValue", None)
            except StopIteration:
                log.warning("No assignment found in changelog %s", str(self))
        return None

    def previous_state(self) -> str:
        """Returns the previous state of a state change changelog"""
        status_key = "issueStatus" if self.__is_issue_status_diff() else "status"
        for d in self.sq_json["diffs"]:
            if d.get("key", "") == status_key:
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
        return any(d.get("key", "") == "tags" for d in self.sq_json["diffs"])

    def get_tags(self) -> Optional[str]:
        """Returns the changelog tags for issue tagging items"""
        try:
            d = next(d for d in self.sq_json["diffs"] if d.get("key", "") == "tags")
            return d.get("newValue", "").split()
        except StopIteration:
            return None

    def changelog_type(self) -> tuple[str, Optional[str]]:
        ctype = (None, None)
        if self.is_assignment():
            ctype = ("ASSIGN", self.assignee())
        elif self.is_unassign():
            ctype = ("UNASSIGN", None)
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
