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

GEN_LOC=test/gen

echo ""
echo "Generating edition / version specific tests"

for target in lts latest cb 9 9-ce common
do
    echo "Generating tests for $target"
    rm -rf "$ROOTDIR/$GEN_LOC/$target"
    mkdir -p "$ROOTDIR/$GEN_LOC/$target" 2>/dev/null
    if [ "$target" == "common" ]; then
        b=$(basename "$f" .py)
        cp conftest.py "$ROOTDIR/$GEN_LOC/$target"
        cp utilities.py "$ROOTDIR/$GEN_LOC/$target"
        cp test_common*.py "$ROOTDIR/$GEN_LOC/$target"
    else
        for f in *.py
        do
            b=$(basename "$f" .py)
            cp "$f" "$ROOTDIR/$GEN_LOC/$target/${b}_${target}.py"
        done
        cp "credentials-$target.py" "$ROOTDIR/$GEN_LOC/$target/credentials.py"
        mv "$ROOTDIR/$GEN_LOC/$target/conftest_${target}.py" "$ROOTDIR/$GEN_LOC/$target/conftest.py"
        mv "$ROOTDIR/$GEN_LOC/$target/utilities_${target}.py" "$ROOTDIR/$GEN_LOC/$target/utilities.py"
        rm "$ROOTDIR/$GEN_LOC/$target/"test_common*.py
    fi
done

