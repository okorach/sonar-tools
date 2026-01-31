#!/usr/bin/env python3
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
"""Converts Ruff report format to Sonar external issues format"""

import sys
import json
import re

TOOLNAME = "ruff"

TRIVY_TO_MQR_MAPPING = {"CRITICAL": "BLOCKER"}
MAPPING = {"LOW": "MINOR", "MEDIUM": "MAJOR", "HIGH": "CRITICAL", "BLOCKER": "BLOCKER"}


def main() -> None:
    """Main script entry point"""
    v1 = len(sys.argv) > 1 and sys.argv[1] == "v1"
    rules_dict = {}
    issue_list = []
    lines = sys.stdin.read().splitlines()
    i = 0
    sonar_issue = None
    issue_range = {}
    nblines = len(lines)
    end_line = None
    while i < nblines:
        line = lines[i]
        # Search for pattern like "sonar/projects.py:196:13: B904 Within an `except` clause, raise exceptions"
        if m := re.match(r"^([^:]+):(\d+):(\d+): ([A-Z0-9]+)( \[\*\])? (.+)$", line):
            if sonar_issue is not None:
                issue_list.append(sonar_issue)
                end_line = None
            file_path = m.group(1)
            issue_range = {
                "startLine": int(m.group(2)),
                "endLine": int(m.group(2)),
                "startColumn": int(m.group(3)) - 1,
                "endColumn": int(m.group(3)),
            }
            rule_id = m.group(4)
            message = m.group(6)
            sonar_issue = {
                "ruleId": rule_id,
                "effortMinutes": 5,
                "primaryLocation": {
                    "message": m.group(6),
                    "filePath": file_path,
                    "textRange": issue_range,
                },
            }
            if v1:
                sonar_issue["engineId"] = TOOLNAME
                sonar_issue["severity"] = "MAJOR"
                sonar_issue["type"] = "CODE_SMELL"
            rules_dict[rule_id] = {
                "id": rule_id,
                "name": rule_id,
                "description": message,
                "engineId": TOOLNAME,
                "type": "CODE_SMELL",
                "severity": "MAJOR",
                "cleanCodeAttribute": "LOGICAL",
                "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
            }
        elif m := re.match(r"\s+\|\s\|(_+)\^ [A-Z0-9]+", lines[i]):
            issue_range["endLine"] = end_line or issue_range["startLine"]
            end_line = None
            if rule_id != "I001":
                issue_range["endColumn"] = len(m.group(1))
            else:
                issue_range["endLine"] -= 1
                issue_range.pop("startColumn")
                issue_range.pop("endColumn")
            end_line = None
        elif m := re.match(r"\s*(\d+)\s\|\s\|.*$", lines[i]):
            end_line = int(m.group(1))
        i += 1

    if len(issue_list) == 0:
        return
    external_issues = {"rules": list(rules_dict.values()), "issues": issue_list}
    if v1:
        external_issues.pop("rules")
    print(json.dumps(external_issues, indent=3, separators=(",", ": ")))


if __name__ == "__main__":
    main()
