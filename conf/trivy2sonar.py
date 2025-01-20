#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2024-2025 Olivier Korach
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

    Converts Trivy JSON format to Sonar external issues format

"""
import sys
import json

TOOLNAME = "trivy"

MAPPING = {"INFO": "INFO", "LOW": "MINOR", "MEDIUM": "MAJOR", "HIGH": "CRITICAL", "BLOCKER": "BLOCKER"}


def main() -> None:
    """Main script entry point"""
    text = "".join(sys.stdin)

    rules_dict = {}
    issue_list = {}

    for issue in json.loads(text)["Results"][0]["Vulnerabilities"]:

        sonar_issue = {
            "ruleId": f"{TOOLNAME}:{issue['VulnerabilityID']}",
            "effortMinutes": 30,
            "primaryLocation": {
                "message": f"{issue['VulnerabilityID']} - {issue['Title']}",
                "filePath": "conf/snapshot.Dockerfile",
                "textRange": {
                    "startLine": 1,
                    # "endLine": 1,
                    # "startColumn": 1,
                    # "endColumn": 1,
                },
            },
        }
        issue_list[sonar_issue["primaryLocation"]["message"]] = sonar_issue
        # score = max([v["V3Score"] for v in issue['CVSS'].values()])
        # if score <= 4:
        #     sev = "LOW"
        # elif score <= 7:
        #     sev = "MEDIUM"
        # else:
        #     sev = "HIGH"
        sev_mqr = issue.get("Severity", "MEDIUM")
        rules_dict[f"{TOOLNAME}:{issue['VulnerabilityID']}"] = {
            "id": f"{TOOLNAME}:{issue['VulnerabilityID']}",
            "name": f"{TOOLNAME}:{issue['VulnerabilityID']} - {issue['Title']}",
            "description": issue.get("Description", ""),
            "engineId": TOOLNAME,
            "type": "VULNERABILITY",
            "severity": MAPPING[sev_mqr],
            "cleanCodeAttribute": "LOGICAL",
            "impacts": [{"softwareQuality": "SECURITY", "severity": sev_mqr}],
        }

    external_issues = {"rules": list(rules_dict.values()), "issues": list(issue_list.values())}
    print(json.dumps(external_issues, indent=3, separators=(",", ": ")))


if __name__ == "__main__":
    main()
