#!/usr/local/bin/python3
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
"""

    Imports a list of projects to a SonarQube platform

"""
import sys
from unittest.mock import patch

from cli import options, projects_cli
import sonar.logging as log


def main() -> None:
    """Deprecated entry point for sonar-projects-import"""
    log.warning("\n*** sonar-projects-import is deprecated, please use 'sonar-projects -i' instead ***\n")
    args = sys.argv.copy()
    args[0] = "sonar-projects"
    args.append(f"-{options.IMPORT_SHORT}")
    with patch.object(sys, "argv", args):
        projects_cli.main()


if __name__ == "__main__":
    main()
