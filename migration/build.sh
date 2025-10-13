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

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

build_image=1
release=0
release_docker=0

while [[ $# -ne 0 ]]; do
    case "${1}" in
        nodocker)
            build_image=0
            ;;
        pypi)
            release=1
            ;;
        dockerhub)
            release_docker=1
            ;;
        *)
            ;;
    esac
    shift
done

rm -rf "${ROOT_DIR}/build/lib/migration" "${ROOT_DIR}/build/lib/cli" "${ROOT_DIR}/build/lib/sonar" "${ROOT_DIR}"/build/scripts*/sonar_migration "${ROOT_DIR}"/dist/sonar_migration*
mv "${ROOT_DIR}/pyproject.toml" "${ROOT_DIR}/pyproject.toml.sonar-tools"
cp "${ROOT_DIR}/migration/pyproject.toml" "${ROOT_DIR}"
poetry build
mv "${ROOT_DIR}/pyproject.toml.sonar-tools" "${ROOT_DIR}/pyproject.toml"

# Deploy locally for tests
pip install --upgrade --force-reinstall "${ROOT_DIR}"/dist/sonar_migration-*-py3-*.whl

if [[ "${build_image}" == "1" ]]; then
    docker build -t olivierkorach/sonar-migration:latest -f migration/snapshot.Dockerfile "${ROOT_DIR}" --load
fi