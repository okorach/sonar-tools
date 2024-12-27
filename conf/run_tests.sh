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

ME="$( basename "${BASH_SOURCE[0]}" )"
ROOTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONFDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
buildDir="$ROOTDIR/build"
coverageReport="$buildDir/coverage.xml"
utReport="$buildDir/xunit-results.xml"
[ ! -d $buildDir ] && mkdir $buildDir

echo "Running tests"
export SONAR_HOST_URL=${1:-${SONAR_HOST_URL}}
TEST_DIRS=$ROOTDIR/test/
if [ -d "$ROOTDIR/test_lts/" ]; then
    TEST_DIRS="$TEST_DIRS $ROOTDIR/test_lts/"
fi
coverage run --branch --source=$ROOTDIR -m pytest $ROOTDIR/test/ --junit-xml="$utReport"

coverage xml -o $coverageReport
