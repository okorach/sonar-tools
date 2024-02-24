#!/bin/bash

case $1 in
    lts)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_U_ADMIN
        ;;
    latest)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST
        export SONAR_TOKEN=$SONAR_TOKEN_LATEST_U_ADMIN
        ;;
    lts-user)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_U_USER
        ;;
    lts-ce-user)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_U_USER
        ;;
    latest-user)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST
        export SONAR_TOKEN=$SONAR_TOKEN_LATEST_U_USER
        ;;
    latest-ce-user)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST
        export SONAR_TOKEN=$SONAR_TOKEN_LATEST_U_USER
        ;;
    lts-ce)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS_CE
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_CE
        ;;
    latest-ce)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST_CE
        export SONAR_TOKEN=$SONAR_LATEST_CE_TOKEN
        ;;
    lts-ee)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS_EE
        export SONAR_TOKEN=$SONAR_LTS_EE_TOKEN
        ;;
    latest-ee)
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST_EE
        export SONAR_TOKEN=$SONAR_TOKEN_LATEST_EE
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