#!/bin/bash
#
# sonar-tools
# Copyright (C) 2024-2026 Olivier Korach
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

[[ ! -d "${BUILD_DIR}" ]] && mkdir "${BUILD_DIR}"

echo "Running tests"

cd "${ROOT_DIR}" || exit 1

sonar start -i test

testList="${1:-"latest cb 99 cloud"}"
for target in ${testList}
do
    sonar start -i "${target}" && sleep 30
    skipCloud=""
    if [[ "${target}" != "cloud" ]]; then
        skipCloud="--ignore=${ROOT_DIR}/test/unit/test_common_sonarcloud.py"
    fi
    SONAR_TEST_PLATFORM="${target}" poetry run coverage run --append --branch --source="${ROOT_DIR}" \
        -m pytest --platform="${target}" "${ROOT_DIR}/test/unit/" \
        --ignore="${ROOT_DIR}/test/unit/test_common_audit.py" \
        --ignore="${ROOT_DIR}/test/unit/test_common_misc.py" \
        --ignore="${ROOT_DIR}/test/unit/test_common_sif.py" \
        ${skipCloud} \
        --junit-xml="${BUILD_DIR}/xunit-${target}.xml"
done

# Common tests (platform-independent)
poetry run coverage run --append --branch --source="${ROOT_DIR}" \
    -m pytest "${ROOT_DIR}"/test/unit/test_common_*.py \
    --junit-xml="${BUILD_DIR}/xunit-common.xml"

poetry run coverage xml -o "${BUILD_DIR}/coverage.xml"
