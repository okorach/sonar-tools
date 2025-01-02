#!/bin/bash
#
# sonar-tools
# Copyright (C) 2025 Olivier Korach
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

cd "$ROOTDIR/test/unit" || exit 1

for target in lts latest
do
    rm -rf "$ROOTDIR/test/$target"
    mkdir -p "$ROOTDIR/test/$target" 2>/dev/null
    for f in *.py
    do
        b=$(basename "$f" .py)
        cp "$f" "$ROOTDIR/test/$target/${b}_${target}.py"
    done
    cp "credentials-$target.py" "$ROOTDIR/test/$target/credentials.py"
    mv "$ROOTDIR/test/$target/conftest_${target}.py" "$ROOTDIR/test/$target/conftest.py"
    mv "$ROOTDIR/test/$target/utilities_${target}.py" "$ROOTDIR/test/$target/utilities.py"
done
