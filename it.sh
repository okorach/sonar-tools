
set -euo pipefail

echo "Hello $*"

[ $# -eq 0 ] && echo "Usage: $0 <env1> [... <envN>]" && exit 1

rm -f *.json *.csv

for env in $*
do
    echo "Running with environment $env"
    . sqenv $env
    sonar-measures-export -b -o measures-$env-1.csv -m _all
    [ -s "measures-$env-1.csv" ]
    sonar-measures-export -b -p -r -d -m _all >measures-$env-2.csv
    [ -s "measures-$env-2.csv" ]
    sonar-measures-export -b -o measures-$env-1.json -m _all
    [ -s "measures-$env-1.json" ]
    sonar-measures-export -b -p -r -d -m _all -f json >measures-$env-2.json
    [ -s "measures-$env-2.json" ]

    sonar-issues-export -o issues-$env-1.csv
    [ -s "issues-$env-1.csv" ]
    sonar-issues-export -o issues-$env-1.json
    [ -s "issues-$env-1.json" ]
    sonar-issues-export -f json -k okorach_audio-video-tools,okorach_sonarqube-tools >issues-$env-2.json
    [ -s "issues-$env-2.json" ]
    sonar-issues-export -f json -k okorach_audio-video-tools,okorach_sonarqube-tools --useFindings >issues-$env-3.json
    [ -s "issues-$env-3.json" ]

    sonar-audit || echo "OK" >audit-$env-1.csv
    [ -s "audit-$env-1.csv" ]
    sonar-audit -f audit-$env-1.json || echo "OK"
    [ -s "audit-$env-1.json" ]
    sonar-audit --format json --what qp,qg,settings || echo "OK" >audit-$env-2.json
    [ -s "audit-$env-2.json" ]

    sonar-housekeeper -P 365 -B 90 -T 180 -R 30 >housekeeper-$env-1.csv || echo "OK"
    [ -s "housekeeper-$env-1.csv" ]

    sonar-loc >loc-$env-1.csv
    [ -s "loc-$env-1.csv" ]
    sonar-loc -n -a >loc-$env-2.csv 
    [ -s "loc-$env-2.csv" ]

    sonar-projects-export
done

echo "====================================="
echo "          IT tests success"
echo "====================================="
