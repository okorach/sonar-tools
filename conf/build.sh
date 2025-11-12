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

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

build_docs=0
build_docker=0
offline=0
deps=0

. "${CONF_DIR}/env.sh"

while [[ $# -ne 0 ]]; do
    case "${1}" in
        docs|doc)
            build_docs=1
            ;;
        docker)
            build_docker=1
            ;;
        offline)
            offline=1
            ;;
        deps)
            deps=1
            ;;
        *)
            ;;
    esac
    shift
done

echo "======= FORMATTING CODE ========="
ruff format
echo "======= BUILDING PACKAGE ========="
if [[ "${offline}" = "1" ]]; then
    cp "${ROOT_DIR}/conf/offline/setup.py" "${ROOT_DIR}/"
    cp "${ROOT_DIR}/conf/offline/sonar-tools" "${ROOT_DIR}/"
    mv "${ROOT_DIR}/pyproject.toml" "${ROOT_DIR}/pyproject.toml.bak"
    python setup.py bdist_wheel
    mv "${ROOT_DIR}/pyproject.toml.bak" "${ROOT_DIR}/pyproject.toml"
    rm "${ROOT_DIR}/setup.py" "${ROOT_DIR}/sonar-tools" "${ROOT_DIR}/sonar_tools.egg-info"
    # python -m build
else
    rm -rf "${ROOT_DIR}/build/lib/sonar" "${ROOT_DIR}/build/lib/cli" "${ROOT_DIR}"/build/scripts*/sonar-tools "${ROOT_DIR}"/dist/sonar_tools*
    poetry build
fi
# Deploy locally for tests
if [[ "${deps}" = "1" ]]; then
    pipopts="--upgrade"
else
    pipopts="--no-deps"
fi
pip install "${pipopts}" --force-reinstall "${ROOT_DIR}"/dist/sonar_tools-*-py3-*.whl

if [[ "${build_docs}" = "1" ]]; then
    echo "======= BUILDING DOCS ========="
    rm -rf doc/api/build
    sphinx-build -b html doc/api/source doc/api/build
fi

if [[ "${build_docker}" = "1" ]]; then
    echo "======= BUILDING DOCKER IMAGE WITH SNAPSHOT ========="
    docker build -t "olivierkorach/sonar-tools:${VERSION}-snapshot" -t olivierkorach/sonar-tools:latest -f "${CONF_DIR}/snapshot.Dockerfile" "${ROOT_DIR}" --load
fi
