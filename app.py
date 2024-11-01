# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# !/usr/bin/env python3

import os
import yaml
import aws_cdk as cdk
from pipeline.pipeline_stack import PipelineStack


# Get data from config file and convert to dict
CONFIG_FILE_PATH = "./configs/deploy-config.yaml"
with open(CONFIG_FILE_PATH, 'r', encoding="utf-8") as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

app = cdk.App()

PipelineStack(
    app, config['deployInfrastructure']['cloudformation']['stackName'],
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION')
    ),
    config=config
)

app.synth()
