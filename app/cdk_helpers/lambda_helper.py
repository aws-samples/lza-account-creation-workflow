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
    aws_iam as iam,
    aws_kms as kms
)


def create_lambda_layer(scope, layer_name: str, description: str = None) -> lambda_.ILayerVersion:
    """
    Creates an AWS Lambda layer.

    Args:
        scope (Construct): The CDK construct scope in which to define this layer.
        layer_name: The name of the layer.
        description: An optional description of the layer.

    Returns: 
        lambda_.ILayerVersion: The Lambda layer version object.
    """
    layer = lambda_.LayerVersion(
        scope, f"rLambdaLayer{layer_name.title().replace('_','')}",
        layer_version_name=layer_name,
        removal_policy=RemovalPolicy.RETAIN,
        code=lambda_.Code.from_asset(
            path=path.join(Path(__file__).parents[0], f"../lambda_layer/{layer_name}"),
            bundling=BundlingOptions(
                image=DockerImage.from_registry("public.ecr.aws/sam/build-python3.12:1.117.0-20240521231233"),
                command=[
                    'bash',
                    '-c',
                    'cp -au . /asset-output && pip3 install -r requirements.txt -t /asset-output/python'
                ],
                output_type=BundlingOutput.AUTO_DISCOVER
            ),
        ),
        compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
        description=description
    )

    return layer


def create_lambda_function(scope, function_name: str, function_path: str, retention_role: iam.IRole,
                           key: kms.IKey, timeout: int = 120, layers: list = None, env_vars: dict = None,
                           description: str = 'Lambada') -> lambda_.IFunction:
    """
    Creates an AWS Lambda function.

    Args:
        scope (Construct): The CDK construct scope in which to define this function. 
        function_name (str): The name of the Lambda function.
        function_path (str): The path to the Lambda function code.
        retention_role (): The IAM role for log retention. 
        key (kms.IKey): The KMS key to encrypt environment variables.
        timeout (int): The function timeout in seconds.
        layers (list): Optional list of Lambda layers.
        env_vars (dict): Optional dict of environment variables.
        description (str): An optional description.

    Returns:
        lambda_.IFunction: The Lambda function object.
    """
    i_function = lambda_.Function(
        scope, f"rLambdaFunction{function_name}",
        function_name=function_name,
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="main.lambda_handler",
        description=description,
        code=lambda_.Code.from_asset(
            path=path.join(Path(__file__).parents[0], f"../lambda_src/{function_path}/{function_name}"),
            bundling=BundlingOptions(
                image=DockerImage.from_registry("public.ecr.aws/sam/build-python3.12:1.117.0-20240521231233"),
                command=[
                    'bash',
                    '-c',
                    'pip3 install -r requirements.txt -t /asset-output && cp -au . /asset-output',
                ],
                output_type=BundlingOutput.AUTO_DISCOVER
            ),
        ),
        environment_encryption=key,
        timeout=Duration.seconds(timeout)
    )

    logs.LogRetention(
        scope, f"rLogRetention{function_name}",
        log_group_name=f"/aws/lambda/{function_name}",
        retention=logs.RetentionDays.TWO_MONTHS,
        removal_policy=RemovalPolicy.DESTROY,
        role=retention_role
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

    return i_function


def create_lambda_docker_function(scope, function_name: str, function_path: str, retention_role: iam.IRole,
                                  key: kms.IKey, timeout: int = 120, env_vars: dict = None,
                                  description: str = 'Lambada') -> lambda_.IFunction:
    """
    Creates an AWS Lambda function using a Docker container.

    Args:
        scope (Construct): The CDK construct scope in which to define this function.
        function_name (str): The name of the Lambda function.
        function_path (str): The path to the Lambda function code.
        retention_role (): The IAM role for log retention. 
        key (kms.IKey): The KMS key to encrypt environment variables.
        timeout (int): The function timeout in seconds.
        env_vars (dict): Optional dict of environment variables.
        description (str): An optional description.

    Returns:
        lambda_.IFunction: The Lambda function object.
    """    
    i_function = lambda_.DockerImageFunction(
        scope, f"rLambdaFunction{function_name}",
        function_name=function_name,
        description=description,
        code=lambda_.DockerImageCode.from_image_asset(path.join(
            Path(__file__).parents[0], f"../lambda_src/{function_path}/{function_name}"
        )),
        # log_retention=logs.RetentionDays.TWO_MONTHS,
        # log_retention_role=retention_role,
        environment_encryption=key,
        timeout=Duration.seconds(timeout)
    )

    logs.LogRetention(
        scope, f"rLogRetention{function_name}",
        log_group_name=f"/aws/lambda/{function_name}",
        retention=logs.RetentionDays.TWO_MONTHS,
        removal_policy=RemovalPolicy.DESTROY,
        role=retention_role
    )

    if env_vars:
        for env_key, env_value in env_vars.items():
            i_function.add_environment(
                key=env_key,
                value=env_value
            )

    return i_function
