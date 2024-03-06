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
tests=pytest
while [ $# -ne 0 ]
do
  case "$1" in
    -nolint)
      dolint=false
      ;;
    -unittest)
      tests=unittest
      ;;
    *)
      scanOpts="$scanOpts $1"
      ;;
  esac
  shift
done

buildDir="build"
pylintReport="$buildDir/pylint-report.out"
banditReport="$buildDir/bandit-report.json"
flake8Report="$buildDir/flake8-report.out"
coverageReport="$buildDir/coverage.xml"

[ ! -d $buildDir ] && mkdir $buildDir
rm -rf -- ${buildDir:?"."}/* .coverage */__pycache__ */*.pyc # mediatools/__pycache__  testpytest/__pycache__ testunittest/__pycache__

echo "Running tests"
if [ "$tests" != "unittest" ]; then
  coverage run -m pytest
  # pytest --cov=mediatools --cov-branch --cov-report=xml:$coverageReport testpytest/
else
  coverage run --source=. --branch -m unittest discover
fi
coverage xml -o $coverageReport

if [ "$dolint" != "false" ]; then
  ./run_linters.sh
fi

version=$(grep PACKAGE_VERSION sonar/version.py | cut -d "=" -f 2 | sed "s/[\'\" ]//g")
version=$(echo $version)
pr_branch=""
for o in $scanOpts
do
  key="$(echo $o | cut -d '=' -f 1)"
  if [ "$key" = "-Dsonar.pullrequest.key" ]; then
    pr_branch="-Dsonar.pullrequest.branch=foo"
  fi
done


echo "Running: sonar-scanner \
  -Dsonar.projectVersion=$version \
  -Dsonar.python.flake8.reportPaths=$flake8Report \
  -Dsonar.python.pylint.reportPaths=$pylintReport \
  -Dsonar.python.bandit.reportPaths=$banditReport \
  -Dsonar.python.coverage.reportPaths=$coverageReport \
  $pr_branch \
  $scanOpts"

sonar-scanner \
  -Dsonar.projectVersion=$version \
  -Dsonar.python.flake8.reportPaths=$flake8Report \
  -Dsonar.python.pylint.reportPaths=$pylintReport \
  -Dsonar.python.bandit.reportPaths=$banditReport \
  -Dsonar.python.coverage.reportPaths=$coverageReport \
  -Dsonar.coverage.exclusions=**/*.sh \
  $pr_branch \
  $scanOpts
