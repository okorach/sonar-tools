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
from typing import Optional, Any

import sonar.logging as log
from sonar import platform, projects, applications, portfolios
from sonar.components import Component


def get_components(
    endpoint: platform.Platform,
    component_type: str,
    key_regexp: Optional[str] = None,
    branch_regexp: Optional[str] = None,
    pr_regexp: Optional[str] = None,
    **kwargs: Any,
) -> list[Component]:
    """Returns list of components that match the filters"""
    key_regexp = key_regexp or ".+"
    components: list[Component]
    if component_type in ("apps", "applications"):
        components = list(applications.Application.get_list(endpoint).values())
    elif component_type == "portfolios":
        components = list(portfolios.Portfolio.get_list(endpoint).values())
        if kwargs.get("topLevelOnly", False):
            components = [p for p in components if p.is_toplevel()]
    else:
        components = list(projects.Project.get_list(endpoint).values())
    if key_regexp:
        components = [comp for comp in components if re.match(rf"^{key_regexp}$", comp.key)]
    # If pull_requests flag is set, include PRs for each project
    log.info("PR regexp: %s", pr_regexp)
    if component_type == "projects" and pr_regexp:
        log.info("Projects list: %s", [str(proj) for proj in components])
        for proj in components:
            log.info("Project: %s", str(proj))
            components += [pr for pr in proj.pull_requests().values() if re.match(rf"^{pr_regexp}$", pr.key)]
            log.info("Components list: %s", [str(comp) for comp in components])
    if component_type != "portfolios" and branch_regexp:
        components = [b for comp in components for b in comp.branches().values() if re.match(rf"^{branch_regexp}$", b.name)]
    return components
