# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_logs as logs,
    Duration
)


def create_stepfunction(scope, sfn_name: str, sfn_data: dict, sfn_def_file: str) -> sfn.StateMachine:
    """
    Creates an AWS Step Functions state machine.

    Args:
        scope (Construct): The CDK construct scope in which to define this state machine.
        sfn_name (str): The name of the state machine.
        sfn_data (dict): Data substitutions for the state machine definition.
        sfn_def_file (str): Path to the state machine definition file.

    Returns:
        sfn.StateMachine: The created state machine object.
    """
    log_group = logs.LogGroup(scope, f"rLogGroup{sfn_name.title().replace('/','')}")

    stepfunction = sfn.StateMachine(
        scope, f"rStateMachine{sfn_name}",
        state_machine_name=sfn_name,
        definition_body=sfn.DefinitionBody.from_file(sfn_def_file),
        definition_substitutions=sfn_data,
        timeout=Duration.minutes(180),  # 3 hours
        tracing_enabled=True,
        logs=sfn.LogOptions(
            destination=log_group,
            level=sfn.LogLevel.ALL
        )
    )

    return stepfunction
