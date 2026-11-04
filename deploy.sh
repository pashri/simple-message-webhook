#!/usr/bin/env bash

# This script should make it easy to deploy an AWS stack via SAM.
#
# Deploy (default):
#     AWS_PROFILE=<profile> ./deploy.sh
#
# Deploy to a named samconfig environment:
#     AWS_PROFILE=<profile> ./deploy.sh -c development
#
# Build only (no deploy, no keys created):
#     AWS_PROFILE=<profile> ./deploy.sh --no-deploy
#
# Before deploying, any missing write or read key is created in SSM and
# printed once. Copy it then; it is not shown again.

# Fail if anything exits with error code
set -euo pipefail
IFS=$'\n\t'
shopt -s failglob

# Help function
helpfunction() {
    echo ""
    echo "Usage: $0 [-c CONFIG_ENV] [-n|--no-deploy]"
    echo -e "\t-c (optional) Config environment"
    echo -e "\t-n, --no-deploy (optional) Validate and build only"
    exit 1
}

# Parse arguments
CONFIG_ENV="default"
NO_DEPLOY=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c) [[ $# -ge 2 ]] || helpfunction; CONFIG_ENV="$2"; shift 2 ;;
        -n|--no-deploy) NO_DEPLOY=true; shift ;;
        *) helpfunction ;;
    esac
done

# Set other parameters
export REGION="ap-southeast-2"  # Must match the region in samconfig.toml.
WRITE_KEY_PARAMETER="/simple-message-webhook/write-key"
READ_KEY_PARAMETER="/simple-message-webhook/read-key"

# Validate, export dependencies, build, remove exports, and deploy
echo "Validate, export dependencies, build, and deploy"
sam validate --lint --region="${REGION}"
uv export --no-dev --no-emit-project --no-color \
  --format requirements-txt -o src/requirements.txt
sam build
rm src/requirements.txt

# Exit early if --no-deploy flag is set
if [ "$NO_DEPLOY" = true ]; then
    echo "Build complete. Skipping deployment (--no-deploy flag set)."
    exit 0
fi

# Create any missing key. put-parameter without --overwrite never
# replaces an existing key.
for name in "${WRITE_KEY_PARAMETER}" "${READ_KEY_PARAMETER}"; do
    key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
    # --value= keeps a key starting with "-" from reading as a flag.
    if output="$(aws ssm put-parameter --region "${REGION}" \
        --name="${name}" --type SecureString --value="${key}" 2>&1)"; then
        echo "Created ${name}: ${key}"
        echo "Copy this key now. It is not shown again."
    elif grep -q ParameterAlreadyExists <<< "${output}"; then
        echo "Using existing ${name}"
    else
        echo "${output}" >&2
        exit 1
    fi
done

sam deploy --config-env="${CONFIG_ENV}" --resolve-s3 \
  --no-confirm-changeset --no-fail-on-empty-changeset \
  --parameter-overrides \
  "WriteKeyParameterName=${WRITE_KEY_PARAMETER}" \
  "ReadKeyParameterName=${READ_KEY_PARAMETER}"

# If there are any post-deployment steps, they can be added below.
