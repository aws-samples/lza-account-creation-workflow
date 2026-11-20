# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_kms as kms
)
from app.cdk_helpers.lambda_helper import create_lambda_function
from app.cdk_helpers.nag_helper import nag_suppress, partition_variants


def setup_default_stepfunction_lambdas(scope, config: dict, boto3_layer: lambda_.ILayerVersion,
                                       account_creation_layer: lambda_.ILayerVersion,
                                       lambda_key: kms.IKey, sns_key: kms.IKey,
                                       account_creation_failure_sns_arn,
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
        lambda_key: KMS key for Lambda environment encryption
        sns_key: KMS key used for SNS topic encryption
        account_creation_failure_sns_arn: SNS topic ARN for failures
        account_creation_email_ses_identity: SES identity email

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
        description='This function will ensure there are no running processes before proceeding '
                    'to create an AWS Account.',
        layers=[boto3_layer, account_creation_layer],
        timeout=120,
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
            resources=[
                f"arn:{partition}:codebuild:{region}:{account_id}:project/"
                f"{config['appInfrastructure']['accountDecommissionProject']}"]
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
            resources=[
                f"arn:{partition}:codepipeline:{region}:{account_id}:"
                f"{config['appInfrastructure']['lzaPipelineName']}"]
        ))
    _sfn_lambdas.update({"CheckForRunningProcessesFunctionArn": i_check_for_running_proc_fn.function_arn})

    # CREATE ACCOUNT
    lza_pipeline_source = config['appInfrastructure'].get('lzaPipelineSource', 'S3')

    if lza_pipeline_source == 'S3':
        # Resolved from SSM at synth time; app_stack reports an error when
        # either value is empty or invalid.
        lza_config_bucket = config['appInfrastructure']['lzaConfigBucketName']
        lza_pipeline_kms_key_arn = config['appInfrastructure']['lzaPipelineKmsKeyArn']
        i_create_account_fn = create_lambda_function(
            scope=scope,
            function_name='CreateAccountS3',
            function_path='stepfunction',
            description='This function will update the LZA account-config.yaml which will create an AWS Service '
            'Catalog Provisioned Product for Account Vending Machine which creates an account within Control Tower.',
            layers=[account_creation_layer],
            timeout=900,
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
                    "s3:ListBucket"
                ],
                resources=[f"arn:{partition}:s3:::{lza_config_bucket}"]
            ))
        i_create_account_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=[f"arn:{partition}:s3:::{lza_config_bucket}/*"]
            ))
        # KMS permissions for the LZA pipeline S3 bucket encryption key
        i_create_account_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:GenerateDataKey"
                ],
                resources=[lza_pipeline_kms_key_arn]
            ))
        nag_suppress(
            i_create_account_fn.role.node.find_child('DefaultPolicy').node.find_child('Resource'),
            [{
                "id": "AwsSolutions-IAM5",
                "reason": "s3:GetObject and s3:PutObject must reach the "
                          "account-config zip, whose key is set by the LZA "
                          "pipeline source action. Scoped to objects in the "
                          "LZA config bucket only.",
                "appliesTo": partition_variants([
                    f"Resource::arn:<AWS::Partition>:s3:::{lza_config_bucket}/*"
                ])
            }]
        )

    elif lza_pipeline_source == 'GitHub':
        github_secret_name = config['appInfrastructure'].get('githubSecretName', 'GitHubPATSecret')
        i_create_account_fn = create_lambda_function(
            scope=scope,
            function_name='CreateAccountGitHub',
            function_path='stepfunction',
            description='Updates LZA accounts-config.yaml via GitHub PR and triggers the LZA CodePipeline.',
            layers=[account_creation_layer],
            timeout=900,
            key=lambda_key,
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "SC_CT_PRODUCT_NAME": "AWS Control Tower Account Factory",
                "LZA_CONFIG_REPO_NAME": config['appInfrastructure']['lzaRepositoryName'],
                "ROOT_EMAIL_PREFIX": config['appInfrastructure']['rootEmailPrefix'],
                "ROOT_EMAIL_DOMAIN": config['appInfrastructure']['rootEmailDomain'],
                "GITHUB_SECRET_NAME": github_secret_name,
                "GITHUB_REPO_OWNER": config['appInfrastructure'].get('githubRepoOwner', ''),
                "GITHUB_REPO_BRANCH": config['appInfrastructure'].get('githubRepoBranch', 'main')
            }
        )
        i_create_account_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue"
                ],
                resources=[f"arn:{partition}:secretsmanager:{region}:{account_id}:secret:{github_secret_name}-*"]
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
            resources=[
                f"arn:{partition}:codepipeline:{region}:{account_id}:"
                f"{config['appInfrastructure']['lzaPipelineName']}"]
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
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "SC_CT_PRODUCT_NAME": "AWS Control Tower Account Factory",
            "LZA_CONFIG_REPO_NAME": config['appInfrastructure']['lzaRepositoryName'],
            "ROOT_EMAIL_PREFIX": config['appInfrastructure']['rootEmailPrefix'],
            "ROOT_EMAIL_DOMAIN": config['appInfrastructure']['rootEmailDomain']
        }
    )
    # LZA CodeBuild projects share the accelerator prefix of the LZA pipeline name
    # (for example "AWSAccelerator-" for "AWSAccelerator-Pipeline")
    lza_project_prefix = config['appInfrastructure']['lzaPipelineName'].rsplit("-", 1)[0] + "-"
    lza_codebuild_projects_arn = f"arn:{partition}:codebuild:{region}:{account_id}:project/{lza_project_prefix}*"
    i_get_account_status_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "codebuild:BatchGetBuilds"
            ],
            resources=[
                f"arn:{partition}:codebuild:{region}:{account_id}:project/"
                f"{config['appInfrastructure']['accountDecommissionProject']}",
                lza_codebuild_projects_arn
            ]
        ))
    i_get_account_status_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
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
            resources=[f"arn:{partition}:servicecatalog:{region}:{account_id}:*"]
        ))
    nag_suppress(
        i_get_account_status_fn.role.node.find_child('DefaultPolicy').node.find_child('Resource'),
        [{
            "id": "AwsSolutions-IAM5",
            "reason": "Service Catalog product and portfolio IDs are dynamic "
                      "(created by Control Tower). Scoped to account-level "
                      "servicecatalog resources. LZA CodeBuild project names "
                      "are generated by LZA; codebuild:BatchGetBuilds is "
                      "scoped to the LZA accelerator project name prefix.",
            "appliesTo": partition_variants([
                f"Resource::arn:<AWS::Partition>:servicecatalog:{region}:{account_id}:*",
                f"Resource::arn:<AWS::Partition>:codebuild:{region}:{account_id}:project/{lza_project_prefix}*"
            ])
        }]
    )
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
            resources=[
                f"arn:{partition}:codepipeline:{region}:{account_id}:"
                f"{config['appInfrastructure']['lzaPipelineName']}"]
        ))
    _sfn_lambdas.update({"GetAccountStatusFunctionArn": i_get_account_status_fn.function_arn})

    # CREATE ADDITIONAL RESOURCES
    i_create_additional_resources_fn = create_lambda_function(
        scope=scope,
        function_name='CreateAdditionalResources',
        function_path='stepfunction',
        description='This function will create additional resources to complete the account provisioning process.',
        layers=[account_creation_layer],
        timeout=900,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "ASSUMED_ROLE_NAME": "AWSControlTowerExecution"
        }
    )
    i_create_additional_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "iam:CreateAccountAlias"
            ],
            resources=["*"]
        ))
    i_create_additional_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "organizations:ListTagsForResource",
                "organizations:TagResource",
                "organizations:UntagResource"
            ],
            resources=[
                f"arn:{partition}:organizations::{account_id}:account/o-*/*",
                f"arn:{partition}:organizations::{account_id}:ou/o-*/ou-*",
                f"arn:{partition}:organizations::{account_id}:root/o-*/r-*"
            ]
        ))
    i_create_additional_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "tag:GetResources",
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
    nag_suppress(
        i_create_additional_resources_fn.role.node.find_child('DefaultPolicy').node.find_child('Resource'),
        [{
            "id": "AwsSolutions-IAM5",
            "reason": "iam:CreateAccountAlias only supports '*' as resource "
                      "(account-scoped action, no resource ARN). "
                      "tag:Get* actions only support '*' as resource. "
                      "organizations actions are scoped to account, OU and "
                      "root ARNs of the management account; the 'o-*' "
                      "organization ID stays a wildcard because a management "
                      "account belongs to exactly one organization, so it "
                      "grants nothing extra. "
                      "sts:AssumeRole targets newly-created accounts with "
                      "unpredictable IDs; scoped to specific role name.",
            "appliesTo": partition_variants([
                "Resource::*",
                "Resource::arn:aws:iam::*:role/AWSControlTowerExecution",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:account/o-*/*",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:ou/o-*/ou-*",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:root/o-*/r-*"
            ])
        }]
    )
    _sfn_lambdas.update({"CreateAdditionalResourcesFunctionArn": i_create_additional_resources_fn.function_arn})

    # VALIDATE RESOURCES
    lza_validation_role = config['appInfrastructure']['lzaAccountValidationRole']

    i_validate_resources_fn = create_lambda_function(
        scope=scope,
        function_name='ValidateResources',
        function_path='stepfunction',
        description='This function will validate AWS Resources created during account provisioning.',
        layers=[account_creation_layer],
        timeout=900,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "ASSUMED_VALIDATION_ROLE_NAME": lza_validation_role,
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
                "organizations:ListOrganizationalUnitsForParent"
            ],
            resources=[
                f"arn:{partition}:organizations::{account_id}:account/o-*/*",
                f"arn:{partition}:organizations::{account_id}:ou/o-*/ou-*",
                f"arn:{partition}:organizations::{account_id}:root/o-*/r-*",
                f"arn:{partition}:organizations::{account_id}:organization/o-*"
            ]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "organizations:DescribeOrganization",
                "organizations:ListAccounts"
            ],
            resources=["*"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "ssm:GetParameters"
            ],
            resources=[f"arn:{partition}:ssm:{region}:{account_id}:parameter/core-accounts/*"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "identitystore:GetUserId"
            ],
            resources=[f"arn:{partition}:identitystore::{account_id}:identitystore/*"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "codepipeline:ListActionExecutions"
            ],
            resources=[
                f"arn:{partition}:codepipeline:{region}:{account_id}:"
                f"{config['appInfrastructure']['lzaPipelineName']}"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "codebuild:BatchGetBuilds"
            ],
            resources=[f"arn:{partition}:codebuild:{region}:{account_id}:project/*"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "logs:GetLogEvents"
            ],
            resources=[f"arn:{partition}:logs:{region}:{account_id}:log-group:*:log-stream:*"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "states:GetExecutionHistory"
            ],
            resources=[f"arn:{partition}:states:{region}:{account_id}:execution:*:*"]
        ))
    i_validate_resources_fn.add_to_role_policy(
        statement=iam.PolicyStatement(
            actions=[
                "sts:AssumeRole"
            ],
            resources=[
                f"arn:aws:iam::*:role/{lza_validation_role}"
            ]
        ))
    nag_suppress(
        i_validate_resources_fn.role.node.find_child('DefaultPolicy').node.find_child('Resource'),
        [{
            "id": "AwsSolutions-IAM5",
            "reason": "ValidateResources must inspect resources across newly "
                      "created accounts. organizations:DescribeOrganization and "
                      "organizations:ListAccounts require '*' resource. "
                      "codebuild project names are dynamic (LZA-generated). "
                      "logs and states require wildcard for dynamic log groups "
                      "and executions. sts:AssumeRole targets new accounts "
                      "with unpredictable IDs; scoped to a specific role name. "
                      "The 'o-*' organization ID stays a wildcard because a "
                      "management account belongs to exactly one organization.",
            "appliesTo": partition_variants([
                "Resource::*",
                f"Resource::arn:aws:iam::*:role/{lza_validation_role}",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:account/o-*/*",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:ou/o-*/ou-*",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:root/o-*/r-*",
                f"Resource::arn:<AWS::Partition>:organizations::{account_id}:organization/o-*",
                f"Resource::arn:<AWS::Partition>:ssm:{region}:{account_id}:parameter/core-accounts/*",
                f"Resource::arn:<AWS::Partition>:identitystore::{account_id}:identitystore/*",
                f"Resource::arn:<AWS::Partition>:codebuild:{region}:{account_id}:project/*",
                f"Resource::arn:<AWS::Partition>:logs:{region}:{account_id}:log-group:*:log-stream:*",
                f"Resource::arn:<AWS::Partition>:states:{region}:{account_id}:execution:*:*"
            ])
        }]
    )
    _sfn_lambdas.update({"ValidateResourcesFunctionArn": i_validate_resources_fn.function_arn})

    # RETURN RESPONSE
    i_return_response_fn = create_lambda_function(
        scope=scope,
        function_name='ReturnResponse',
        function_path='stepfunction',
        description='This function will return either an Account Number or Failure message.',
        layers=[account_creation_layer],
        timeout=900,
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
            resources=[sns_key.key_arn]
        ))
    _sfn_lambdas.update({"ReturnResponseFunctionArn": i_return_response_fn.function_arn})

    # SEND EMAIL WITH SES
    i_send_email_ses_fn = create_lambda_function(
        scope=scope,
        function_name='SendEmailWithSES',
        function_path='stepfunction',
        description='This function will send an email using an SES identity.',
        timeout=900,
        key=lambda_key,
        env_vars={
            "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
            "SES_IDENTITY_ARN": f"arn:{partition}:ses:{region}:{account_id}:identity/"
                                f"{account_creation_email_ses_identity}",
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
