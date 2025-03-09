#!/bin/bash
#
# media-tools
# Copyright (C) 2022-2025 Olivier Korach
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

localbuild="$1"

buildDir="$ROOTDIR/build"
pylintReport="$buildDir/pylint-report.out"
# banditReport="$buildDir/bandit-report.json"
flake8Report="$buildDir/flake8-report.out"
shellcheckReport="$buildDir/external-issues-shellcheck.json"
trivyReport="$buildDir/external-issues-trivy.json"
[ ! -d "$buildDir" ] && mkdir "$buildDir"
# rm -rf -- ${buildDir:?"."}/* .coverage */__pycache__ */*.pyc # mediatools/__pycache__  tests/__pycache__

echo "===> Running pylint"
rm -f "$pylintReport"
pylint --rcfile "$CONFDIR"/pylintrc "$ROOTDIR"/*.py "$ROOTDIR"/*/*.py -r n --msg-template="{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}" | tee "$pylintReport"
re=$?
if [ "$re" == "32" ]; then
    >&2 echo "ERROR: pylint execution failed, errcode $re, aborting..."
    exit $re
fi

echo "===> Running flake8"
rm -f "$flake8Report"
# See .flake8 file for settings
flake8 --config "$CONFIG/.flake8" "$ROOTDIR" >"$flake8Report"

if [ "$localbuild" = "true" ]; then
    echo "===> Running shellcheck"
    shellcheck "$ROOTDIR"/*.sh "$ROOTDIR"/*/*.sh -s bash -f json | "$CONFDIR"/shellcheck2sonar.py >"$shellcheckReport"
    [ ! -s "$shellcheckReport" ] && rm -f "$shellcheckReport"

    echo "===> Running checkov"
    checkov -d . --framework dockerfile -o sarif --output-file-path "$buildDir"

    echo "===> Running trivy"
    "$CONFDIR"/build.sh docker
    trivy image -f json -o "$buildDir"/trivy_results.json olivierkorach/sonar-tools:latest
    python3 "$CONFDIR"/trivy2sonar.py < "$buildDir"/trivy_results.json > "$trivyReport"
    [ ! -s "$trivyReport" ] && rm -f "$trivyReport"
fi