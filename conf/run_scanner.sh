#!/bin/bash
#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# VERSION 3 of the License, or (at your option) any later VERSION.
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

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

. "${CONF_DIR}/env.sh"

auth=""
if [[ "${SONAR_HOST_URL}" = "${SONAR_HOST_URL_9}" ]]; then
  auth="-Dsonar.login=${SONAR_TOKEN}"
fi

while [[ $# -ne 0 ]]
do
  case "${1}" in
    -Dsonar.host.url=*)
      scanOpts=("${scanOpts[@]}" "${1}")
      url=$(echo "${1}" | cut -d = -f 2)
      if [[ "${url}" = "${SONAR_HOST_URL_9}" ]]; then
        auth="-Dsonar.login=${SONAR_TOKEN}"
      fi
      ;;
    *)
      scanOpts=("${scanOpts[@]}" "${1}")
      ;;
  esac
  shift
done

cmd="sonar-scanner -Dsonar.projectVersion=${VERSION} \
  -Dsonar.python.flake8.reportPaths=${FLAKE8_REPORT} \
  -Dsonar.python.pylint.reportPaths=${PYLINT_REPORT} \
  -Dsonar.token=${SONAR_TOKEN} ${auth}\
  "${scanOpts[*]}""

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "${branch}" != "master" ]]; then
  cmd="${cmd} -Dsonar.branch.name=${branch}"
fi

relativeDir=$(basename "${BUILD_DIR}")
TO_CSV="tr '\n' ' ' | sed -E -e 's/ +$//' -e 's/ +/,/g'"

if ls "${BUILD_DIR}"/coverage.xml >/dev/null 2>&1; then
  cmd="${cmd} -Dsonar.python.coverage.reportPaths=${relativeDir}/coverage.xml"
else
  echo "===> NO COVERAGE REPORT"
fi

if ls "${BUILD_DIR}"/xunit-*.xml >/dev/null 2>&1; then
  echo "XUNIT FILES = ${BUILD_DIR}/xunit-*.xml"
  cmd="${cmd} -Dsonar.python.xunit.reportPath=${BUILD_DIR}/xunit-*.xml"
else
  echo "===> NO UNIT TESTS REPORT"
fi

if ls "${BUILD_DIR}"/external-issues*.json >/dev/null 2>&1; then
  files=$(ls "${BUILD_DIR}"/external-issues*.json | eval "${TO_CSV}")
  echo "EXTERNAL ISSUES FILES = ${files}"
  cmd="${cmd} -Dsonar.externalIssuesReportPaths=${files}"
else
  echo "===> NO EXTERNAL ISSUES"
fi

if ls "${BUILD_DIR}"/*.sarif >/dev/null 2>&1; then
  files=$(ls "${BUILD_DIR}"/*.sarif | eval "${TO_CSV}")
  echo "SARIF FILES = ${files}"
  cmd="${cmd} -Dsonar.sarifReportPaths=${files}"
else
  echo "===> NO SARIF REPORT"
fi

if ls "${BUILD_DIR}"/*.cdx.json >/dev/null 2>&1; then
  files=$(ls "${BUILD_DIR}"/*.cdx.json | eval "${TO_CSV}")
  echo "SBOM FILES = ${files}"
  cmd="${cmd} -Dsonar.sca.sbomImportPaths=${files}"
else
  echo "===> NO SBOM"
fi

echo "=============================================================="
echo "Running: ${cmd}" | sed "s/${SONAR_TOKEN}/<SONAR_TOKEN>/g"
echo "=============================================================="

${cmd}
