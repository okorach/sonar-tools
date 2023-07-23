#!/bin/bash

case $1 in
    lts)
        export SONAR_HOST_URL=$SONAR_LTS_URL
        export SONAR_TOKEN=$SONAR_LTS_TOKEN
        ;;
    latest)
        export SONAR_HOST_URL=$SONAR_LATEST_URL
        export SONAR_TOKEN=$SONAR_LATEST_TOKEN
        ;;
    lts-user)
        export SONAR_HOST_URL=$SONAR_LTS_URL
        export SONAR_TOKEN=$SONAR_LTS_USER_TOKEN
        ;;
    latest-user)
        export SONAR_HOST_URL=$SONAR_LATEST_URL
        export SONAR_TOKEN=$SONAR_LATEST_USER_TOKEN
        ;;
    lts-ce)
        export SONAR_HOST_URL=$SONAR_LTS_CE_URL
        export SONAR_TOKEN=$SONAR_LTS_CE_TOKEN
        ;;
    latest-ce)
        export SONAR_HOST_URL=$SONAR_LATEST_CE_URL
        export SONAR_TOKEN=$SONAR_LATEST_CE_TOKEN
        ;;
    lts-ee)
        export SONAR_HOST_URL=$SONAR_LTS_EE_URL
        export SONAR_TOKEN=$SONAR_LTS_EE_TOKEN
        ;;
    latest-ee)
        export SONAR_HOST_URL=$SONAR_LATEST_EE_URL
        export SONAR_TOKEN=$SONAR_LATEST_EE_TOKEN
        ;;
    -h)
        echo "Usage: source $0 [lts|lts-user|latest|latest-user|lts-ce|latest-ce|lts-ee|latest-ee]"
        exit 1
        ;;
    *)
        echo "ERROR: environment $1 unknown"
        echo "Usage: source $0 [lts|lts-user|latest|latest-user|lts-ce|latest-ce|lts-ee|latest-ee]"
        exit 2
        ;;
esac    