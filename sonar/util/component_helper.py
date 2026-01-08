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
        log.info("Searching for %s matching '%s'", component_type, key_regexp)
        components = [comp for comp in components if re.match(rf"^{key_regexp}$", comp.key)]
    if component_type in ("projects", "apps", "applications") and branch_regexp:
        log.info("Searching for %s branches matching '%s'", component_type, branch_regexp)
        components = [br for comp in components for br in comp.branches().values() if re.match(rf"^{branch_regexp}$", br.name)]
    # If pull_requests flag is set, include PRs for each project
    elif component_type == "projects" and pr_regexp:
        log.info("Searching for %s PRs matching '%s'", component_type, pr_regexp)
        components = [pr for proj in components for pr in proj.pull_requests().values() if re.match(rf"^{pr_regexp}$", pr.key)]
    return components
