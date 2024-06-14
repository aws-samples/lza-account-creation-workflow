# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
from constructs import Construct
from app.app_stack import AccountCreationWorkflowStack


class PipelineAppStage(cdk.Stage):
    """
    Class constructor.

    Args:
        scope (Construct): The construct scope. 
        construct_id (str): The construct ID.
        config (dict): The configuration dictionary.
        kwargs: Additional arguments passed to the parent constructor.
    
    Returns:
        None

    This method initializes the construct class by calling the parent constructor 
    and constructing an AccountCreationWorkflowStack with the provided configuration.
    """   

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        AccountCreationWorkflowStack(
            self, config['appInfrastructure']['cloudformation']['stackName'],
            stack_name=config['appInfrastructure']['cloudformation']['stackName'],
            config=config
        )
