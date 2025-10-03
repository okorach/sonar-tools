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

ROOTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONFDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

"${CONFDIR}"/build.sh

SONAR_TOOLS_RELEASE="${ROOTDIR}/sonar/version.py"
DOCKERFILE_RELEASE="${CONFDIR}/release.Dockerfile"

version=$(grep PACKAGE_VERSION "$SONAR_TOOLS_RELEASE" | cut -d "=" -f 2 | cut -d '"' -f 2)

docker_version=$(grep 'pip install sonar-tools==' "${DOCKERFILE_RELEASE}" | sed -E 's/.*sonar-tools==([0-9\.]+).*/\1/')

if [ "${version}" != "${docker_version}" ]; then
    echo "Docker version and pypi version are different (${docker_version} vs ${version}), release aborted"
    exit 1
fi

echo "Confirm release [y/n] ?"
read -r confirm
if [ "$confirm" = "y" ]; then
    version=$(grep PACKAGE_VERSION "${ROOTDIR}"/sonar/version.py | cut -d "=" -f 2 | sed -e "s/[\'\" ]//g" -e "s/^ +//" -e "s/ +$//")

    echo "Releasing on pypi.org"
    python3 -m twine upload "${ROOTDIR}/dist/sonar_tools-${version}-py3-none-any.whl"
    echo -n "Waiting pypi release to be effective"
    while [ "$(get_pypi_latest_version sonar-tools)" != "${version}" ]; do
        sleep 10
        echo -n "."
    done
    echo " done"
    echo "Releasing on dockerhub"
    docker buildx build --push --platform linux/amd64,linux/arm64 -t "olivierkorach/sonar-tools:${version}" -t olivierkorach/sonar-tools:latest -f "${CONFDIR}/release.Dockerfile" "${ROOTDIR}"
    cd "${ROOTDIR}" && docker pushrm olivierkorach/sonar-tools

    echo "Running scan"
    "${CONFDIR}/scan.sh" -test
fi