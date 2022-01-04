
set -euo pipefail

[ $# -eq 0 ] && echo "Usage: $0 <env1> [... <envN>]" && exit 1

mkdir -p tmp
rm -f tmp/*

echo "Restore sonar-tools last released version"
echo "Y" | pip uninstall sonar-tools
pip install sonar-tools
for env in $*
do
    . sqenv $env
    sonar-measures-export -b -o tmp/measures-$env-released.csv -m _main
    sonar-issues-export -o tmp/findings-$env-released.csv
    sonar-audit >tmp/audit-$env-released.csv || echo "OK"
    sonar-loc -n -a >tmp/loc-$env-released.csv 
done

echo "Install sonar-tools current local version"
./deploy.sh
for env in $*
do
    echo "Running with environment $env"
    . sqenv $env
    sonar-measures-export -b -o tmp/measures-$env-unreleased.csv -m _main
    [ -s "tmp/measures-$env-unreleased.csv" ]
    sonar-measures-export -b -p -r -d -m _all >tmp/measures-$env-2.csv
    [ -s "tmp/measures-$env-2.csv" ]
    sonar-measures-export -b -o tmp/measures-$env-1.json -m _all
    [ -s "tmp/measures-$env-1.json" ]
    sonar-measures-export -b -p -r -d -m _all -f json >tmp/measures-$env-2.json
    [ -s "tmp/measures-$env-2.json" ]

    sonar-findings-export -o tmp/findings-$env-unreleased.csv
    [ -s "tmp/findings-$env-unreleased.csv" ]
    sonar-findings-export -o tmp/findings-$env-1.json
    [ -s "tmp/findings-$env-1.json" ]
    sonar-findings-export -f json -k okorach_audio-video-tools,okorach_sonarqube-tools >tmp/findings-$env-2.json
    [ -s "tmp/findings-$env-2.json" ]
    sonar-findings-export -f json -k okorach_audio-video-tools,okorach_sonarqube-tools --useFindings >tmp/findings-$env-3.json
    [ -s "tmp/findings-$env-3.json" ]

    sonar-audit >tmp/audit-$env-unreleased.csv || echo "OK"
    [ -s "tmp/audit-$env-unreleased.csv" ]
    sonar-audit -f tmp/audit-$env-1.json || echo "OK"
    [ -s "tmp/audit-$env-1.json" ]
    sonar-audit --format json --what qp,qg,settings >tmp/audit-$env-2.json || echo "OK"
    [ -s "tmp/audit-$env-2.json" ]

    sonar-housekeeper -P 365 -B 90 -T 180 -R 30 >tmp/housekeeper-$env-1.csv || echo "OK"
    [ -s "tmp/housekeeper-$env-1.csv" ]

    sonar-loc >tmp/loc-$env-1.csv
    [ -s "tmp/loc-$env-1.csv" ]
    sonar-loc -n -a >tmp/loc-$env-unreleased.csv 
    [ -s "tmp/loc-$env-unreleased.csv" ]

    sonar-projects-export
done

rm -f diff.txt
for env in $*
do
    for f in measures findings audit loc
    do
        echo "==========================" | tee -a diff.txt
        echo $f-$env diff                 | tee -a diff.txt
        echo "==========================" | tee -a diff.txt
        sort tmp/$f-$env-released.csv >tmp/$f-$env-released.sorted.csv
        sort tmp/$f-$env-unreleased.csv >tmp/$f-$env-unreleased.sorted.csv
        diff tmp/$f-$env-released.sorted.csv tmp/$f-$env-unreleased.sorted.csv | tee -a diff.txt
    done
done

echo "====================================="
echo "          IT tests success"
echo "====================================="
