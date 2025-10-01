#!/usr/bin/env python3
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
"""

    Converts Ruff report format to Sonar external issues format

"""
import sys
import json
import re

TOOLNAME = "ruff"

TRIVY_TO_MQR_MAPPING = {"CRITICAL": "BLOCKER"}
MAPPING = {"LOW": "MINOR", "MEDIUM": "MAJOR", "HIGH": "CRITICAL", "BLOCKER": "BLOCKER"}


def main() -> None:
    """Main script entry point"""
    rules_dict = {}
    issue_list = {}
    lines = sys.stdin.read().splitlines()
    i = 0
    nblines = len(lines)
    while i < nblines:
        line = lines[i]
        i += 1
        # Search for pattern like "F401 [*] `sys` imported but unused"
        if not (m := re.match(r"^([A-Za-z0-9]+) (\[\*\]) (.+)$", line)):
            continue
        rule_id = m.group(1)
        message = m.group(3)
        line = lines[i]
        i += 1
        # Search for pattern like "   --> cli/cust_measures.py:28:8"
        if not (m := re.match(r"^\s*--> ([^:]+):(\d+):(\d+)$", line)):
            continue
        file_path = m.group(1)
        line_no = int(m.group(2))

        # Search for "   |        ^^^" pattern"
        while i < nblines and not (m := re.match(r"^\s*\|\s(\s*)(\^+)", lines[i])):
            i += 1
        if not m:
            continue
        start_col = len(m.group(1))
        end_col = start_col + len(m.group(2))

        sonar_issue = {
            "ruleId": f"{TOOLNAME}:{rule_id}",
            "effortMinutes": 5,
            "primaryLocation": {
                "message": message,
                "filePath": file_path,
                "textRange": {
                    "startLine": line_no,
                    "endLine": line_no,
                    "startColumn": start_col,
                    "endColumn": end_col,
                },
            },
        }

        issue_list[f"{rule_id} - {message}"] = sonar_issue
        rules_dict[f"{TOOLNAME}:{rule_id}"] = {
            "id": f"{TOOLNAME}:{rule_id}",
            "name": f"{TOOLNAME}:{rule_id}",
            "description": message,
            "engineId": TOOLNAME,
            "type": "CODE_SMELL",
            "severity": "MAJOR",
            "cleanCodeAttribute": "LOGICAL",
            "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
        }

    external_issues = {"rules": list(rules_dict.values()), "issues": list(issue_list.values())}
    print(json.dumps(external_issues, indent=3, separators=(",", ": ")))


if __name__ == "__main__":
    main()
