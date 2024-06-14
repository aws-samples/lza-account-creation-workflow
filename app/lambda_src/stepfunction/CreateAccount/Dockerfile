# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM public.ecr.aws/lambda/python:3.12.2024.05.24.18

# Set env variables
ARG wd=/var/task/

# Copy file from local machine to image
COPY main.py helper.py git_helper requirements.txt ${wd}

# Install 2.40 version of Git
RUN dnf install -y git && dnf clean all

# Install dependent python packages
WORKDIR ${wd}
RUN python3 -m pip install --no-cache-dir -r requirements.txt -t "${wd}"
RUN python3 -m pip install --no-cache-dir git-remote-codecommit

# Setup Default Healthcheck
HEALTHCHECK NONE

# Command can be overwritten by providing a different command in the template directly.
CMD ["main.lambda_handler"]
