# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
from aws_cdk import (
    Stack,
    Tags,
    Aspects,
    CfnOutput,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets
)
from constructs import Construct
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from app.cdk_helpers.helper import replace_ssm_in_config
from app.cdk_helpers.kms_helper import create_kms_keys
from app.cdk_helpers.sns_helper import create_sns_topic
from app.cdk_helpers.ses_helper import create_ses_identity
from app.cdk_helpers.stepfunction_helper import create_stepfunction
from app.cdk_helpers.lambda_helper import create_lambda_layer, create_lambda_function
from app.default_stepfunction_lambdas import setup_default_stepfunction_lambdas
from app.option_api_gateway import setup_api_gateway
from app.option_azure_ad_integration import setup_azure_ad_integration


class AccountCreationWorkflowStack(Stack):
    """
    Account Creation Workflow Stack
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        """
        Initialize the construct.

        This method sets up initial configuration by replacing SSM 
        parameters, extracting account details, and initializing 
        integration settings from the config.

        Args:
            scope (Construct): The construct scope
            construct_id (str): Unique ID for the construct
            config (dict): Configuration dictionary
            **kwargs: Additional arguments
        
        Returns:
            None
        """
        super().__init__(scope, construct_id, **kwargs)

        # Replace SSM Parameters within config file
        config = replace_ssm_in_config(scope=self, input_config=config)

        # Set varaibles
        account_id = Stack.of(self).account
        region = Stack.of(self).region
        partition = Stack.of(self).partition

        # Integration usage
        azure_ad_intgration = config['appInfrastructure'].get('enableAzureADIntegration', False)
        use_api_gateway = config['appInfrastructure'].get('useApiGateway', False)
        use_graph_api_sync = config['appInfrastructure'].get('useGraphApiSync', False)

        # Start StepFunction Data
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

        # EventBus is needed incase the originating region is not us-east-1, organizational resources only push 
        #   Cloudtrail events to us-east-1. We have to pass that event to the from us-east-1 to the desired region. 
        if region != 'us-east-1':
            i_event_bus = events.EventBus(
                self, "rLzaAccountCreationWorkflowEventBus",
                event_bus_name="LzaAccountCreationWorkflowEventBus"
            )
            CfnOutput(self, "oLzaAccountCreationWorkflowEventBusArn", value=i_event_bus.event_bus_arn)
        else:
            i_event_bus = events.EventBus.from_event_bus_name(
                self, "rDefaultEventBus",
                event_bus_name='default'
            )
            
        events.Rule(self, "rEventRuleAccountTagToSsmParameter",
            event_bus=i_event_bus,                    
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

        # Lamdab Functions used by StepFunction
        sfn_lambdas = setup_default_stepfunction_lambdas(
            scope=self,
            config=config,
            boto3_layer=i_boto3_layer,
            account_creation_layer=i_account_creation_helper_layer,
            retention_role=i_log_retention_role,
            lambda_key=i_kms_keys['Lambda'],
            account_creation_failure_sns_arn=i_account_creation_failure_sns.topic_arn,
            account_creation_email_ses_identity=i_account_creation_from_email_ses.email_identity_name
        )

        # Setup the use of Active Directory Integration or not
        if azure_ad_intgration:
            _sfn_azure_lambdas = setup_azure_ad_integration(
                scope=self,
                config=config,
                boto3_layer=i_boto3_layer,
                retention_role=i_log_retention_role,
                lambda_key=i_kms_keys['Lambda']
            )

            sfn_lambdas.update(_sfn_azure_lambdas)

            if use_graph_api_sync:
                def_file = "app/stepfunction/definition-ad-integration-w-idc-sync.yaml"
            else:
                def_file = "app/stepfunction/definition-ad-integration.yaml"

        else:
            def_file = "app/stepfunction/definition.yaml"

        # Setup Api Gateway to kick off the StepFunction
        if use_api_gateway:
            setup_api_gateway(
                scope=self,
                config=config,
                boto3_layer=i_boto3_layer,
                retention_role=i_log_retention_role,
                lambda_key=i_kms_keys['Lambda']
            )

        # StepFunction
        sfn_data.update(sfn_lambdas)
        i_sfn = create_stepfunction(
            scope=self,
            sfn_name=config['appInfrastructure']['stepFunctionName'],
            sfn_data=sfn_data,
            sfn_def_file=def_file
        )
        i_sfn.add_to_role_policy(
            statement=iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=list(sfn_lambdas.values())
        ))

        NagSuppressions.add_stack_suppressions(
            self,
            [{
                "id": 'AwsSolutions-IAM4',
                "reason": 'The IAM user, role, or group uses AWS managed policies.'
            },
            {
                "id": 'AwsSolutions-IAM5',
                "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag rule suppression' \
                    ' with evidence for those permission.'
            },
            {
                "id": 'AwsSolutions-L1',
                "reason": 'The non-container Lambda function is not configured to use the latest runtime version.'
            },
            {
                "id": 'AwsSolutions-COG4',
                "reason": 'The API GW method does not use a Cognito user pool authorizer.'
            },
            {
                "id": 'AwsSolutions-APIG2',
                "reason": 'Validation has been created for POST Method.'
            }]
        )

        # Add tags to all resources created
        tags = json.loads(json.dumps(config['tags']))
        for key, value in tags.items():
            Tags.of(self).add(key, value)

        Aspects.of(self).add(AwsSolutionsChecks())
