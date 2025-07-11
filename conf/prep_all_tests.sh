#!/bin/bash
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

# Deletes and recreates a fresh TESTSYNC project in SonarQube
curl -X POST -u $SONAR_TOKEN: "http://localhost:20010/api/projects/delete?project=TESTSYNC"
conf/scan.sh -Dsonar.host.url=http://localhost:20010 -Dsonar.projectKey=TESTSYNC -Dsonar.projectName=TESTSYNC

sonar-scanner -Dsonar.host.url=http://localhost:10000 -Dsonar.pullrequest.key=5 -Dsonar.pullrequest.branch=feature/5
sonar-scanner -Dsonar.host.url=http://localhost:10000 -Dsonar.pullrequest.key=7 -Dsonar.pullrequest.branch=feature/7

sonar-scanner -Dsonar.host.url=http://localhost:9000 -Dsonar.pullrequest.key=5 -Dsonar.pullrequest.branch=feature/5 -Dsonar.login="$SONAR_TOKEN_9_ADMIN_ANALYSIS"
sonar-scanner -Dsonar.host.url=http://localhost:9000 -Dsonar.pullrequest.key=7 -Dsonar.pullrequest.branch=feature/7 -Dsonar.login="$SONAR_TOKEN_9_ADMIN_ANALYSIS"

sonar-scanner -Dsonar.host.url=http://localhost:8000 -Dsonar.pullrequest.key=5 -Dsonar.pullrequest.branch=feature/5 -Dsonar.login="$SONAR_TOKEN_LTS_ADMIN_ANALYSIS"
sonar-scanner -Dsonar.host.url=http://localhost:8000 -Dsonar.pullrequest.key=7 -Dsonar.pullrequest.branch=feature/7 -Dsonar.login="$SONAR_TOKEN_LTS_ADMIN_ANALYSIS"

sonar-scanner -Dsonar.host.url=http://localhost:7000 -Dsonar.login="$SONAR_TOKEN_CB_ADMIN_ANALYSIS"
