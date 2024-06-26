#!/bin/bash
#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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

dolint=true
dotest=false

scanOpts=()

while [ $# -ne 0 ]
do
  case "$1" in
    -nolint)
      dolint=false
      ;;
    -test)
      dotest=true
      ;;
    *)
      scanOpts=("${scanOpts[@]}" "$1")
      ;;
  esac
  shift
done

buildDir="build"
pylintReport="$buildDir/pylint-report.out"
banditReport="$buildDir/bandit-report.json"
flake8Report="$buildDir/flake8-report.out"
coverageReport="$buildDir/coverage.xml"
externalIssuesReport="$buildDir/external-issue-report.json"

[ ! -d $buildDir ] && mkdir $buildDir
rm -rf -- ${buildDir:?"."}/* .coverage */__pycache__ */*.pyc # mediatools/__pycache__  testpytest/__pycache__ testunittest/__pycache__

if [ "$dotest" == "true" ]; then
  ./run_tests.sh
fi

if [ "$dolint" != "false" ]; then
  ./run_linters.sh
fi

version=$(grep PACKAGE_VERSION sonar/version.py | cut -d "=" -f 2 | sed -e "s/[\'\" ]//g" -e "s/^ +//" -e "s/ +$//")
pr_branch=""
for o in "${scanOpts[@]}"
do
  key="$(echo "$o" | cut -d '=' -f 1)"
  if [ "$key" = "-Dsonar.pullrequest.key" ]; then
    pr_branch="-Dsonar.pullrequest.branch=foo"
  fi
done

cmd="sonar-scanner -Dsonar.projectVersion=$version \
  -Dsonar.python.flake8.reportPaths=$flake8Report \
  -Dsonar.python.pylint.reportPaths=$pylintReport \
  -Dsonar.python.bandit.reportPaths=$banditReport \
  -Dsonar.externalIssuesReportPaths=$externalIssuesReport \
  -Dsonar.login=$SONAR_TOKEN \
  -Dsonar.token=$SONAR_TOKEN \
  $pr_branch" \
  "${scanOpts[@]}"

if [ -f "$coverageReport" ]; then
   cmd="$cmd -Dsonar.python.coverage.reportPaths=$coverageReport"
fi

echo "Running: $cmd"

$cmd
