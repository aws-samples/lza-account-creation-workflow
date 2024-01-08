# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
from aws_cdk import (
    Stack,
    Tags,
    Aspects,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets
)
from constructs import Construct
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from app.helper import replace_ssm_in_config
from app.kms_helper import create_kms_keys
from app.sns_helper import create_sns_topic
from app.ses_helper import create_ses_identity
from app.stepfunction_helper import create_stepfunction
from app.lambda_helper import create_lambda_layer, create_lambda_function, create_lambda_docker_function


class AccountCreationWorkflowStack(Stack):
    """This is the CDK Class that will produce the Account Creation Approval Workflow Stack"""

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Replace SSM Parameters within config file
        config = replace_ssm_in_config(scope=self, temp_config=config)

        # Set varaibles
        account_id = Stack.of(self).account
        region = Stack.of(self).region
        partition = Stack.of(self).partition

        pipeline_stack_name = config['deployInfrastructure']['cloudformation']['stackName']
        app_stack_name = config['appInfrastructure']['cloudformation']['stackName']

        # 3rd Party Integrations
        azure_ad_intgration = config['appInfrastructure'].get('enableAzureADIntegration', "")

        # Start StepFunction Data
        sfn_lambdas = {}
        sfn_data = {
            "AccountId": account_id,
            "Region": region,
            "SSOLoginURL": config['appInfrastructure']['ssoLoginUrl'],
            "SuccessEmailCcList": config['appInfrastructure']['ses']['accountCompletionCcList'],
            "SuccessEmailBlindCcList": config['appInfrastructure']['ses']['accountCompletionBlindCcList'],
        }

        # KMS Keys
        i_kms_keys = create_kms_keys(scope=self)

        # SNS Topics
        i_account_creation_failure_sns = create_sns_topic(
            scope=self, sns_name='AccountCreationFailure',
            key=i_kms_keys['SNS'],
            subscribers_email=config['appInfrastructure']['sns']['accountCreationFailure']
        )

        # SES Identity
        i_account_creation_from_email_ses = create_ses_identity(
            scope=self, identity_name='AccountCreationFromEmail',
            identity_email=config['appInfrastructure']['ses']['accountCompletionFromEmail']
        )

        # Lambda Layers
        i_account_creation_helper_layer = create_lambda_layer(
            scope=self, layer_name='account_creation_helper',
            description=''
        )
        i_boto3_layer = create_lambda_layer(
            scope=self, layer_name='boto3',
            description='Updated boto3 layer to ensure the latest boto3 package is being used for AWS Lambda Functions'
        )

        # IAM Role for cdk log retention
        i_log_retention_role = iam.Role(
            self, "rLogRetentionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="IAM Role for the Log Retention Solution"
        )
        i_log_retention_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )
        i_log_retention_role.add_to_policy(
            statement=iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup",
                "logs:DeleteRetentionPolicy",
                "logs:PutRetentionPolicy"
            ],
            resources=["*"]
        ))
        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLogRetentionRole/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission. Needed * for resource readonly access to logs.'
            }]
        )   

        # Lambda Event Based
        i_account_tag_ssm_parameter_fn = create_lambda_function(
            scope=self,
            function_name='AccountTagToSsmParameter',
            function_path='event',
            description='This function will create a local SSM Parameter for each Account Tag found in AWS Organizations.',
            layers=[i_account_creation_helper_layer, i_boto3_layer],
            timeout=120,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "ASSUMED_ROLE_NAME": config['appInfrastructure']['accountTagToSsmParameterRole']
            }
        )
        i_account_tag_ssm_parameter_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "sts:AssumeRole"
            ],
            resources=[f"arn:{partition}:iam::*:role/{config['appInfrastructure']['accountTagToSsmParameterRole']}"]
        ))
        events.Rule(self, "rEventRuleAccountTagToSsmParameter",
            event_pattern=events.EventPattern(
                detail={
                    "eventSource": ["organizations.amazonaws.com"],
                    "eventName": ["TagResource", "UntagResource"]
                },
                detail_type=events.Match.equals_ignore_case("AWS API Call via CloudTrail"),
                source=["aws.organizations"],
            ),
            targets=[targets.LambdaFunction(i_account_tag_ssm_parameter_fn)]
        )
        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionAccountTagToSsmParameter/ServiceRole/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission. Needed * for resource readonly access to all accounts.'
            }]
        )    

        # Lamdab Functions used by StepFunction
        # CHECK FOR RUNNING PROCESSES
        i_check_for_running_proc_fn = create_lambda_function(
            scope=self,
            function_name='CheckForRunningProcesses',
            function_path='stepfunction',
            description='This function will ensure there are no running processes before proceeding to create an AWS Account.',
            layers=[i_boto3_layer],
            timeout=120,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
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
        sfn_lambdas.update({"CheckForRunningProcessesFunctionArn": i_check_for_running_proc_fn.function_arn})

        # CREATE ACCOUNT
        i_create_account_fn = create_lambda_docker_function(
            scope=self,
            function_name='CreateAccount',
            function_path='stepfunction',
            description='This function will update the LZA account-config.yaml which will create an AWS Service ' \
                'Catalog Provisioned Product for Account Vending Machine which creates an account within Control Tower.',
            timeout=900,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
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
        sfn_lambdas.update({"CreateAccountFunctionArn": i_create_account_fn.function_arn})

        # GET ACCOUNT STATUS
        i_get_account_status_fn = create_lambda_function(
            scope=self,
            function_name='GetAccountStatus',
            function_path='stepfunction',
            description='This function will check the account creation status.',
            layers=[i_account_creation_helper_layer],
            timeout=900,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
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
        sfn_lambdas.update({"GetAccountStatusFunctionArn": i_get_account_status_fn.function_arn})

        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionGetAccountStatus/ServiceRole/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission. Added temporarily to identify resource arns.'
            }]
        )    
        
        # CREATE ADDITIONAL RESOURCES
        i_create_additional_resources_fn = create_lambda_function(
            scope=self,
            function_name='CreateAdditionalResources',
            function_path='stepfunction',
            description='This function will create additional resources to complete the account provisioning process.',
            layers=[i_account_creation_helper_layer],
            timeout=900,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
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
        sfn_lambdas.update({"CreateAdditionalResourcesFunctionArn": i_create_additional_resources_fn.function_arn})

        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionCreateAdditionalResources/ServiceRole/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission. Added temporarily to identify resource arns.'
            }]
        )   

        # VALIDATE RESOURCES
        i_validate_resources_fn = create_lambda_function(
            scope=self,
            function_name='ValidateResources',
            function_path='stepfunction',
            description='This function will validate AWS Resources created during account provisioning.',
            layers=[i_account_creation_helper_layer],
            timeout=900,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
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
        sfn_lambdas.update({"ValidateResourcesFunctionArn": i_validate_resources_fn.function_arn})

        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionValidateResources/ServiceRole/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission. Added temporarily to identify resource arns.'
            }]
        )

        # RETURN RESPONSE
        i_return_response_fn = create_lambda_function(
            scope=self,
            function_name='ReturnResponse',
            function_path='stepfunction',
            description='This function will return either an Account Number or Failure message.',
            layers=[i_account_creation_helper_layer],
            timeout=900,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "SNS_FAILURE_TOPIC": i_account_creation_failure_sns.topic_arn
            }
        )
        i_return_response_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "sns:Publish"
            ],
            resources=[i_account_creation_failure_sns.topic_arn]
        ))
        i_return_response_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "kms:GenerateDataKey"
            ],
            resources=["*"]
        ))        
        sfn_lambdas.update({"ReturnResponseFunctionArn": i_return_response_fn.function_arn})

        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionReturnResponse/ServiceRole/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission. Added temporarily to identify resource arns.'
            }]
        )

        i_send_email_ses_fn = create_lambda_function(
            scope=self,
            function_name='SendEmailWithSES',
            function_path='stepfunction',
            description='This function willsend an email using an SES identity.',
            timeout=900,
            retention_role=i_log_retention_role,
            key=i_kms_keys['Lambda'],
            env_vars={
                "LOG_LEVEL": config['appInfrastructure']['lambda']['functionLogLevel'],
                "SES_IDENTITY_ARN": f"arn:{partition}:ses:{region}:{account_id}:identity/{i_account_creation_from_email_ses.email_identity_name}",
                "FROM_EMAIL_ADDRESS": i_account_creation_from_email_ses.email_identity_name
            }
        )
        i_send_email_ses_fn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=[
                "ses:SendEmail"
            ],
            resources=[f"arn:{partition}:ses:{region}:{account_id}:identity/{i_account_creation_from_email_ses.email_identity_name}"]
        ))
        sfn_lambdas.update({"SendEmailWithSESFunctionArn": i_send_email_ses_fn.function_arn})

        if azure_ad_intgration:
            i_identity_center_helper_layer = create_lambda_layer(
                scope=self, layer_name='identity_center_helper',
                description='Layer to hold common AWS Identity Center code.'
            )
            i_azure_ad_helper_layer = create_lambda_layer(
                scope=self, layer_name='azure_ad_helper',
                description='Layer to hold common Azure Active Directory code.'
            )

            # SYNC AZURE AD GROUP
            i_sync_ad_group_fn = create_lambda_function(
                scope=self,
                function_name='AzureADGroupSync',
                function_path='stepfunction',
                description='This function will create a new Azure AD group in the specified tenant',
                layers=[i_azure_ad_helper_layer],
                timeout=900,
                retention_role=i_log_retention_role,
                key=i_kms_keys['Lambda'],
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
            sfn_lambdas.update({"AzureADGroupSyncFunctionArn": i_sync_ad_group_fn.function_arn})

            NagSuppressions.add_resource_suppressions_by_path(
                self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionAzureADGroupSync/ServiceRole/DefaultPolicy/Resource",
                [{
                    "id": 'AwsSolutions-IAM5',
                    "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                        ' with evidence for those permission. List permissions typically needs to have a * in resources.'
                }]
            )
            
            # VALIDATE AD GROUP SYNC TO SSO
            i_valid_ad_group_sync_fn = create_lambda_function(
                scope=self,
                function_name='ValidateADGroupSyncToSSO',
                function_path='stepfunction',
                description='This function will check that the AD group exists in Identity Center (SSO)',
                layers=[
                    i_boto3_layer,
                    i_identity_center_helper_layer
                ],
                timeout=900,
                retention_role=i_log_retention_role,
                key=i_kms_keys['Lambda'],
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
            sfn_lambdas.update({"ValidateADGroupSyncToSSOFunctionArn": i_valid_ad_group_sync_fn.function_arn})

            NagSuppressions.add_resource_suppressions_by_path(
                self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionValidateADGroupSyncToSSO/ServiceRole/DefaultPolicy/Resource",
                [{
                    "id": 'AwsSolutions-IAM5',
                    "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                        ' with evidence for those permission. List permissions typically needs to have a * in resources.'
                }]
            )
            
            # ATTACH PERMISSION SET
            i_attach_permission_set_fn = create_lambda_function(
                scope=self,
                function_name='AttachPermissionSet',
                function_path='stepfunction',
                description='This function will attach a given permission set name to a given group name',
                layers=[
                    i_boto3_layer,
                    i_identity_center_helper_layer
                ],
                timeout=900,
                retention_role=i_log_retention_role,
                key=i_kms_keys['Lambda'],
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
            sfn_lambdas.update({"AttachPermissionSetFunctionArn": i_attach_permission_set_fn.function_arn})

            NagSuppressions.add_resource_suppressions_by_path(
                self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rLambdaFunctionAttachPermissionSet/ServiceRole/DefaultPolicy/Resource",
                [{
                    "id": 'AwsSolutions-IAM5',
                    "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                        ' with evidence for those permission. List permissions typically needs to have a * in resources.'
                }]
            )

        # Setup the use of Active Directory Integration or not
        if azure_ad_intgration:
            def_file = "app/stepfunction/definition-ad-integration.yaml"
        else:
            def_file = "app/stepfunction/definition.yaml"
        
        # StepFunction
        sfn_data.update(sfn_lambdas)
        i_sfn = create_stepfunction(
            scope=self,
            sfn_name='CreateAccount',
            sfn_data=sfn_data,
            sfn_def_file=def_file
        )
        i_sfn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=list(sfn_lambdas.values())
        ))
        
        NagSuppressions.add_resource_suppressions_by_path(
            self, f"/{pipeline_stack_name}/Deploy-Application/{app_stack_name}/rStateMachineCreateAccount/Role/DefaultPolicy/Resource",
            [{
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission.'
            }]
        )

        # Add tags to all resources created
        tags = json.loads(json.dumps(config['tags']))
        for key, value in tags.items():
            Tags.of(self).add(key, value)

        Aspects.of(self).add(AwsSolutionsChecks())
        
        NagSuppressions.add_stack_suppressions(
            self,
            [{
                "id": 'AwsSolutions-IAM4',
                "reason": 'The IAM user, role, or group uses AWS managed policies.'
            },
            {
                 "id": 'AwsSolutions-L1',
                "reason": 'The non-container Lambda function is not configured to use the latest runtime version.'
            }]
        )
