# Copyright (C) 2024-2025 Olivier Korach
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

. "${CONF_DIR}"/env.sh

"${CONF_DIR}"/build.sh

DOCKERFILE_RELEASE="${CONF_DIR}/release.Dockerfile"

docker_VERSION=$(grep 'pip install sonar-tools==' "${DOCKERFILE_RELEASE}" | sed -E 's/.*sonar-tools==([0-9\.]+).*/\1/')

if [[ "${VERSION}" != "${docker_VERSION}" ]]; then
    echo "Docker VERSION and pypi VERSION are different (${docker_VERSION} vs ${VERSION}), release aborted"
    exit 1
fi

echo "Confirm release [y/n] ?"
read -r confirm
if [[ "${confirm}" = "y" ]]; then
    VERSION=$(grep PACKAGE_VERSION "${ROOT_DIR}"/sonar/VERSION.py | cut -d "=" -f 2 | sed -e "s/[\'\" ]//g" -e "s/^ +//" -e "s/ +$//")

    echo "Releasing on pypi.org"
    python3 -m twine upload "${ROOT_DIR}/dist/sonar_tools-${VERSION}-py3-none-any.whl"
    echo -n "Waiting pypi release to be effective"
    while [[ "$(get_pypi_latest_VERSION sonar-tools)" != "${VERSION}" ]]; do
        sleep 10
        echo -n "."
    done
    echo " done"
    echo "Releasing on dockerhub"
    docker buildx build --push --platform linux/amd64,linux/arm64 -t "olivierkorach/sonar-tools:${VERSION}" -t olivierkorach/sonar-tools:latest -f "${CONF_DIR}/release.Dockerfile" "${ROOT_DIR}"
    cd "${ROOT_DIR}" && docker pushrm olivierkorach/sonar-tools

    echo "Running scan"
    "${CONF_DIR}/scan.sh" -test
fi