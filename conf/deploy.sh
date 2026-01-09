#!/bin/bash
#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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

deps=0
"${CONF_DIR}"/build.sh "$@"

while [[ $# -ne 0 ]]; do
    case "${1}" in
        deps)
            deps=1
            ;;
        *)
            ;;
    esac
    shift
done

# Deploy locally for tests
if [[ "${deps}" = "1" ]]; then
    pipopts="--upgrade"
else
    pipopts="--no-deps"
fi
pip install "${pipopts}" --force-reinstall "${ROOT_DIR}"/dist/sonar_tools-*-py3-*.whl
