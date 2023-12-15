# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from os import path
from pathlib import Path
from aws_cdk import (
    Duration,
    RemovalPolicy,
    BundlingOptions,
    DockerImage,
    BundlingOutput,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_iam as iam
)
from cdk_nag import NagSuppressions


def create_lambda_layer(scope, layer_name: str, description: str = None) -> lambda_.ILayerVersion:
    """Creates Lambda Function Layer"""
    layer = lambda_.LayerVersion(
        scope, f"rLambdaLayer{layer_name.title().replace('_','')}",
        layer_version_name=layer_name,
        removal_policy=RemovalPolicy.RETAIN,
        code=lambda_.Code.from_asset(
            path=path.join(Path(__file__).parents[0], f"lambda_layer/{layer_name}"),
            bundling=BundlingOptions(
                image=DockerImage.from_registry("amazon/aws-sam-cli-build-image-python3.9"),
                command=[
                    'bash',
                    '-c',
                    'cp -au . /asset-output && pip install -r requirements.txt -t /asset-output/python',
                ],
                output_type=BundlingOutput.AUTO_DISCOVER
            ),
        ),
        compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
        description=description
    )

    return layer


def create_lambda_function(scope, function_name: str, function_path: str, retention_role: iam.IRole, 
                           timeout: int = 120, layers: list = None, env_vars: dict = None, 
                           description: str = 'Lambada') -> lambda_.IFunction:
    """Creates Lambda Function"""
    i_function = lambda_.Function(
        scope, f"rLambdaFunction{function_name}",
        function_name=function_name,
        runtime=lambda_.Runtime.PYTHON_3_9,
        handler="main.lambda_handler",
        description=description,
        code=lambda_.Code.from_asset(
            path=path.join(Path(__file__).parents[0], f"lambda_src/{function_path}/{function_name}"),
            bundling=BundlingOptions(
                image=DockerImage.from_registry("amazon/aws-sam-cli-build-image-python3.9"),
                command=[
                    'bash',
                    '-c',
                    'pip install -r requirements.txt -t /asset-output && cp -au . /asset-output',
                ],
                output_type=BundlingOutput.AUTO_DISCOVER
            ),
        ),
        log_retention=logs.RetentionDays.TWO_MONTHS,
        log_retention_role=retention_role,
        timeout=Duration.seconds(timeout)
    )

    if env_vars:
        for env_key, env_value in env_vars.items():
            i_function.add_environment(
                key=env_key,
                value=env_value
            )

    if layers:
        for layer in layers:
            i_function.add_layers(layer)

    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/account-creation-workflow-pipeline/Deploy-Application/account-creation-workflow-application/rLambdaFunction{function_name}/Resource",
        [{
            "id": 'AwsSolutions-L1',
            "reason": 'The non-container Lambda function is not configured to use the latest runtime version.'
        }]
    )

    return i_function


def create_lambda_docker_function(scope, function_name: str, function_path: str, retention_role: iam.IRole, 
                                  timeout: int = 120, env_vars: dict = None, description: str = 'Lambada', 
                                  ) -> lambda_.IFunction:
    i_function = lambda_.DockerImageFunction(
        scope, f"rLambdaFunction{function_name}",
        function_name=function_name,
        description=description,
        code=lambda_.DockerImageCode.from_image_asset(path.join(Path(__file__).parents[0], f"lambda_src/{function_path}/{function_name}")),
        log_retention=logs.RetentionDays.TWO_MONTHS,
        log_retention_role=retention_role,
        timeout=Duration.seconds(timeout)
    )

    if env_vars:
        for env_key, env_value in env_vars.items():
            i_function.add_environment(
                key=env_key,
                value=env_value
            )

    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/account-creation-workflow-pipeline/Deploy-Application/account-creation-workflow-application/rLambdaFunction{function_name}/ServiceRole/Resource",
        [{
            "id": 'AwsSolutions-IAM4',
            "reason": 'The IAM user, role, or group uses AWS managed policies.'
        }]
    )

    return i_function
