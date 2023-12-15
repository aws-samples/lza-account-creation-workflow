#!/usr/bin/env bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

LOGS_DIR="logs"
[ ! -d "${LOGS_DIR}" ] && mkdir "${LOGS_DIR}"

pylint_threshold="5"
cfnlint_threshold="5"

echo "Linting Python Application Files"
find "app" -name "*.py" | \
  grep -Ev ".venv|.pytest_cach|.tox|botocore|boto3|.aws" | \
  xargs pylint --rcfile .pylintrc > "${LOGS_DIR}/src-lint-output.txt"

app_score=$(sed -n 's/^Your code has been rated at \([-0-9.]*\)\/.*/\1/p' "${LOGS_DIR}/src-lint-output.txt")
echo "*-------------------------------------------------------------*"
echo "          Application Linting Score: ${app_score}            "
echo "*-------------------------------------------------------------*"

if (( $(echo "${app_score} < ${pylint_threshold}" |bc -l) )); then
  echo "Src Python Exceeds Linting Threshold (${pylint_threshold}). Please review code and try again..."
  exit 1
fi

echo "Linting Python Pipeline Files"
find "pipeline" -name "*.py" | \
  grep -Ev ".venv|.pytest_cach|.tox|botocore|boto3|.aws" | \
  xargs pylint --rcfile .pylintrc > "${LOGS_DIR}/src-layers-lint-output.txt"

pipeline_score=$(sed -n 's/^Your code has been rated at \([-0-9.]*\)\/.*/\1/p' "${LOGS_DIR}/src-layers-lint-output.txt")
echo "*-------------------------------------------------------------*"
echo "          Pipeline Linting Score: ${pipeline_score}            "
echo "*-------------------------------------------------------------*"

if (( $(echo "${pipeline_score} < ${pylint_threshold}" |bc -l) )); then
  echo "Src-Layers Python Exceeds Linting Threshold (${pylint_threshold}). Please review code and try again..."
  exit 1
fi
