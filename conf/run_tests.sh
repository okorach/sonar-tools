#!/bin/bash
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

# ME="$( basename "${BASH_SOURCE[0]}" )"
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

. "${CONF_DIR}/env.sh"

SYNC_PROJECT_KEY="TESTSYNC"

[[ ! -d "${BUILD_DIR}" ]] && mkdir "${BUILD_DIR}"

echo "Running tests"

. "${CONF_DIR}/build_tests.sh"

cd "${ROOT_DIR}" || exit 1

sonar start -i test

for target in latest cb 9 common
do
    if [[ "${target}" != "common" ]]; then
        sonar start -i "${target}" && sleep 30
    fi
    if [[ -d "${ROOT_DIR}/${GEN_LOC}/${target}/" ]]; then
        # Recreate a fresh TESTSYNC project for sync tests
        curl -X POST -u "${SONAR_TOKEN_TEST_ADMIN_USER}:" "${SONAR_HOST_URL_TEST}/api/projects/delete?project=${SYNC_PROJECT_KEY}"
        conf/run_scanner.sh -Dsonar.host.url="${SONAR_HOST_URL_TEST}" -Dsonar.projectKey="${SYNC_PROJECT_KEY}" -Dsonar.projectName="${SYNC_PROJECT_KEY}" -Dsonar.token="${SONAR_TOKEN_TEST_ADMIN_ANALYSIS}"
        # Run tests
        poetry run coverage run --branch --source="${ROOT_DIR}" -m pytest "${ROOT_DIR}/${GEN_LOC}/${target}/" --junit-xml="${BUILD_DIR}/xunit-results-${target}.xml"
        poetry run coverage xml -o "${BUILD_DIR}/coverage-${target}.xml"
    fi
done
