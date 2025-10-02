#!/bin/bash
#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

dolint="true"
dotest="false"
if [ "$CI" == "" ]; then
  localbuild="true"
else
  localbuild="false"
fi

scanOpts=()

while [ $# -ne 0 ]
do
  case "$1" in
    -nolint)
      dolint="false"
      ;;
    -test)
      dotest="true"
      ;;
    -local)
      localbuild="true"
      ;;
    *)
      scanOpts=("${scanOpts[@]}" "$1")
      ;;
  esac
  shift
done

buildDir="build"
pylintReport="$buildDir/pylint-report.out"
flake8Report="$buildDir/flake8-report.out"

[ ! -d "$buildDir" ] && mkdir "$buildDir"
# rm -rf -- ${buildDir:?"."}/* .coverage */__pycache__ */*.pyc # mediatools/__pycache__  testpytest/__pycache__ testunittest/__pycache__


if [ "$dolint" != "false" ]; then
  "$CONFDIR"/run_linters.sh "$localbuild"
fi

if [ "$dotest" == "true" ]; then
  "$CONFDIR"/run_tests.sh
fi

version=$(grep PACKAGE_VERSION "$ROOTDIR/sonar/version.py" | cut -d "=" -f 2 | sed -e "s/[\'\" ]//g" -e "s/^ +//" -e "s/ +$//")


cmd="sonar-scanner -Dsonar.projectVersion=$version \
  -Dsonar.python.flake8.reportPaths=$flake8Report \
  -Dsonar.python.pylint.reportPaths=$pylintReport \
  -Dsonar.token=$SONAR_TOKEN \
  "${scanOpts[*]}""

if [ "$SONAR_HOST_URL" == "$SONAR_HOST_URL_9" ]; then
  cms="$cmd -Dsonar.login=$SONAR_TOKEN"
fi

if ls $buildDir/coverage*.xml >/dev/null 2>&1; then
  cmd="$cmd -Dsonar.python.coverage.reportPaths=$buildDir/coverage*.xml"
else
  echo "===> NO COVERAGE REPORT"
fi

if ls $buildDir/xunit-results*.xml >/dev/null 2>&1; then
  cmd="$cmd -Dsonar.python.xunit.reportPath=$buildDir/xunit-results*.xml"
else
  echo "===> NO UNIT TESTS REPORT"
  cmd="$cmd -Dsonar.python.xunit.reportPath="
fi

if ls $buildDir/external-issues*.json >/dev/null 2>&1; then
  files=$(ls $buildDir/external-issues*.json | tr '\n' ' ' | sed -E -e 's/ +$//' -e 's/ +/,/g')
  echo "EXTERNAL ISSUES FILES = $files"
  cmd="$cmd -Dsonar.externalIssuesReportPaths=$files"
else
  echo "===> NO EXTERNAL ISSUES"
fi


echo
echo "Running: $cmd" | sed "s/$SONAR_TOKEN/<SONAR_TOKEN>/g"
echo

$cmd
