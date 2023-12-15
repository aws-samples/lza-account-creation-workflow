# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
from constructs import Construct
from app.account_creation_workflow_stack import AccountCreationWorkflowStack


class PipelineAppStage(cdk.Stage):
    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        AccountCreationWorkflowStack(
            self, config['appInfrastructure']['cloudformation']['stackName'],
            stack_name=config['appInfrastructure']['cloudformation']['stackName'],
            config=config
        )
