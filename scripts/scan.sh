#!/usr/bin/env bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

LOGS_DIR="logs"
[ ! -d "${LOGS_DIR}" ] && mkdir "${LOGS_DIR}"

echo "Scanning Python Source for Vulnerabilities"
bandit --recursive src -f json > "${LOGS_DIR}/src-bandit-output.json"
src_high=$(jq -r '.metrics._totals."SEVERITY.HIGH"' "${LOGS_DIR}/src-bandit-output.json" | awk '{sum+=$0} END{print sum}')
src_med=$(jq -r '.metrics._totals."SEVERITY.MEDIUM"' "${LOGS_DIR}/src-bandit-output.json" | awk '{sum+=$0} END{print sum}')
src_low=$(jq -r '.metrics._totals."SEVERITY.LOW"' "${LOGS_DIR}/src-bandit-output.json" | awk '{sum+=$0} END{print sum}')
echo "*-----------------------------------------------------------------------*"
echo "    Bandit Source - High:${src_high} Medium:${src_med} Low:${src_low}"
echo "*-----------------------------------------------------------------------*"

echo ""
echo "Scanning Python Layer for Vulnerabilities"
bandit --recursive src-layers -f json > "${LOGS_DIR}/src-layer-bandit-output.json"
src_layer_high=$(jq -r '.metrics._totals."SEVERITY.HIGH"' "${LOGS_DIR}/src-layer-bandit-output.json" | awk '{sum+=$0} END{print sum}')
src_layer_med=$(jq -r '.metrics._totals."SEVERITY.MEDIUM"' "${LOGS_DIR}/src-layer-bandit-output.json" | awk '{sum+=$0} END{print sum}')
src_layer_low=$(jq -r '.metrics._totals."SEVERITY.LOW"' "${LOGS_DIR}/src-layer-bandit-output.json" | awk '{sum+=$0} END{print sum}')
echo "*-----------------------------------------------------------------------*"
echo "     Bandit Layer - High:${src_layer_high} Medium:${src_layer_med} Low:${src_layer_low}"
echo "*-----------------------------------------------------------------------*"

echo ""
echo "Scanning Python Scripts for Vulnerabilities"
bandit --recursive scripts -f json > "${LOGS_DIR}/scripts-bandit-output.json"
src_layer_high=$(jq -r '.metrics._totals."SEVERITY.HIGH"' "${LOGS_DIR}/scripts-bandit-output.json" | awk '{sum+=$0} END{print sum}')
src_layer_med=$(jq -r '.metrics._totals."SEVERITY.MEDIUM"' "${LOGS_DIR}/scripts-bandit-output.json" | awk '{sum+=$0} END{print sum}')
src_layer_low=$(jq -r '.metrics._totals."SEVERITY.LOW"' "${LOGS_DIR}/scripts-bandit-output.json" | awk '{sum+=$0} END{print sum}')
echo "*-----------------------------------------------------------------------*"
echo "     Bandit Scripts - High:${src_layer_high} Medium:${src_layer_med} Low:${src_layer_low}"
echo "*-----------------------------------------------------------------------*"


echo ""
echo "Scanning Python depend for Vulnerabilities"
safety check | tee -a "${LOGS_DIR}/safety-output.txt"
