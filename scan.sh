#!/bin/bash

buildDir="build"
[ ! -d $buildDir ] && mkdir $buildDir
pylintReport="$buildDir/pylint-report.out"
banditReport="$buildDir/bandit-report.json"
flake8Report="$buildDir/flake8-report.out"

if [ "$1" != "-nolint" ]; then
  echo "Running pylint"
  rm -f $pylintReport
  pylint *.py */*.py -r n --msg-template="{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}" | tee $pylintReport
  re=$?
  if [ "$re" == "32" ]; then
    >&2 echo "ERROR: pylint execution failed, errcode $re, aborting..."
    exit $re
  fi

  echo "Running flake8"
  rm -f $flake8Report
  flake8 --ignore=W503  --max-line-length=150 . >$flake8Report

  echo "Running bandit"
  rm -f $banditReport
  bandit -f json -r . >$banditReport
else
  shift
fi

version=`cat setup.py | grep version | cut -d "=" -f 2 | cut -d "'" -f 2`

sonar-scanner \
  -Dsonar.projectVersion=$version \
  -Dsonar.host.url=$SQ_URL \
  -Dsonar.python.flake8.reportPaths=$flake8Report \
  -Dsonar.python.pylint.reportPath=$pylintReport \
  -Dsonar.python.bandit.reportPaths=$banditReport \
  $*
