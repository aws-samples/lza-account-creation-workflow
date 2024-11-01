# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as lambda_
)
from app.cdk_helpers.lambda_helper import create_lambda_layer, create_lambda_function


def setup_azure_ad_integration(scope, config: dict, boto3_layer: lambda_.ILayerVersion, retention_role: iam.IRole, 
                      lambda_key: kms.IKey) -> dict:
    """
    Sets up Lambda functions for Azure AD integration.

    Initializes Lambda functions for syncing AD groups, validating 
    group sync to SSO, and attaching permission sets.

    Args:
        scope: Construct scope
        config: Configuration dictionary
        boto3_layer: Boto3 layer
        retention_role: Log retention role 
        lambda_key: KMS key

    Returns:  
        dict: Map of function names to ARNs
    """    
    account_id = Stack.of(scope).account
    region = Stack.of(scope).region

    _sfn_lambdas = {}

    i_identity_center_helper_layer = create_lambda_layer(
        scope=scope, layer_name='identity_center_helper',
        description='Layer to hold common AWS Identity Center code.'
    )

    # Integration usage
    use_graph_api_sync = config['appInfrastructure'].get('useGraphApiSync', False)

    if use_graph_api_sync:
        # SYNC AZURE AD GROUP
        i_sync_ad_group_fn = create_lambda_function(
            scope=scope,
            function_name='AzureADGroupSync',
            function_path='stepfunction',
            description='This function will create a new Azure AD group in the specified tenant',
            timeout=900,
            retention_role=retention_role,
            key=lambda_key,
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "GRAPH_API_SECRET_NAME": config['appInfrastructure']['graphApiSecretName']
            }
        )
        i_sync_ad_group_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "secretsmanager:GetResourcePolicy",
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
                "secretsmanager:ListSecretVersionIds"
            ],
            resources=[f"arn:aws:secretsmanager:{region}:{account_id}:secret:{config['appInfrastructure']['graphApiSecretName']}-*"]
        ))
        i_sync_ad_group_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "secretsmanager:ListSecrets"
            ],
            resources=["*"]
        ))
        _sfn_lambdas.update({"AzureADGroupSyncFunctionArn": i_sync_ad_group_fn.function_arn})

    # VALIDATE AD GROUP SYNC TO SSO
    i_valid_ad_group_sync_fn = create_lambda_function(
        scope=scope,
        function_name='ValidateADGroupSyncToSSO',
        function_path='stepfunction',
        description='This function will check that the AD group exists in Identity Center (SSO)',
        layers=[
            boto3_layer,
            i_identity_center_helper_layer
        ],
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel']
        }
    )
    i_valid_ad_group_sync_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "sso:ListInstances",
            "identitystore:ListGroups"
        ],
        resources=["*"]
    ))
    _sfn_lambdas.update({"ValidateADGroupSyncToSSOFunctionArn": i_valid_ad_group_sync_fn.function_arn})

    # ATTACH PERMISSION SET
    i_attach_permission_set_fn = create_lambda_function(
        scope=scope,
        function_name='AttachPermissionSet',
        function_path='stepfunction',
        description='This function will attach a given permission set name to a given group name',
        layers=[
            boto3_layer,
            i_identity_center_helper_layer
        ],
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel']
        }
    )
    i_attach_permission_set_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "sso:ListInstances",
            "sso:CreateAccountAssignment",
            "identitystore:ListGroups",
            "sso:ListPermissionSets",
            "sso:DescribePermissionSet"
        ],
        resources=["*"]
    ))
    _sfn_lambdas.update({"AttachPermissionSetFunctionArn": i_attach_permission_set_fn.function_arn})

    return _sfn_lambdas
