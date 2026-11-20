# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Tags,
    Aspects,
    pipelines,
    aws_iam as iam,
    aws_s3 as s3,
    aws_codepipeline_actions as codepipeline_actions
)
from cdk_nag import NagSuppressions, AwsSolutionsChecks
from app.cdk_helpers.helper import LZA_SSM_VALUE_PATTERNS, get_ssm_parameter_names
from pipeline.pipeline_app_stage import PipelineAppStage

# Days after which server access logs are deleted
ACCESS_LOG_EXPIRATION_DAYS = 90


class PipelineStack(cdk.Stack):
    """
    CDK Stack for the deployment pipeline.

    This stack sets up the CodePipeline for building and deploying the application.
    It includes the source, build, and deployment stages, along with necessary resources
    such as S3 buckets and IAM roles.
    """

    def create_access_log_bucket(self):
        """
        Creates the S3 bucket that receives server access logs of the pipeline buckets.

        The bucket uses SSE-S3 because S3 server access logging cannot deliver
        to a bucket that is encrypted with AWS KMS. Objects expire after 90 days.
        """
        self.access_log_bucket = s3.Bucket(
            self,
            self.construct_prefix + "AccessLogsS3Bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireAccessLogs",
                    expiration=Duration.days(ACCESS_LOG_EXPIRATION_DAYS)
                )
            ]
        )

        NagSuppressions.add_resource_suppressions(
            self.access_log_bucket,
            [
                {
                    "id": "AwsSolutions-S1",
                    "reason": "This bucket is the destination of the server access "
                              "logs of the pipeline buckets and does not log to itself."
                }
            ]
        )

    def create_pipeline_source_bucket(self, config: dict):
        """
        Creates an S3 bucket for uploading the source code archive.

        Args:
            config (dict): The application configuration.
        """
        # Get current stack name
        stack = Stack.of(self)
        region = stack.region
        account = stack.account

        # Create CodePipeline Source Bucket
        src_bucket_name = f"{config['deployInfrastructure']['codepipeline']['sourceBucketPrefix']}-{region}-{account}"
        self.source_bucket = s3.Bucket(
            self,
            self.construct_prefix + "SourceS3Bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            bucket_name=src_bucket_name,
            enforce_ssl=True,
            versioned=True,
            server_access_logs_bucket=self.access_log_bucket,
            server_access_logs_prefix="source-bucket/"
        )

    def enable_artifact_bucket_access_logs(self, artifact_bucket: s3.IBucket):
        """
        Sends the server access logs of the CDK Pipelines artifact bucket to the access-log bucket.

        The artifact bucket is created inside CDK Pipelines and exposes no access-log
        property, so the underlying CloudFormation resource is changed.

        Args:
            artifact_bucket (s3.IBucket): The artifact bucket the pipeline uses.
        """
        artifact_bucket.node.default_child.logging_configuration = s3.CfnBucket.LoggingConfigurationProperty(
            destination_bucket_name=self.access_log_bucket.bucket_name,
            log_file_prefix="artifact-bucket/"
        )
        self.access_log_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="S3ServerAccessLogsFromArtifactBucket",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("logging.s3.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[self.access_log_bucket.arn_for_objects("artifact-bucket/*")],
                conditions={
                    "ArnLike": {"aws:SourceArn": artifact_bucket.bucket_arn},
                    "StringEquals": {"aws:SourceAccount": Stack.of(self).account}
                }
            )
        )

    def create_pipeline(self, config: dict):
        """
        Creates the CodePipeline for building and deploying the application.

        Args:
            config (dict): The application configuration.

        The pipeline includes the source, build, and deployment stages, along with
        necessary resources such as S3 buckets and IAM roles.
        """
        # Get current stack name
        stack = Stack.of(self)

        pipeline_name = config['deployInfrastructure']['codepipeline']['pipelineName']

        # SSM parameter names have to be read before the application stage is
        # created, because the application stack replaces the "SSM:" values.
        lza_ssm_parameter_names = get_ssm_parameter_names(config['appInfrastructure'], LZA_SSM_VALUE_PATTERNS)

        # Create a Pipeline
        source = pipelines.CodePipelineSource.s3(
            bucket=self.source_bucket,
            object_key="zipped/source.zip",
            action_name="Source",
            trigger=codepipeline_actions.S3Trigger.EVENTS
        )
        pipeline = pipelines.CodePipeline(
            self,
            self.construct_prefix + "CodePipeline",
            pipeline_name=pipeline_name,
            docker_enabled_for_self_mutation=True,
            docker_enabled_for_synth=True,
            enable_key_rotation=True,
            cross_account_keys=True,
            code_build_defaults=pipelines.CodeBuildOptions(
                role_policy=[
                    iam.PolicyStatement(
                        actions=[
                            "apigateway:GET"
                        ],
                        resources=["*"],
                        effect=iam.Effect.ALLOW
                    )
                ]
            ),
            synth=pipelines.ShellStep(
                "Synth",
                input=source,
                commands=[
                    "npm install -g aws-cdk",
                    "python -m pip install -r requirements.txt",
                    "cdk synth"
                ]
            )
        )

        # Deployment Stage
        pipeline.add_stage(
            PipelineAppStage(
                self, "Deploy-Application",
                env=cdk.Environment(
                    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
                    region=os.getenv('CDK_DEFAULT_REGION')
                ),
                config=config
            )
        )

        # Builds CodePipeline to allow for Suppression
        pipeline.build_pipeline()

        # Synth lookups of the SSM parameters. A synth CodeBuild project cannot
        # assume the CDK bootstrap lookup role unless it is granted
        # sts:AssumeRole on it, which this pipeline does not do. The CDK CLI
        # then falls back to the credentials of the synth project's own role,
        # so that role needs ssm:GetParameter on exactly these parameters.
        if lza_ssm_parameter_names:
            pipeline.synth_project.role.add_to_principal_policy(
                iam.PolicyStatement(
                    actions=["ssm:GetParameter"],
                    resources=[
                        f"arn:{stack.partition}:ssm:{stack.region}:{stack.account}:parameter{name}"
                        for name in lza_ssm_parameter_names
                    ],
                    effect=iam.Effect.ALLOW
                )
            )

        # Cleanup CodePipeline Artifact Bucket during Cfn Stack Deletion
        pipeline_bucket = pipeline.pipeline.artifact_bucket
        pipeline_bucket.apply_removal_policy(RemovalPolicy.DESTROY)

        # Server access logs of the artifact bucket go to the access-log bucket
        self.enable_artifact_bucket_access_logs(pipeline_bucket)

        NagSuppressions.add_resource_suppressions(
            pipeline,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "The IAM entity contains wildcard permissions and does not "
                    "have a cdk-nag rule suppression with evidence for those permission."
                },
                {
                    "id": "AwsSolutions-CB3",
                    "reason": "The CodeBuild project has privileged mode enabled."
                },
                {
                    "id": "AwsSolutions-CB4",
                    "reason": "The CodeBuild project does not use an AWS KMS key for encryption."
                }
            ],
            apply_to_children=True
        )

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        """
        Initialize the PipelineStack.

        Args:
            scope (Construct): The parent of this stack, usually an App or a Stage, but could be
                any construct.
            construct_id (str): The identifier of this stack. Must be unique within this scope.
            config (dict): Application configuration.
            **kwargs: Other parameters passed to the base class.
        """
        super().__init__(scope, construct_id, **kwargs)

        self.construct_prefix = config['appInfrastructure'].get('constructPrefix')

        # Create Access Log S3 Bucket and Source S3 Bucket
        self.create_access_log_bucket()
        self.create_pipeline_source_bucket(config=config)

        # CodePipeline Setup
        self.create_pipeline(config=config)

        # Add tags to all resources created
        tags = json.loads(json.dumps(config["tags"]))
        for key, value in tags.items():
            Tags.of(self).add(key, value)

        Aspects.of(self).add(AwsSolutionsChecks())
