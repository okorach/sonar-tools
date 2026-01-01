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

"""Sonar utility constants"""

CREATE = "CREATE"
READ = "READ"
UPDATE = "UPDATE"
DELETE = "DELETE"
LIST = "LIST"
SEARCH = "LIST"
GET = "GET"
RENAME = "RENAME"
RECOMPUTE = "RECOMPUTE"

LIST_MEMBERS = "LIST_MEMBERS"
LIST_GROUPS = "LIST_GROUPS"
ADD_MEMBER = "ADD_MEMBER"
REMOVE_MEMBER = "REMOVE_MEMBER"

ASSIGN = "ASSIGN"

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

CE = "community"
DE = "developer"
EE = "enterprise"
DCE = "datacenter"
EDITIONS_SUPPORTING_PORTFOLIOS = (EE, DCE)

SC = "sonarcloud"
SQS = "SonarQube Server"
SQC = "SonarQube Cloud"

MQR_INTRO_VERSION = (10, 2, 0)
ACCEPT_INTRO_VERSION = (10, 2, 0)
NEW_ISSUE_SEARCH_INTRO_VERSION = (10, 2, 0)
GROUP_API_V2_INTRO_VERSION = (10, 4, 0)
USER_API_V2_INTRO_VERSION = (10, 4, 0)

AUDIT_MODE_PARAM = "audit.mode"

DEFAULT = "-DEFAULT-"
DEFAULT_BRANCH = "-DEFAULT_BRANCH-"

SQS_USERS = "sonar-users"  # SonarQube Server users default group name
SQC_USERS = "Members"  # SonarQube Cloud users default group name

SQS_TOKEN_LENGTH = 44
SQC_TOKEN_LENGTH = 40
