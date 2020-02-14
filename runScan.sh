#!/bin/bash

pylintReport="pylint-report.out"
echo "Running pylint"
rm -f $pylintReport
pylint *.py */*.py -r n --msg-template="{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}" | tee $pylintReport
re=$?
if [ "$re" == "32" ]; then
  >&2 echo "ERROR: pylint execution failed, errcode $re, aborting..."
  exit $re
fi

sonar-scanner -Dsonar.python.pylint.reportPath=$pylintReport $*
