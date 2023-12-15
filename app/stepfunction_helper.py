# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_logs as logs,
    Duration
)


def create_stepfunction(scope, sfn_name: str, sfn_data: dict, sfn_def_file: str) -> sfn.StateMachine:
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
