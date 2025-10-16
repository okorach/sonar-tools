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
linters_to_run="${3:-ruff,pylint,flake8,trivy,checkov,shellcheck}"

if [[ "${localbuild}" = "" ]]; then
    localbuild="true"
    if [[ "${CI}" != "" ]]; then
        localbuild="false"
    fi
fi

. "${CONF_DIR}/env.sh"

[[ ! -d "${BUILD_DIR}" ]] && mkdir "${BUILD_DIR}"
# rm -rf -- ${BUILD_DIR:?"."}/* .coverage */__pycache__ */*.pyc # mediatools/__pycache__  tests/__pycache__

if [[ "${linters_to_run}" == *"ruff"* ]]; then
    echo "===> Running ruff"
    rm -f "${RUFF_REPORT}"
    ruff check . | tee "${BUILD_DIR}/ruff-report.txt" | "${CONF_DIR}"/ruff2sonar.py "${external_format}" >"${RUFF_REPORT}"
    re=$?
    if [[ "${re}" = "32" ]]; then
        >&2 echo "ERROR: pylint execution failed, errcode ${re}, aborting..."
        exit "${re}"
    fi
    cat "${BUILD_DIR}/ruff-report.txt"
fi

if [[ "${linters_to_run}" == *"pylint"* ]]; then
    echo "===> Running pylint"
    rm -f "${PYLINT_REPORT}"
    pylint --rcfile "${CONF_DIR}"/pylintrc "${ROOT_DIR}"/*.py "${ROOT_DIR}"/*/*.py -r n --msg-template="{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}" | tee "${PYLINT_REPORT}"
    re=$?
    if [[ "${re}" = "32" ]]; then
        >&2 echo "ERROR: pylint execution failed, errcode ${re}, aborting..."
        exit "${re}"
    fi
fi

if [[ "${linters_to_run}" == *"flake8"* ]]; then
    echo "===> Running flake8"
    rm -f "${FLAKE8_REPORT}"
    # See .flake8 file for settings
    flake8 --config "${CONF_DIR}/.flake8" "${ROOT_DIR}" | tee "${FLAKE8_REPORT}"
fi

if [[ "${localbuild}" = "true" ]]; then
    if [[ "${linters_to_run}" == *"shellcheck"* ]]; then
        echo "===> Running shellcheck"
        shellcheck "$(find "${ROOT_DIR}"" . -name '*.sh') \
            -s bash -f json | jq | tee "${BUILD_DIR}/shellcheck-report.json" | "${CONF_DIR}"/shellcheck2sonar.py "${external_format}" > "${SHELLCHECK_REPORT}"
        [[ ! -s "${SHELLCHECK_REPORT}" ]] && rm -f "${SHELLCHECK_REPORT}"
        cat "${BUILD_DIR}/shellcheck-report.json"
    fi
    if [[ "${linters_to_run}" == *"checkov"* ]]; then
        echo "===> Running checkov"
        checkov -d . --framework dockerfile -o sarif --output-file-path "${BUILD_DIR}"
    fi
    if [[ "${linters_to_run}" == *"trivy"* ]]; then
        echo "===> Running trivy"
        "${CONF_DIR}"/build.sh docker
        trivy image -f json -o "${BUILD_DIR}"/trivy_results.json olivierkorach/sonar-tools:latest
        cat "${BUILD_DIR}"/trivy_results.json
        python3 "${CONF_DIR}"/trivy2sonar.py "${external_format}" < "${BUILD_DIR}"/trivy_results.json > "${TRIVY_REPORT}"
        [[ ! -s "${TRIVY_REPORT}" ]] && rm -f "${TRIVY_REPORT}"
    fi
fi