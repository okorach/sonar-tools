#!/bin/bash
#
# sonar-tools
# Copyright (C) 2024 Olivier Korach
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

build_image=1
release=0

while [ $# -ne 0 ]; do
    case $1 in
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

black --line-length=150 .
rm -rf build dist
python3 setup_migration.py bdist_wheel

# Deploy locally for tests
pip install --upgrade --force-reinstall dist/sonar_migration-*-py3-*.whl

if [ "$build_image" == "1" ]; then
    docker build -t olivierkorach/sonar-migration:0.2 -t olivierkorach/sonar-migration:latest -f docker/migration-snapshot.Dockerfile .
fi

# Deploy on pypi.org once released
if [ "$release" = "1" ]; then
    echo "Confirm release [y/n] ?"
    read -r confirm
    if [ "$confirm" = "y" ]; then
        python3 -m twine upload dist/sonar_migration-*-py3-*.whl
    fi
fi

if [ "$release_docker" = "1" ]; then
    docker buildx build --push --platform linux/amd64,linux/arm64 -t olivierkorach/sonar-migration:0.2  -t olivierkorach/sonar-migration:latest -f docker/migration-release.Dockerfile .
fi