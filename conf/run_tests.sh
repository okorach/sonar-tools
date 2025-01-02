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
coverageReportLatest="$buildDir/coverage-latest.xml"
coverageReportLts="$buildDir/coverage-lts.xml"
coverageReportCloud="$buildDir/coverage-cloud.xml"

utReportLatest="$buildDir/xunit-results.xml"
utReportLts="$buildDir/xunit-results-lts.xml"
utReportCloud="$buildDir/xunit-results-cloud.xml"

[ ! -d $buildDir ] && mkdir $buildDir

echo "Running tests"

$CONFDIR/prep_tests.sh

export SONAR_HOST_URL=${1:-${SONAR_HOST_URL}}

if [ -d "$ROOTDIR/test/latest/" ]; then
    coverage run --branch --source=$ROOTDIR -m pytest $ROOTDIR/test/latest/ --junit-xml="$utReportLatest"
    coverage xml -o $coverageReportLatest
fi

if [ -d "$ROOTDIR/test/lts/" ]; then
    coverage run --branch --source=$ROOTDIR -m pytest $ROOTDIR/test/lts/ --junit-xml="$utReportLts"
    coverage xml -o $coverageReportLts
fi

if [ false ]; then
    if [ -d "$ROOTDIR/test_cloud/" ]; then
        coverage run --branch --source=$ROOTDIR -m pytest $ROOTDIR/test/cloud/ --junit-xml="$utReportCloud"
        coverage xml -o $coverageReportCloud
    fi
fi
