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

"""sonar-tools error codes"""

OK = 0

# HTTP 401
SONAR_API_AUTHENTICATION = 1

# HTTP 403
SONAR_API_AUTHORIZATION = 2

# General Sonar Web API error
SONAR_API = 3

# Auth token not provided
TOKEN_MISSING = 4

# Project, Branch, Application, Portfolio, Metric key provided on cmd line does not exist
NO_SUCH_KEY = 5

# Issue search criteria incorrect
WRONG_SEARCH_CRITERIA = 6

# Requested operation unsupported on this platform (version or edition incompatible)
UNSUPPORTED_OPERATION = 7

RULES_LOADING_FAILED = 8

SIF_AUDIT_ERROR = 9

# Incorrect sonar-tool CLI argument
ARGS_ERROR = 10

# if a global analysis or project analysis token is provided
TOKEN_NOT_SUITED = 11

# HTTP request timeout
HTTP_TIMEOUT = 12

# Request to create an object that already exists
OBJECT_ALREADY_EXISTS = 13

# Connection error (because of wrong token or (on SonarCloud) wrong organization)
CONNECTION_ERROR = 14

# Miscellaneous OS errors
OS_ERROR = 15

# Request to manipulate an object that was not found
OBJECT_NOT_FOUND = 16
