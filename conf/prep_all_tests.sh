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

SYNC_PROJECT_KEY="TESTSYNC"

# Deletes and recreates a fresh $SYNC_PROJECT_KEY project in SonarQube
curl -X POST -u "$SONAR_TOKEN_LATEST_ADMIN_USER:" "http://localhost:20010/api/projects/delete?project=$SYNC_PROJECT_KEY"
conf/scan.sh -Dsonar.host.url=http://localhost:20010 -Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY -Dsonar.token="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS"

curl -X POST -u "$SONAR_TOKEN_LATEST_ADMIN_USER:" "http://localhost:10000/api/projects/delete?project=$SYNC_PROJECT_KEY"
sonar-scanner -Dsonar.host.url=http://localhost:10000 -Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY -Dsonar.login="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS" -Dsonar.token="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS"
curl -X POST -u "$SONAR_TOKEN_LATEST_ADMIN_USER:" "http://localhost:20010/api/projects/delete?project=$SYNC_PROJECT_KEY"
sonar-scanner -Dsonar.host.url=http://localhost:20010 -Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY -Dsonar.login="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS" -Dsonar.token="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS"
curl -X POST -u "$SONAR_TOKEN_LATEST_ADMIN_USER:" "http://localhost:7000/api/projects/delete?project=$SYNC_PROJECT_KEY"
sonar-scanner -Dsonar.host.url=http://localhost:7000 -Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY -Dsonar.login="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS" -Dsonar.token="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS"
curl -X POST -u "$SONAR_TOKEN_9_ADMIN_USER:" "http://localhost:9000/api/projects/delete?project=$SYNC_PROJECT_KEY"
sonar-scanner -Dsonar.host.url=http://localhost:9000 -Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY -Dsonar.login="$SONAR_TOKEN_9_ADMIN_ANALYSIS" -Dsonar.token="$SONAR_TOKEN_9_ADMIN_ANALYSIS"

curl -X POST -u "$SONAR_TOKEN_SONARCLOUD:" "https://sonarcloud.io/api/projects/delete?project=$SYNC_PROJECT_KEY"
sonar-scanner -Dsonar.host.url=https://sonarcloud.io -Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY -Dsonar.organization=okorach -Dsonar.login="$SONAR_TOKEN_SONARCLOUD" -Dsonar.token="$SONAR_TOKEN_SONARCLOUD"

sonar-scanner -Dsonar.host.url=http://localhost:10000 -Dsonar.pullrequest.key=5 -Dsonar.pullrequest.branch=feature/5
sonar-scanner -Dsonar.host.url=http://localhost:10000 -Dsonar.pullrequest.key=7 -Dsonar.pullrequest.branch=feature/7

sonar-scanner -Dsonar.host.url=http://localhost:8000 -Dsonar.pullrequest.key=5 -Dsonar.pullrequest.branch=feature/5 -Dsonar.login="$SONAR_TOKEN_LTS_ADMIN_ANALYSIS"
sonar-scanner -Dsonar.host.url=http://localhost:8000 -Dsonar.pullrequest.key=7 -Dsonar.pullrequest.branch=feature/7 -Dsonar.login="$SONAR_TOKEN_LTS_ADMIN_ANALYSIS"

sonar-scanner -Dsonar.host.url=http://localhost:7000 -Dsonar.login="$SONAR_TOKEN_CB_ADMIN_ANALYSIS"

# Format for 10.x and 9.x is different, file was generated for 10.x, so removing for 9.9
rm build/external-issues*
sonar-scanner -Dsonar.host.url=http://localhost:9000 -Dsonar.pullrequest.key=5 -Dsonar.pullrequest.branch=feature/5 -Dsonar.login="$SONAR_TOKEN_9_ADMIN_ANALYSIS"
sonar-scanner -Dsonar.host.url=http://localhost:9000 -Dsonar.pullrequest.key=7 -Dsonar.pullrequest.branch=feature/7 -Dsonar.login="$SONAR_TOKEN_9_ADMIN_ANALYSIS"

