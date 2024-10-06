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

[ ! -d $buildDir ] && mkdir $buildDir

echo "Running tests"
unreadableSif=$ROOTDIR/test/sif_not_readable.json
chmod u-rw $unreadableSif
export SONAR_HOST_URL=${1:-${SONAR_HOST_URL_TEST}}
coverage run --source=$ROOTDIR -m pytest $ROOTDIR/test/
coverage xml -o $coverageReport
chmod u+rw $unreadableSif
