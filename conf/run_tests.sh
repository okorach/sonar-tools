#!/bin/bash
#
# sonar-tools
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

# ME="$( basename "${BASH_SOURCE[0]}" )"
ROOTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONFDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
buildDir="$ROOTDIR/build"

[ ! -d "$buildDir" ] && mkdir "$buildDir"

echo "Running tests"

. "$CONFDIR/build_tests.sh"


for target in latest cb 9 cloud
do
    sonar start -i $target && sleep 30
    if [ -d "$ROOTDIR/$GEN_LOC/$target/" ]; then
        coverage run --branch --source="$ROOTDIR" -m pytest "$ROOTDIR/$GEN_LOC/$target/" --junit-xml="$buildDir/xunit-results-$target.xml"
        coverage xml -o "$buildDir/coverage-$target.xml"
    fi
    if [ "$target" != "latest" ]; then
        sonar stop -i $target
    fi
done
