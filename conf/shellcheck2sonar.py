#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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

    Converts shellcheck JSON format to Sonar external issues format

"""
import sys
import json

SHELLCHECK = "shellcheck"
MAPPING = {"INFO": "INFO", "LOW": "MINOR", "MEDIUM": "MAJOR", "HIGH": "CRITICAL", "BLOCKER": "BLOCKER"}


def main() -> None:
    """Main script entry point"""
    text = "".join(sys.stdin)

    rules_dict = {}
    issue_list = []

    for issue in json.loads(text):
        sonar_issue = {
            "ruleId": f"{SHELLCHECK}:{issue['code']}",
            "effortMinutes": 5,
            "primaryLocation": {
                "message": issue["message"],
                "filePath": issue["file"],
                "textRange": {
                    "startLine": issue["line"],
                    "endLine": issue["endLine"],
                    "startColumn": issue["column"] - 1,
                    "endColumn": max(issue["column"], issue["endColumn"] - 1),
                },
            },
        }
        issue_list.append(sonar_issue)
        if issue["level"] in ("info", "style"):
            sev_mqr = "LOW"
        elif issue["level"] == "warning":
            sev_mqr = "MEDIUM"
        else:
            sev_mqr = "HIGH"
        rules_dict[f"{SHELLCHECK}:{issue['code']}"] = {
            "id": f"{SHELLCHECK}:{issue['code']}",
            "name": f"{SHELLCHECK}:{issue['code']}",
            "engineId": SHELLCHECK,
            "type": "CODE_SMELL",
            "cleanCodeAttribute": "LOGICAL",
            "severity": MAPPING[sev_mqr],
            "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": sev_mqr}],
        }

    external_issues = {"rules": list(rules_dict.values()), "issues": issue_list}
    print(json.dumps(external_issues, indent=3, separators=(",", ": ")))


if __name__ == "__main__":
    main()
