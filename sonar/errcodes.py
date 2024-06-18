#
# sonar-tools
# Copyright (C) 2024 Olivier Korach
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

ERR_OK = 0

# HTTP 401
ERR_SONAR_API_AUTHENTICATION = 1

# HTTP 403
ERR_SONAR_API_AUTHORIZATION = 2

# General Sonar Web API error
ERR_SONAR_API = 3

# Auth token not provided
ERR_TOKEN_MISSING = 4

# Project, Branch, Application, Portfolio, Metric key provided on cmd line does not exist
ERR_NO_SUCH_KEY = 5

# Issue search criteria incorrect
ERR_WRONG_SEARCH_CRITERIA = 6

# Requested operation unsupported on this platform (version or edition incompatible)
ERR_UNSUPPORTED_OPERATION = 7

ERR_RULES_LOADING_FAILED = 8

ERR_SIF_AUDIT_ERROR = 9

# Incorrect sonar-tool CLI argument
ERR_ARGS_ERROR = 10

# if a global analysis or project analysis token is provided
ERR_TOKEN_NOT_SUITED = 11

# HTTP request timeout
ERR_REQUEST_TIMEOUT = 12
