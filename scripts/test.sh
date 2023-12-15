#!/usr/bin/env bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

set -eo pipefail

echo "#---------------------------------------------------#"
echo "#                  Running Tests                     "
echo "#---------------------------------------------------#"

for test in $(find . -name tox.ini); do
  #pyenv local 3.6.9 3.7.4 3.8.1  # Can do multiple versions like this but need to make sure they are installed
  tox -c "${test}"
done
