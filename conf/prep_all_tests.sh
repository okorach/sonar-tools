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
NAME_AND_KEY="-Dsonar.projectKey=$SYNC_PROJECT_KEY -Dsonar.projectName=$SYNC_PROJECT_KEY"

function create_fresh_project {
    key="$1"
    url="$2"
    usertoken="$3"
    token="$4"
    shift 3
    opts=("$@")
    opt_org=""
    if [ "$url" == "https://sonarcloud.io" ]; then
        opt_org="-Dsonar.organization=okorach"
    fi
    opt_token="-Dsonar.token=$token"
    if [ "$url" == "$SONAR_HOST_URL_9" ]; then
        opt_token="-Dsonar.login=$token"  
    fi
    curl -X POST -u "$usertoken:" "$url/api/projects/delete?project=$key"
    conf/scan.sh "${opts[@]}" -Dsonar.projectKey=$key -Dsonar.projectName=$key -Dsonar.host.url=$url $opt_token $opt_org 
}

create_fresh_project "$SYNC_PROJECT_KEY" "${SONAR_HOST_URL_TEST:?}" "$SONAR_TOKEN_TEST_ADMIN_USER" "$SONAR_TOKEN_TEST_ADMIN_ANALYSIS" -nolint
create_fresh_project "$SYNC_PROJECT_KEY" "${SONAR_HOST_URL_LATEST:?}" "$SONAR_TOKEN_LATEST_ADMIN_USER" "$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS"
create_fresh_project "$SYNC_PROJECT_KEY" "${SONAR_HOST_URL_CB:?}" "$SONAR_TOKEN_CB_ADMIN_USER" "$SONAR_TOKEN_CB_ADMIN_ANALYSIS"
create_fresh_project "$SYNC_PROJECT_KEY" "${SONAR_HOST_URL_9:?}" "$SONAR_TOKEN_9_ADMIN_USER" "$SONAR_TOKEN_9_ADMIN_ANALYSIS"
create_fresh_project "$SYNC_PROJECT_KEY" "https://sonarcloud.io" "$SONAR_TOKEN_SONARCLOUD" "$SONAR_TOKEN_SONARCLOUD"
create_fresh_project "$SYNC_PROJECT_KEY" "${SONAR_HOST_URL_CB:?}" "$SONAR_TOKEN_CB_ADMIN_USER" "$SONAR_TOKEN_CB_ADMIN_ANALYSIS"

for pr in 5 7; do
    sonar-scanner -Dsonar.host.url=${SONAR_HOST_URL_LATEST:?} -Dsonar.pullrequest.key=$pr -Dsonar.pullrequest.branch=feature/$pr -Dsonar.token="$SONAR_TOKEN_LATEST_ADMIN_ANALYSIS"
    sonar-scanner -Dsonar.host.url=${SONAR_HOST_URL_LTS:?} -Dsonar.pullrequest.key=$pr -Dsonar.pullrequest.branch=feature/$pr -Dsonar.token="$SONAR_TOKEN_LTS_ADMIN_ANALYSIS"
done
# Format for 10.x and 9.x is different, file was generated for 10.x, so removing for 9.9

rm build/external-issues*
for pr in 5 7; do
    sonar-scanner -Dsonar.host.url=${SONAR_HOST_URL_9:?} -Dsonar.pullrequest.key=$pr -Dsonar.pullrequest.branch=feature/$pr -Dsonar.login="$SONAR_TOKEN_9_ADMIN_ANALYSIS"
done