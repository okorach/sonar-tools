#!/bin/bash
#
# media-tools
# Copyright (C) 2022-2025 Olivier Korach
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

ME="$( basename "${BASH_SOURCE[0]}" )"
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

external_format="${1}"
localbuild="${2}"

. ${CONF_DIR}/env

[[ ! -d "${BUILD_DIR}" ]] && mkdir "${BUILD_DIR}"
# rm -rf -- ${BUILD_DIR:?"."}/* .coverage */__pycache__ */*.pyc # mediatools/__pycache__  tests/__pycache__

echo "===> Running ruff"
rm -f "${ruffReport}"
ruff check . | tee "${BUILD_DIR}/ruff-report.txt" | "${CONF_DIR}"/ruff2sonar.py "${external_format}" >"${ruffReport}"
re=$?
if [[ "${re}" = "32" ]]; then
    >&2 echo "ERROR: pylint execution failed, errcode ${re}, aborting..."
    exit "${re}"
fi
cat "${BUILD_DIR}/ruff-report.txt"

echo "===> Running pylint"
rm -f "${pylintReport}"
pylint --rcfile "${CONF_DIR}"/pylintrc "${ROOT_DIR}"/*.py "${ROOT_DIR}"/*/*.py -r n --msg-template="{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}" | tee "${pylintReport}"
re=$?
if [[ "${re}" = "32" ]]; then
    >&2 echo "ERROR: pylint execution failed, errcode ${re}, aborting..."
    exit "${re}"
fi

echo "===> Running flake8"
rm -f "${flake8Report}"
# See .flake8 file for settings
flake8 --config "${CONFIG}/.flake8" "${ROOT_DIR}" | tee "${flake8Report}"

if [[ "${localbuild}" = "true" ]]; then
    echo "===> Running shellcheck"
    shellcheck "${ROOT_DIR}"/*.sh "${ROOT_DIR}"/*/*.sh -s bash -f json | jq | tee "${BUILD_DIR}/shellcheck-report.json" | "${CONF_DIR}"/shellcheck2sonar.py "${external_format}" > "${shellcheckReport}"
    [[ ! -s "${shellcheckReport}" ]] && rm -f "${shellcheckReport}"
    cat "${BUILD_DIR}/shellcheck-report.json"

    echo "===> Running checkov"
    checkov -d . --framework dockerfile -o sarif --output-file-path "${BUILD_DIR}"

    echo "===> Running trivy"
    "${CONF_DIR}"/build.sh docker
    trivy image -f json -o "${BUILD_DIR}"/trivy_results.json olivierkorach/sonar-tools:latest
    cat "${BUILD_DIR}"/trivy_results.json
    python3 "${CONF_DIR}"/trivy2sonar.py "${external_format}" < "${BUILD_DIR}"/trivy_results.json > "${trivyReport}"
    [[ ! -s "${trivyReport}" ]] && rm -f "${trivyReport}"
fi