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

import re
from typing import Optional

from sonar import platform, components, projects, applications, portfolios, logging


def get_components(
    endpoint: platform.Platform, component_type: str, key_regexp: Optional[str] = None, branch_regexp: Optional[str] = None
) -> list[components.Component]:
    """Returns list of components that match the filters"""
    key_regexp = key_regexp or ".*"
    if component_type in ("apps", "applications"):
        components = [p for p in applications.get_list(endpoint).values() if re.match(rf"^{key_regexp}$", p.key)]
    elif component_type == "portfolios":
        components = [p for p in portfolios.get_list(endpoint).values() if re.match(rf"^{key_regexp}$", p.key)]
    else:
        components = [p for p in projects.get_list(endpoint).values() if re.match(rf"^{key_regexp}$", p.key)]
    if component_type != "portfolios" and branch_regexp:
        components = [b for c in components for b in c.branches().values() if re.match(rf"^{branch_regexp}$", b.name)]
    return components
