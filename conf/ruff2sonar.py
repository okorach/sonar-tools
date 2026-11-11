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
"""Converts Ruff JSON report format (ruff check --output-format json) to Sonar external issues format"""

import json
import os
import sys

TOOLNAME = "ruff"


def _text_range(issue: dict) -> dict:
    """Converts ruff 1-based location / end_location into a Sonar 0-based column text range"""
    start, end = issue["location"], issue.get("end_location") or issue["location"]
    if end["row"] > start["row"] and end["column"] == 1:
        # Range ends at the start of the next line (e.g. I001 import blocks): flag the whole lines
        return {"startLine": start["row"], "endLine": end["row"] - 1}
    if end["row"] == start["row"] and end["column"] <= start["column"]:
        # Empty range, flag the whole line
        return {"startLine": start["row"], "endLine": start["row"]}
    return {"startLine": start["row"], "endLine": end["row"], "startColumn": start["column"] - 1, "endColumn": end["column"] - 1}


def main() -> None:
    """Main script entry point"""
    v1 = len(sys.argv) > 1 and sys.argv[1] == "v1"
    text = sys.stdin.read().strip()
    rules_dict = {}
    issue_list = []
    for issue in json.loads(text) if text else []:
        rule_id = issue.get("code") or "syntax-error"
        sonar_issue = {
            "engineId": TOOLNAME,
            "ruleId": rule_id,
            "effortMinutes": 5,
            "primaryLocation": {"message": issue["message"], "filePath": os.path.relpath(issue["filename"]), "textRange": _text_range(issue)},
        }
        if v1:
            sonar_issue["severity"] = "MAJOR"
            sonar_issue["type"] = "CODE_SMELL"
        issue_list.append(sonar_issue)
        rules_dict[rule_id] = {
            "id": rule_id,
            "name": f"{rule_id} - {issue.get('name') or rule_id}",
            "description": issue["message"],
            "engineId": TOOLNAME,
            "type": "CODE_SMELL",
            "severity": "MAJOR",
            "cleanCodeAttribute": "LOGICAL",
            "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
        }

    if len(issue_list) == 0:
        return
    external_issues = {"rules": list(rules_dict.values()), "issues": issue_list}
    if v1:
        external_issues.pop("rules")
    print(json.dumps(external_issues, indent=3, separators=(",", ": ")))  # noqa: T201


if __name__ == "__main__":
    main()
