#!/bin/bash
#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

build_docs=1
release=0

while [ $# -ne 0 ]; do
    case $1 in
        nodoc)
            build_docs=0
            ;;
        pypi)
            release=1
            ;;
        *)
            ;;
    esac
    shift
done

black --line-length=150 .
rm -rf build dist
python3 setup.py bdist_wheel

# Deploy locally for tests
# echo "y" | python3 -m pip uninstall sonar-tools
# python3 -m pip install dist/*-py3-*.whl
echo "y" | pip uninstall sonar-tools
pip install dist/*-py3-*.whl

if [ "$build_docs" == "1" ]; then
    rm -rf api-doc/build
    sphinx-build -b html api-doc/source api-doc/build
fi

# Deploy on pypi.org once released
if [ "$release" = "1" ]; then
    echo "Confirm release [y/n] ?"
    read confirm
    if [ "$confirm" = "y" ]; then
        python3 -m twine upload dist/*
    fi
fi