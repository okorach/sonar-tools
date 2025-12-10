#!/usr/bin/env python3
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
This script manipulates custom measures. You may:

Update a custom measure value:
    Usage: cust_measures.py -t <SQ_TOKEN> -u <SQ_URL> -k <projectKey> -m <metricKey> --updateValue <value>
"""

from cli import options
from sonar import errcodes, utilities
import sonar.util.common_helper as chelp

TOOL_NAME = "sonar-custom-measures"


def main():
    start_time = utilities.start_clock()
    chelp.clear_cache_and_exit(errcodes.UNSUPPORTED_OPERATION, "Custom measures are not supported anymore", start_time=start_time)


if __name__ == "__main__":
    main()
