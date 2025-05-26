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
SONAR_TOOLS_RELEASE="$ROOTDIR/sonar/version.py"

build_docs=0
build_docker=0

while [ $# -ne 0 ]; do
    case $1 in
        docs|doc)
            build_docs=1
            ;;
        docker)
            build_docker=1
            ;;
        *)
            ;;
    esac
    shift
done

echo "======= FORMATTING CODE ========="
black --line-length=150 .
echo "======= BUILDING PACKAGE ========="
rm -rf "$ROOTDIR/build/lib/sonar" "$ROOTDIR/build/lib/cli" "$ROOTDIR"/build/scripts*/sonar-tools "$ROOTDIR"/dist/sonar_tools*
python -m build

if [ "$build_docs" == "1" ]; then
    echo "======= BUILDING DOCS ========="
    rm -rf doc/api/build
    sphinx-build -b html doc/api/source doc/api/build
fi

if [ "$build_docker" == "1" ]; then
    echo "======= BUILDING DOCKER IMAGE WITH SNAPSHOT ========="
    version=$(grep PACKAGE_VERSION "$SONAR_TOOLS_RELEASE" | cut -d "=" -f 2 | cut -d '"' -f 2)
    docker build -t "olivierkorach/sonar-tools:$version-snapshot" -t olivierkorach/sonar-tools:latest -f "$CONFDIR/snapshot.Dockerfile" "$ROOTDIR" --load
fi
