#!/bin/bash
#
# sonar-tools
# Copyright (C) 2021-2024 Olivier Korach
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

cur_dir=$(dirname $0)

check() {
    if [ -s "$1" ]; then
        echo "Output file $1 is OK"
    else
        echo "Output file $1 is missing or empty" | tee -a $IT_LOG_FILE
        # exit 1
    fi
}


[ $# -eq 0 ] && echo "Usage: $0 <env1> [... <envN>]" && exit 1

IT_ROOT="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; cd .. ; pwd -P )"
IT_ROOT="$IT_ROOT/tmp"
IT_LOG_FILE="$IT_ROOT/it.log"
mkdir -p $IT_ROOT
rm -f $IT_ROOT/*.log $IT_ROOT/*.csv $IT_ROOT/*.json

noExport=0
if [ "$1" == "--noExport" ]; then
    noExport=1
    shift
fi

date | tee -a $IT_LOG_FILE
echo "Install sonar-tools current local version" | tee -a $IT_LOG_FILE
./deploy.sh nodoc
for env in $*
do
    echo "Running with environment $env" | tee -a $IT_LOG_FILE
    export SONAR_TOKEN=$SONAR_TOKEN_ADMIN_USER
    cd test;./sonar-create --pg_backup ~/backup/db.$env.backup

    echo "IT $env sonar-measures-export" | tee -a $IT_LOG_FILE

    f="$IT_ROOT/measures-$env-unrel.csv"
    sonar-measures-export -b -f $f -m _main --withURL
    check $f
    f="$IT_ROOT/measures-$env-2.csv"
    sonar-measures-export -b -p -r -d -m _all >$f
    check $f
    f="$IT_ROOT/measures-$env-1.json"
    sonar-measures-export -b -f $f -m _all
    check $f
    f="$IT_ROOT/measures-$env-2.json"
    sonar-measures-export -b -p -r -d -m _all --format json >$f
    check $f
    f="$IT_ROOT/measures-$env-3.csv"
    sonar-measures-export -b -f $f --csvSeparator '+' -m _main
    check $f

    echo "IT $env sonar-findings-export" | tee -a $IT_LOG_FILE
    f="$IT_ROOT/findings-$env-unrel.csv"
    sonar-findings-export -v DEBUG -f $IT_ROOT/findings-$env-unrel.csv
    check $f
    f="$IT_ROOT/findings-$env-1.json"
    sonar-findings-export -f $f
    check $f
    f="$IT_ROOT/findings-$env-2.json"
    sonar-findings-export -v DEBUG --format json -k okorach_audio-video-tools,okorach_sonar-tools >$f
    check $f
    f="$IT_ROOT/findings-$env-3.json"
    sonar-findings-export -v DEBUG --format json -k okorach_audio-video-tools,okorach_sonar-tools --useFindings >$f
    check $f
    f="$IT_ROOT/findings-$env-4.csv"
    sonar-findings-export --format json -k okorach_audio-video-tools,okorach_sonar-tools --csvSeparator '+' >$f
    check $f

    echo "IT $env sonar-audit" | tee -a $IT_LOG_FILE
    f="$IT_ROOT/audit-$env-unrel.csv"
    sonar-audit >$f
    check $f
    f="$IT_ROOT/audit-$env-1.json"
    sonar-audit -f $f
    check $f
    f="$IT_ROOT/audit-$env-2.json"
    sonar-audit --format json --what qualitygates,qualityprofiles,settings >$f
    check $f
    f="$IT_ROOT/audit-$env-3.csv"
    sonar-audit  --csvSeparator '+' --format csv >$f
    check $f

    echo "IT $env sonar-housekeeper" | tee -a $IT_LOG_FILE
    f="$IT_ROOT/housekeeper-$env-1.csv"
    sonar-housekeeper -P 365 -B 90 -T 180 -R 30 >$f
    check $f

    echo "IT $env sonar-loc" | tee -a $IT_LOG_FILE
    f="$IT_ROOT/loc-$env-1.csv"
    sonar-loc >$f
    check $f
    f="$IT_ROOT/loc-$env-unrel.csv"
    sonar-loc -n -a >$f
    check $f
    f="$IT_ROOT/loc-$env-2.csv"
    sonar-loc -n -a -f $f --csvSeparator ';'
    check $f

    f="$IT_ROOT/config-$env-1.json"
    echo "IT $env sonar-config -e -w \"qualitygates, qualityprofiles, projects\" -k okorach_audio-video-tools,okorach_sonar-tools >$f" | tee -a $IT_LOG_FILE
    sonar-config -e -w "qualitygates, qualityprofiles, projects" -k okorach_audio-video-tools,okorach_sonar-tools >$f

    f="$IT_ROOT/config-$env-2.json"
    echo "IT $env sonar-config --export >$f" | tee -a $IT_LOG_FILE
    sonar-config --export >$f

    f="$IT_ROOT/config-$env-unrel.json"
    echo "IT $env sonar-config --export -f $f" | tee -a $IT_LOG_FILE
    sonar-config --export -f $f

    if [ $noExport -eq 1 ]; then
        echo "IT $env sonar-projects-export test skipped" | tee -a $IT_LOG_FILE
    else
        echo "IT $env sonar-projects-export" | tee -a $IT_LOG_FILE
        sonar-projects-export
    fi

    echo "IT $env sonar-findings-export USER export" | tee -a $IT_LOG_FILE
    f1="$IT_ROOT/findings-$env-admin.csv"
    sonar-findings-export -v DEBUG -f $f1 -k okorach_audio-video-tools,okorach_sonar-tools

    export SONAR_TOKEN=$SONAR_TOKEN_USER_USER
    f2="$IT_ROOT/findings-$env-user.csv"
    sonar-findings-export -v DEBUG -f $f2 -k okorach_audio-video-tools,okorach_sonar-tools
done

echo "Restore sonar-tools last released version"
echo "Y" | pip uninstall sonar-tools
pip install sonar-tools
for env in $*
do
    . sonar-env.sh $env
    echo "IT released tools $env" | tee -a $IT_LOG_FILE
    sonar-measures-export -b -f $IT_ROOT/measures-$env-rel.csv -m _main --withURL
    sonar-findings-export -f $IT_ROOT/findings-$env-rel.csv
    sonar-audit >$IT_ROOT/audit-$env-rel.csv || echo "OK"
    sonar-loc -n -a >$IT_ROOT/loc-$env-rel.csv 
    sonar-config -e >$IT_ROOT/config-$env-rel.json 
done
./deploy.sh nodoc
for env in $*
do
    echo "IT compare released and unreleased $env" | tee -a $IT_LOG_FILE
    for f in measures findings audit loc
    do
        root=$IT_ROOT/$f-$env
        echo "==========================" | tee -a $IT_LOG_FILE
        echo $f-$env diff                 | tee -a $IT_LOG_FILE
        echo "==========================" | tee -a $IT_LOG_FILE
        sort $root-rel.csv >$root-rel.sorted.csv
        sort $root-unrel.csv >$root-unrel.sorted.csv
        diff $root-rel.sorted.csv $root-unrel.sorted.csv | tee -a $IT_LOG_FILE || echo "" 
    done
    for f in config
    do
        root=$IT_ROOT/$f-$env
        echo "==========================" | tee -a $IT_LOG_FILE
        echo $f-$env diff                 | tee -a $IT_LOG_FILE
        echo "==========================" | tee -a $IT_LOG_FILE
        diff $root-rel.json $root-unrel.json | tee -a $IT_LOG_FILE || echo "" 
    done
    echo "==========================" | tee -a $IT_LOG_FILE
    echo findings-$env admin vs user diff                 | tee -a $IT_LOG_FILE
    echo "==========================" | tee -a $IT_LOG_FILE
    f1="$IT_ROOT/findings-$env-admin.csv"
    f2="$IT_ROOT/findings-$env-user.csv"
    diff $f1 $f2 | tee -a $IT_LOG_FILE || echo ""
done

echo "====================================="
echo "          IT tests success"
echo "====================================="
