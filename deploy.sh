#!/bin/bash

# Parse CLI args
RESET=0
DEBUG=0

while test $# -gt 0
do
    case "$1" in
        --reset) RESET=1
            ;;
        --debug) DEBUG=1
            ;;
	--help) echo "Usage: ./deploy.sh [--reset] [--debug]"; exit 0
	    ;;
    esac
    shift
done


echo "running deploy with reset=${RESET}, debug=${DEBUG}"

NAMESPACE=$(oc project --short=true)
if [ $? -ne 0 ]; then
    echo "ERROR: unable to get current project -- are you logged in for 'oc'?"
    exit 1
fi

echo "deploying into namespace: ${NAMESPACE}"

# Check if 'iqe-creds' secret exists in namespace
oc get secret iqe-creds
if [ $? -ne 0 ]; then
    echo "ERROR: No secret named 'iqe-creds' -- fix that first"
    exit 1
fi

# Check if 'jira-creds' secret exists in namespace
oc get secret jira-creds
if [ $? -ne 0 ]; then
    echo "ERROR: No secret named 'jira-creds' -- fix that first"
    exit 1
fi


# Import the pull secret if it doesn't exist in the namespace
oc get secret cloudservices-black-box-pull-secret
if [ $? -ne 0 ]; then
    echo "ERROR: No secret named 'cloudservices-black-box-pull-secret' -- fix that first"
    exit 1
fi

# Load the src code as a config map
oc delete configmap black-box-runner
oc create configmap black-box-runner --from-file=./src

# Delete selenium dc's if reset=true
if [ $RESET -eq 1 ]; then
    oc delete all -l app=selenium
fi

# Set log level
if [ $DEBUG -eq 1 ]; then
    LOG_LEVEL="DEBUG"
else
    LOG_LEVEL="INFO"
fi

# Process template, link secrets, import iqe-tests image, and rollotu the black-box-runner
oc process -p LOG_LEVEL="${LOG_LEVEL}" -p NAMESPACE="${NAMESPACE}" -f runner-template.yaml | oc apply -f -
oc process -f selenium-template.yaml | oc apply -f -
oc secrets link default cloudservices-black-box-pull-secret --for=pull
oc secrets link black-box-runner-svc-acct cloudservices-black-box-pull-secret --for=pull
oc import-image iqe-tests:latest --from="quay.io/cloudservices/iqe-tests:latest"
oc tag quay.io/cloudservices/iqe-tests:latest iqe-tests:latest --scheduled=true
REVISION=$(oc rollout latest dc/black-box-runner --output=jsonpath='{.status.latestVersion}')
if [ -z "${REVISION}" ]; then
    oc rollout status dc/black-box-runner
else
    oc rollout status dc/black-box-runner --revision=${REVISION}
fi
