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
"""Exports a MISRA report"""

import sys
from unittest.mock import patch
from cli import findings_export
from cli.options import TAGS


def main() -> None:
    """Sets CLI parameters and parses them"""
    args = sys.argv.copy()
    args[0] = "sonar-findings-export"
    possible_opts = [f"--{TAGS[:i]}" for i in range(1, len(TAGS) + 1)]
    if not any(opt in args for opt in possible_opts):
        args += [f"--{TAGS}", "misra-c++2023"]
    with patch.object(sys, "argv", args):
        findings_export.main()


if __name__ == "__main__":
    main()
