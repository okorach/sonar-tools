#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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

"""Main entry point for sonar-tools"""

from sonar import version, errcodes
import sonar.util.common_helper as chelp


def main() -> None:
    """Main entry point for sonar-tools"""
    print(
        f"""
sonar-tools version {version.PACKAGE_VERSION}
(c) Olivier Korach 2019-2026
Collections of utilities for SonarQube Server and Cloud:
- sonar-audit: Audits a SonarQube Server or Cloud platform for bad practices, performance, configuration problems
- sonar-housekeeper: Deletes projects that have not been analyzed since a given number of days
- sonar-loc: Produces a list of projects with their LoC count as computed by SonarQube Server or Cloud
  commercial licenses (ie taking the largest branch or PR)
- sonar-measures-export: Exports measures/metrics of one, several or all projects of the platform in CSV or JSON
  (Can also export measures history)
- sonar-findings-export: Exports findings (potentially filtered) from the platform in CSV or JSON
  (also available as sonar-issues-export for backward compatibility, but deprecated)
- sonar-findings-sync: Synchronizes issues between 2 branches of a same project, a whole project
  branches of 2 different projects (potentially on different platforms).
  (also available as sonar-issues-sync for backward compatibility, but deprecated)
- sonar-projects: Exports or imports projects to/from zip file (Import works for SonarQube Server EE and higher)
- sonar-config: Exports or imports an entire (or subsets of a) SonarQube Server or Cloud platform configuration as code (JSON)
- sonar-rules: Exports Sonar rules
See tools built-in -h help and https://github.com/okorach/sonar-tools for more documentation
"""
    )
    chelp.clear_cache_and_exit(errcodes.OK)


if __name__ == "__main__":
    main()
