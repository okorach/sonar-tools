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

"""Project utility functions"""

import math
from sonar import logging as log


def split_loc_filter(loc_filter: str) -> tuple[str, str]:
    """Parses a ncloc filter and returns new filters to split the search"""
    __FILTER_AND = " and "
    loc_min, loc_max = 0, 100000000
    new_filters = []
    for f in loc_filter.split(__FILTER_AND):
        if f.startswith("ncloc>="):
            try:
                loc_min = int(f[len("ncloc>=") :])
            except ValueError:
                pass
        elif f.startswith("ncloc>"):
            try:
                loc_min = int(f[len("ncloc>") :]) + 1
            except ValueError:
                pass
        elif f.startswith("ncloc<="):
            try:
                loc_max = int(f[len("ncloc<=") :])
            except ValueError:
                pass
        elif f.startswith("ncloc<"):
            try:
                loc_max = int(f[len("ncloc<") :]) - 1
            except ValueError:
                pass
        else:
            new_filters.append(f)
    loc_middle = int(2 ** ((math.log2(loc_max) + math.log2(max(loc_min, 1))) / 2))
    log.debug("LoC split: min=%d, middle=%d, max=%d", loc_min, loc_middle, loc_max)
    slice1 = __FILTER_AND.join(new_filters + [f"ncloc>={loc_min}", f"ncloc<={loc_middle}"])
    slice2 = __FILTER_AND.join(new_filters + [f"ncloc>{loc_middle}", f"ncloc<={loc_max}"])
    return slice1, slice2
