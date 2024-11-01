# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_logs as logs
)
from app.cdk_helpers.lambda_helper import create_lambda_function


def setup_api_gateway(scope, config: dict, boto3_layer: lambda_.ILayerVersion, retention_role: iam.IRole,
                      lambda_key: kms.IKey):
    """
    Set up API Gateway for the account creation workflow.

    Parameters:
        scope (Construct): The construct scope.
        config (dict): The configuration dictionary. 
        boto3_layer (ILayerVersion): The Lambda layer for AWS SDK.
        retention_role (IRole): The role for Lambda function logs retention.
        lambda_key (IKey): The KMS key for encrypting Lambda function code.
    
    Returns:
        None

    This function creates the necessary API Gateway resources like REST API, 
    resources, methods etc to support the account creation workflow. It also 
    sets up Lambda functions and integrates them with API Gateway.
    """
    # Set variables
    account_id = Stack.of(scope).account
    region = Stack.of(scope).region
    partition = Stack.of(scope).partition

    # Create Log Group for API Gateway
    log_group = logs.LogGroup(
        scope, "rApiGatewayCreateAccountLogGroup",
        log_group_name=f"/aws/apigateway/{config['appInfrastructure']['apiGatewayName']}",
        retention=logs.RetentionDays.TWO_MONTHS,
        removal_policy=RemovalPolicy.DESTROY
    )

    # Create an API Gateway client
    api_gateway = boto3.client('apigateway')

    # Get the API Gateway account information
    account_info = api_gateway.get_account()

    # API Gateway Configurations
    api_deploy_options=apigw.StageOptions(
        access_log_destination=apigw.LogGroupLogDestination(log_group),
        access_log_format=apigw.AccessLogFormat.clf(),
        logging_level=apigw.MethodLoggingLevel.INFO,
        data_trace_enabled=True
    )

    api_endpoint_configuration=apigw.EndpointConfiguration(
        types=[apigw.EndpointType.EDGE]
    )
 
    api_iam_policy = iam.PolicyDocument(
        statements=[
            iam.PolicyStatement(
                actions=["execute-api:Invoke"],
                effect=iam.Effect.ALLOW,
                principals=[iam.AccountRootPrincipal()],
                resources=[
                    f"arn:{partition}:execute-api:{region}:{account_id}:*/prod/GET/check_name",
                    f"arn:{partition}:execute-api:{region}:{account_id}:*/prod/POST/execute",
                    f"arn:{partition}:execute-api:{region}:{account_id}:*/prod/GET/get_execution_status"
                ]
            )
        ]
    )

    # Check if the CloudWatch log role ARN is specified, if not create API Gateway role
    #  and associate it to the API Gateway
    if 'cloudwatchRoleArn' not in account_info:
        api = apigw.RestApi(
            scope, "rApiGatewayCreateAccount",
            rest_api_name=config['appInfrastructure']['apiGatewayName'],
            description="RestAPI to intiate and check status of the Account Creation Workflow.",
            cloud_watch_role=True,
            deploy_options=api_deploy_options,
            endpoint_configuration=api_endpoint_configuration,
            policy=api_iam_policy
        )
    else:
        api = apigw.RestApi(
            scope, "rApiGatewayCreateAccount",
            rest_api_name=config['appInfrastructure']['apiGatewayName'],
            description="RestAPI to intiate and check status of the Account Creation Workflow.",
            deploy_options=api_deploy_options,
            endpoint_configuration=api_endpoint_configuration,
            policy=api_iam_policy
        )

    CfnOutput(scope, "oApiGatewayCreateAccountEndpoint", value=api.url)

    # Check Name Availability
    i_name_available = create_lambda_function(
        scope=scope,
        function_name='NameAvailability',
        function_path='api',
        description='This function will be used to check to see if the AWS Account Name is available to use.',
        layers=[boto3_layer],
        timeout=60,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel']
        }
    )
    i_name_available.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "organizations:DescribeOrganization",
            "organizations:DescribeAccount",
            "organizations:ListAccounts"
        ],
        resources=["*"]
    ))

    api_check_name = api.root.add_resource("check_name")
    api_check_name.add_method(
        http_method="GET",
        integration=apigw.LambdaIntegration(i_name_available),
        method_responses=[{"statusCode": "200"}],
        authorization_type=apigw.AuthorizationType.IAM
    )

    # Run StepFunction
    i_run_stepfunction = create_lambda_function(
        scope=scope,
        function_name='RunStepFunction',
        function_path='api',
        description='This function will be used to kick off the Account Creation StepFunction',
        layers=[boto3_layer],
        timeout=60,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "STEPFUNCTION_NAME": config['appInfrastructure']['stepFunctionName']
        }
    )
    i_run_stepfunction.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "states:ListExecutions",
            "states:DescribeExecution",
            "states:DescribeStateMachine",
            "states:StartExecution"
        ],
        resources=[f"arn:{partition}:states:{region}:{account_id}:stateMachine:{config['appInfrastructure']['stepFunctionName']}"]
    ))
 
    api_model = api.add_model(
        "rApiGatewayModel",
        content_type="application/json",
        model_name="AccountCreationRequest",
        schema=apigw.JsonSchema(
            schema=apigw.JsonSchemaVersion.DRAFT4,
            title="AccountCreationRequest",
            type=apigw.JsonSchemaType.OBJECT,
            required=["account_name", "support_dl", "managed_org_unit"],
            properties={
                # Required
                "account_name": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                "support_dl": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                "managed_org_unit": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                # Optional
                "ad_integration": apigw.JsonSchema(type=apigw.JsonSchemaType.ARRAY),
                "account_email": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                "force_update": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                "bypass_creation": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                "account_tags": apigw.JsonSchema(type=apigw.JsonSchemaType.ARRAY)
            }
        )
    )

    api_validator = api.add_request_validator(
       "rApiGatewayRequestValidator",
       request_validator_name="AccountCreationRequestValidator",
       validate_request_body=True
    )

    # Sets up /execute to be the endpoint
    execute = api.root.add_resource("execute")
    execute.add_method(
        http_method="POST",
        integration=apigw.LambdaIntegration(i_run_stepfunction),
        method_responses=[{"statusCode": "200"}],
        request_models={'application/json': api_model},
        request_validator=api_validator,
        authorization_type=apigw.AuthorizationType.IAM
    )

    # Get Create Account Status
    i_get_exec_status = create_lambda_function(
        scope=scope,
        function_name='GetExecutionStatus',
        function_path='api',
        description='This function will be used to check the status of the Account Creation.',
        layers=[boto3_layer],
        timeout=60,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "SF_EXECUTION_ARN_BASE": f"arn:{partition}:states:{region}:{account_id}:execution:{config['appInfrastructure']['stepFunctionName']}"
        }
    )
    i_get_exec_status.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "states:ListExecutions",
            "states:DescribeExecution",
            "states:DescribeStateMachine",
            "states:StartExecution",
            "states:GetExecutionHistory"
        ],
        resources=[
            f"arn:{partition}:states:{region}:{account_id}:stateMachine:{config['appInfrastructure']['stepFunctionName']}",
            f"arn:{partition}:states:{region}:{account_id}:execution:{config['appInfrastructure']['stepFunctionName']}:*"
        ]
    ))

    execute = api.root.add_resource("get_execution_status")
    execute.add_method(
        http_method="GET",
        integration=apigw.LambdaIntegration(i_get_exec_status),
        method_responses=[{"statusCode": "200"}],
        authorization_type=apigw.AuthorizationType.IAM
    )

    # If you would like to deploy a user with credentials to access API Gateway, add a user name to the config file
    api_user_name = config['appInfrastructure'].get("apiGatewayUser")
    if api_user_name:
        i_iam_group = iam.Group(
            scope, "rApiGatewayGroup",
            managed_policies=[iam.ManagedPolicy(
                scope, "rApiGatewayGroupManagedPolicy",
                document=iam.PolicyDocument(
                    statements=[iam.PolicyStatement(
                        actions=[
                            "execute-api:Invoke"
                        ],
                        resources=[
                            f"arn:{partition}:execute-api:{region}:{account_id}:{api.rest_api_id}/prod/GET/check_name",
                            f"arn:{partition}:execute-api:{region}:{account_id}:{api.rest_api_id}/prod/POST/execute",
                            f"arn:{partition}:execute-api:{region}:{account_id}:{api.rest_api_id}/prod/GET/get_execution_status"
                        ]
                    )]
                )
            )]
        )

        iam.User(
            scope, "rApiGatewayUser",
            user_name=api_user_name,
            groups=[i_iam_group]
        )
