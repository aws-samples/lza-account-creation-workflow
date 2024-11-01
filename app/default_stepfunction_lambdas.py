# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_kms as kms
)
from app.cdk_helpers.lambda_helper import create_lambda_function, create_lambda_docker_function


def setup_default_stepfunction_lambdas(scope, config: dict, boto3_layer: lambda_.ILayerVersion,
                                       account_creation_layer: lambda_.ILayerVersion, retention_role: iam.IRole,
                                       lambda_key: kms.IKey, account_creation_failure_sns_arn,
                                       account_creation_email_ses_identity):
    """
    Sets up default Lambda functions for a Step Functions workflow.

    Initializes Lambda functions for checking processes, creating 
    accounts, getting account status, and more. Returns a dictionary
    mapping function names to ARNs.

    Args:
        scope: Construct scope
        config: Configuration dictionary 
        boto3_layer: Boto3 layer
        account_creation_layer: Helper layer
        retention_role: Log retention role
        lambda_key: KMS key

    Returns:  
        dict: Map of function names to ARNs
    """
    account_id = Stack.of(scope).account
    region = Stack.of(scope).region
    partition = Stack.of(scope).partition

    _sfn_lambdas = {}

    # CHECK FOR RUNNING PROCESSES
    i_check_for_running_proc_fn = create_lambda_function(
        scope=scope,
        function_name='CheckForRunningProcesses',
        function_path='stepfunction',
        description='This function will ensure there are no running processes before proceeding to create an AWS Account.',
        layers=[boto3_layer],
        timeout=120,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LZA_PIPELINE_NAME": config['appInfrastructure'].get('lzaPipelineName', ""),
            "ACCOUNT_DECOMMISSION_PROJECT_NAME": config['appInfrastructure'].get('accountDecommissionProject', "")
        }
    )
    i_check_for_running_proc_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "codebuild:ListBuildsForProject",
            "codebuild:BatchGetBuilds"
        ],
        resources=[f"arn:{partition}:codebuild:{region}:{account_id}:project/{config['appInfrastructure']['accountDecommissionProject']}"]
    ))
    i_check_for_running_proc_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "codepipeline:GetPipeline",
            "codepipeline:GetPipelineState",
            "codepipeline:GetPipelineExecution",
            "codepipeline:ListPipelines",
            "codepipeline:ListPipelineExecutions"
        ],
        resources=[f"arn:{partition}:codepipeline:{region}:{account_id}:{config['appInfrastructure']['lzaPipelineName']}"]
    ))
    _sfn_lambdas.update({"CheckForRunningProcessesFunctionArn": i_check_for_running_proc_fn.function_arn})

    # CREATE ACCOUNT
    lza_pipeline_source = config['appInfrastructure'].get('lzaPipelineSource', 'S3')
    if lza_pipeline_source == 'S3':
        i_create_account_fn = create_lambda_function(
            scope=scope,
            function_name='CreateAccountS3',
            function_path='stepfunction',
            description='This function will update the LZA account-config.yaml which will create an AWS Service ' \
                'Catalog Provisioned Product for Account Vending Machine which creates an account within Control Tower.',
            timeout=900,
            retention_role=retention_role,
            key=lambda_key,
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "SC_CT_PRODUCT_NAME": "AWS Control Tower Account Factory",
                "LZA_CONFIG_REPO_NAME": config['appInfrastructure']['lzaRepositoryName'],
                "ROOT_EMAIL_PREFIX": config['appInfrastructure']['rootEmailPrefix'],
                "ROOT_EMAIL_DOMAIN": config['appInfrastructure']['rootEmailDomain']
            }
        )
        i_create_account_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "s3:ListBucket",
                "s3:GetObject",
                "s3:PutObject",
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:GenerateDataKey"
            ],
            resources=["*"]
        ))

    # Work In Progress
    elif lza_pipeline_source == 'GitHub':
        i_create_account_fn = create_lambda_function(
            scope=scope,
            function_name='CreateAccountGitHub',
            function_path='stepfunction',
            description='This function will update the LZA account-config.yaml which will create an AWS Service ' \
                'Catalog Provisioned Product for Account Vending Machine which creates an account within Control Tower.',
            timeout=900,
            retention_role=retention_role,
            key=lambda_key,
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "SC_CT_PRODUCT_NAME": "AWS Control Tower Account Factory",
                "LZA_CONFIG_REPO_NAME": config['appInfrastructure']['lzaRepositoryName'],
                "ROOT_EMAIL_PREFIX": config['appInfrastructure']['rootEmailPrefix'],
                "ROOT_EMAIL_DOMAIN": config['appInfrastructure']['rootEmailDomain']
            }
        )

    # Archived
    elif lza_pipeline_source == 'CodeCommit':
        i_create_account_fn = create_lambda_docker_function(
            scope=scope,
            function_name='CreateAccountCodeCommit',
            function_path='stepfunction',
            description='This function will update the LZA account-config.yaml which will create an AWS Service ' \
                'Catalog Provisioned Product for Account Vending Machine which creates an account within Control Tower.',
            timeout=900,
            retention_role=retention_role,
            key=lambda_key,
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "SC_CT_PRODUCT_NAME": "AWS Control Tower Account Factory",
                "LZA_CONFIG_REPO_NAME": config['appInfrastructure']['lzaRepositoryName'],
                "ROOT_EMAIL_PREFIX": config['appInfrastructure']['rootEmailPrefix'],
                "ROOT_EMAIL_DOMAIN": config['appInfrastructure']['rootEmailDomain']
            }
        )
        i_create_account_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "codecommit:GitPull",
                "codecommit:GitPush",
                "codecommit:GetBranch",
                "codecommit:ListBranches",
                "codecommit:ListPullRequests",
                "codecommit:ListTagsForResource",
                "codecommit:ListRepositories",
                "codecommit:CreateBranch",
                "codecommit:MergeBranchesByFastForward",
                "codecommit:MergeBranchesBySquash",
                "codecommit:MergeBranchesByThreeWay",
                "codecommit:GetMergeCommit",
                "codecommit:GetMergeConflicts",
                "codecommit:GetMergeOptions",
                "codecommit:BatchDescribeMergeConflicts",
                "codecommit:DescribeMergeConflicts",
                "codecommit:DescribePullRequestEvents",
                "codecommit:CreatePullRequest",
                "codecommit:CreateCommit",
                "codecommit:GetCommit",
                "codecommit:BatchGetCommits",
                "codecommit:GetDifferences",
                "codecommit:GetReferences",
                "codecommit:GetTree",
                "codecommit:GetRepository",
                "codecommit:TagResource",
                "codecommit:UntagResource",
                "codecommit:UploadArchive",
                "codecommit:GetUploadArchiveStatus"
            ],
            resources=[f"arn:{partition}:codecommit:{region}:{account_id}:{config['appInfrastructure']['lzaRepositoryName']}"]
        ))

    i_create_account_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "codepipeline:StartPipelineExecution",
            "codepipeline:GetPipeline",
            "codepipeline:GetPipelineState",
            "codepipeline:GetPipelineExecution",
            "codepipeline:ListPipelines",
            "codepipeline:ListPipelineExecutions"
        ],
        resources=[f"arn:{partition}:codepipeline:{region}:{account_id}:{config['appInfrastructure']['lzaPipelineName']}"]
    ))
    _sfn_lambdas.update({"CreateAccountFunctionArn": i_create_account_fn.function_arn})

    # GET ACCOUNT STATUS
    i_get_account_status_fn = create_lambda_function(
        scope=scope,
        function_name='GetAccountStatus',
        function_path='stepfunction',
        description='This function will check the account creation status.',
        layers=[account_creation_layer],
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "SC_CT_PRODUCT_NAME": "AWS Control Tower Account Factory",
            "LZA_CONFIG_REPO_NAME": config['appInfrastructure']['lzaRepositoryName'],
            "ROOT_EMAIL_PREFIX": config['appInfrastructure']['rootEmailPrefix'],
            "ROOT_EMAIL_DOMAIN": config['appInfrastructure']['rootEmailDomain']
        }
    )
    i_get_account_status_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "codebuild:BatchGetBuilds",
            "servicecatalog:ScanProvisionedProducts",
            "servicecatalog:SearchProducts",
            "servicecatalog:ListPortfolios",
            "servicecatalog:ListTagsForResource",
            "servicecatalog:ListApplications",
            "servicecatalog:DescribePortfolioShares",
            "servicecatalog:DescribeProduct",
            "servicecatalog:DescribePortfolio",
            "servicecatalog:DescribeProvisionedProduct",
            "servicecatalog:DescribeProvisioningArtifact",
            "servicecatalog:SearchProvisionedProducts"
        ],
        resources=["*"]
    ))
    i_get_account_status_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "codepipeline:GetPipeline",
            "codepipeline:GetPipelineState",
            "codepipeline:GetPipelineExecution",
            "codepipeline:ListPipelines",
            "codepipeline:ListPipelineExecutions",
            "codepipeline:ListActionExecutions"
        ],
        resources=[f"arn:{partition}:codepipeline:{region}:{account_id}:{config['appInfrastructure']['lzaPipelineName']}"]
    ))
    _sfn_lambdas.update({"GetAccountStatusFunctionArn": i_get_account_status_fn.function_arn})

    # NagSuppressions.add_resource_suppressions_by_path(
    #     scope, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionGetAccountStatus/ServiceRole/DefaultPolicy/Resource",
    #     [{
    #         "id": 'AwsSolutions-IAM5',
    #         "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
    #             ' with evidence for those permission. Added temporarily to identify resource arns.'
    #     }]
    # )

    # CREATE ADDITIONAL RESOURCES
    i_create_additional_resources_fn = create_lambda_function(
        scope=scope,
        function_name='CreateAdditionalResources',
        function_path='stepfunction',
        description='This function will create additional resources to complete the account provisioning process.',
        layers=[account_creation_layer],
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "ASSUMED_ROLE_NAME": "AWSControlTowerExecution"
        }
    )
    i_create_additional_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "iam:CreateAccountAlias",
            "organizations:ListTagsForResource",
            "organizations:TagResource",
            "organizations:UntagResource",
            "tag:GetGetResources",
            "tag:GetTagKeys",
            "tag:GetTagValues"
        ],
        resources=["*"]
    ))
    i_create_additional_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "sts:AssumeRole"
        ],
        resources=["arn:aws:iam::*:role/AWSControlTowerExecution"]
    ))
    _sfn_lambdas.update({"CreateAdditionalResourcesFunctionArn": i_create_additional_resources_fn.function_arn})

    # NagSuppressions.add_resource_suppressions_by_path(
    #     scope, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionCreateAdditionalResources/ServiceRole/DefaultPolicy/Resource",
    #     [{
    #         "id": 'AwsSolutions-IAM5',
    #         "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
    #             ' with evidence for those permission. Added temporarily to identify resource arns.'
    #     }]
    # )   

    # VALIDATE RESOURCES
    i_validate_resources_fn = create_lambda_function(
        scope=scope,
        function_name='ValidateResources',
        function_path='stepfunction',
        description='This function will validate AWS Resources created during account provisioning.',
        layers=[account_creation_layer],
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "ASSUMED_VALIDATION_ROLE_NAME": config['appInfrastructure']['lzaAccountValidationRole'],
            "ASSUMED_CONFIG_LOG_ROLE_NAME": config['appInfrastructure']['lzaConfigLogValidationRole'],
            "LOG_ARCHIVE_ACCOUNT_NAME": "Log Archive",
            "LOG_ARCHIVE_ACCOUNT_SSM": "/core-accounts/log-archive-account"
        }
    )
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "organizations:DescribeOrganization",
            "organizations:DescribeAccount",
            "organizations:ListAccounts",
            "organizations:ListTagsForResource",
            "organizations:ListRoots",
            "organizations:ListChildren",
            "organizations:ListOrganizationalUnitsForParent",
            "ssm:GetParameters",
            "identitystore:GetUserId",
            "codepipeline:ListActionExecutions",
            "codebuild:BatchGetBuilds",
            "logs:GetLogEvents",
            "states:GetExecutionHistory"
        ],
        resources=["*"]
    ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "sts:AssumeRole"
        ],
        resources=[f"arn:aws:iam::*:role/{config['appInfrastructure']['lzaAccountValidationRole']}"]
    ))
    _sfn_lambdas.update({"ValidateResourcesFunctionArn": i_validate_resources_fn.function_arn})

    # RETURN RESPONSE
    i_return_response_fn = create_lambda_function(
        scope=scope,
        function_name='ReturnResponse',
        function_path='stepfunction',
        description='This function will return either an Account Number or Failure message.',
        layers=[account_creation_layer],
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "SNS_FAILURE_TOPIC": account_creation_failure_sns_arn
        }
    )
    i_return_response_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "sns:Publish"
        ],
        resources=[account_creation_failure_sns_arn]
    ))
    i_return_response_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "kms:GenerateDataKey",
            "kms:Decrypt"
        ],
        resources=["*"]
    ))        
    _sfn_lambdas.update({"ReturnResponseFunctionArn": i_return_response_fn.function_arn})

    i_send_email_ses_fn = create_lambda_function(
        scope=scope,
        function_name='SendEmailWithSES',
        function_path='stepfunction',
        description='This function willsend an email using an SES identity.',
        timeout=900,
        retention_role=retention_role,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "SES_IDENTITY_ARN": f"arn:{partition}:ses:{region}:{account_id}:identity/{account_creation_email_ses_identity}",
            "FROM_EMAIL_ADDRESS": account_creation_email_ses_identity
        }
    )
    i_send_email_ses_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
        actions=[
            "ses:SendEmail"
        ],
        resources=[f"arn:{partition}:ses:{region}:{account_id}:identity/{account_creation_email_ses_identity}"]
    ))
    _sfn_lambdas.update({"SendEmailWithSESFunctionArn": i_send_email_ses_fn.function_arn})

    return _sfn_lambdas