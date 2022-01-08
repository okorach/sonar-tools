#!/bin/bash
#
# sonar-tools
# Copyright (C) 2021-2022 Olivier Korach
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
set -euo pipefail

check() {
    if [ -s "$1" ]; then
        echo "Output file $1 is OK"
    else
        echo "Output file $1 is missing or empty" | tee -a $IT_LOG_FILE
        exit 1
    fi
}


[ $# -eq 0 ] && echo "Usage: $0 <env1> [... <envN>]" && exit 1


IT_LOG_FILE="tmp/it.log"
mkdir -p tmp
rm -f tmp/*

noExport=0
if [ $1 == "--noExport" ]; then
    noExport=1
    shift
fi

echo "Install sonar-tools current local version" | tee -a $IT_LOG_FILE
./deploy.sh
for env in $*
do
    echo "Running with environment $env" | tee -a $IT_LOG_FILE
    . sqenv $env
    echo "IT $env sonar-measures-export" | tee -a $IT_LOG_FILE

    f="tmp/measures-$env-unreleased.csv"
    sonar-measures-export -b -o $f -m _main --includeURLs
    check $f
    f="tmp/measures-$env-2.csv"
    sonar-measures-export -b -p -r -d -m _all >$f
    check $f
    f="tmp/measures-$env-1.json"
    sonar-measures-export -b -o $f -m _all
    check $f
    f="tmp/measures-$env-2.json"
    sonar-measures-export -b -p -r -d -m _all -f json >$f
    check $f
    f="tmp/measures-$env-3.csv"
    sonar-measures-export -b -o $f --csvSeparator '+' -m _main
    check $f

    echo "IT $env sonar-findings-export" | tee -a $IT_LOG_FILE
    f="tmp/findings-$env-unreleased.csv"
    sonar-findings-export -v DEBUG -o tmp/findings-$env-unreleased.csv
    check $f
    f="tmp/findings-$env-1.json"
    sonar-findings-export -o $f
    check $f
    f="tmp/findings-$env-2.json"
    sonar-findings-export -v DEBUG -f json -k okorach_audio-video-tools,okorach_sonarqube-tools >$f
    check $f
    f="tmp/findings-$env-3.json"
    sonar-findings-export -v DEBUG -f json -k okorach_audio-video-tools,okorach_sonarqube-tools --useFindings >$f
    check $f
    f="tmp/findings-$env-4.csv"
    sonar-findings-export -f json -k okorach_audio-video-tools,okorach_sonarqube-tools --csvSeparator '+' >$f
    check $f

    echo "IT $env sonar-audit" | tee -a $IT_LOG_FILE
    f="tmp/audit-$env-unreleased.csv"
    sonar-audit >$f
    check $f
    f="tmp/audit-$env-1.json"
    sonar-audit -f $f
    check $f
    f="tmp/audit-$env-2.json"
    sonar-audit --format json --what qp,qg,settings >$f
    check $f
    f="tmp/audit-$env-3.csv"
    sonar-audit  --csvSeparator '+' --format csv >$f
    check $f

    echo "IT $env sonar-housekeeper" | tee -a $IT_LOG_FILE
    f="tmp/housekeeper-$env-1.csv"
    sonar-housekeeper -P 365 -B 90 -T 180 -R 30 >$f
    check $f

    echo "IT $env sonar-loc" | tee -a $IT_LOG_FILE
    f="tmp/loc-$env-1.csv"
    sonar-loc >$f
    check $f
    f="tmp/loc-$env-unreleased.csv"
    sonar-loc -n -a >$f
    check $f
    f="tmp/loc-$env-2.csv"
    sonar-loc -n -a -o $f --csvSeparator ';'
    check $f

    if [ $noExport -eq 1 ]; then
        echo "IT $env sonar-projects-export test skipped" | tee -a $IT_LOG_FILE
    else
        echo "IT $env sonar-projects-export" | tee -a $IT_LOG_FILE
        sonar-projects-export
    fi
done

echo "Restore sonar-tools last released version"
echo "Y" | pip uninstall sonar-tools
pip install sonar-tools
for env in $*
do
    . sqenv $env
    echo "IT released tools $env" | tee -a $IT_LOG_FILE
    sonar-measures-export -b -o tmp/measures-$env-released.csv -m _main --includeURLs
    sonar-issues-export -o tmp/findings-$env-released.csv
    sonar-audit >tmp/audit-$env-released.csv || echo "OK"
    sonar-loc -n -a >tmp/loc-$env-released.csv 
done
./deploy.sh
for env in $*
do
    echo "IT compare released and unreleased $env" | tee -a $IT_LOG_FILE
    for f in measures findings audit loc
    do
        echo "==========================" | tee -a $IT_LOG_FILE
        echo $f-$env diff                 | tee -a $IT_LOG_FILE
        echo "==========================" | tee -a $IT_LOG_FILE
        sort tmp/$f-$env-released.csv | sed 's/,None/,/g' sed 's/;/,/g' >tmp/$f-$env-released.sorted.csv
        mv tmp/$f-$env-released.sorted.csv tmp/$f-$env-released.csv
        sort tmp/$f-$env-unreleased.csv >tmp/$f-$env-unreleased.sorted.csv
        mv tmp/$f-$env-unreleased.sorted.csv tmp/$f-$env-unreleased.csv
        diff tmp/$f-$env-released.csv tmp/$f-$env-unreleased.csv | tee -a $IT_LOG_FILE
    done
done

echo "====================================="
echo "          IT tests success"
echo "====================================="
