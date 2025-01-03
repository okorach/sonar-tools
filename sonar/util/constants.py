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

""" Sonar utility constants """

CREATE = "CREATE"
READ = "READ"
UPDATE = "UPDATE"
DELETE = "DELETE"
LIST = "LIST"
SEARCH = "LIST"
GET = "GET"
RENAME = "RENAME"

SET_TAGS = "SET_TAGS"
GET_TAGS = "GET_TAGS"

USE_CACHE = "use_cache"

VULN = "VULNERABILITY"
BUG = "BUG"
CODE_SMELL = "CODE_SMELL"
HOTSPOT = "SECURITY_HOTSPOT"

# Keys for JSON sonar-config export/import
CONFIG_KEY_PLATFORM = "platform"
CONFIG_KEY_SETTINGS = "globalSettings"
CONFIG_KEY_USERS = "users"
CONFIG_KEY_GROUPS = "groups"
CONFIG_KEY_GATES = "qualityGates"
CONFIG_KEY_RULES = "rules"
CONFIG_KEY_PROFILES = "qualityProfiles"
CONFIG_KEY_PROJECTS = "projects"
CONFIG_KEY_APPS = "applications"
CONFIG_KEY_PORTFOLIOS = "portfolios"
