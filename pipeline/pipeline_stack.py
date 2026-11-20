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
    pipelines,
    aws_iam as iam,
    aws_s3 as s3,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions
)
from app.cdk_helpers.helper import LZA_SSM_VALUE_PATTERNS, get_ssm_parameter_names
from app.cdk_helpers.nag_helper import nag_suppress, partition_variants
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

        nag_suppress(
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
            pipeline_type=codepipeline.PipelineType.V2,
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

        self.acknowledge_pipeline_findings(pipeline)

    def acknowledge_pipeline_findings(self, pipeline: pipelines.CodePipeline) -> None:
        """
        Acknowledges the cdk-nag findings on the roles CDK Pipelines creates.

        CDK Pipelines generates these grants for its own roles (pipeline,
        source action, synth, self-mutation and file asset publishing). cdk-nag
        3 has no rule-wide acknowledgment, so each wildcard finding is named.
        The resource findings are built from the pipeline's own constructs so
        they follow logical ID changes.

        Args:
            pipeline (pipelines.CodePipeline): The built CDK pipeline.
        """
        stack = Stack.of(self)

        def logical_id(construct) -> str:
            return stack.resolve(stack.get_logical_id(construct.node.default_child))

        artifact_bucket = logical_id(pipeline.pipeline.artifact_bucket)
        project_ids = [
            logical_id(pipeline.synth_project),
            logical_id(pipeline.node.find_child("UpdatePipeline").node.find_child("SelfMutation")),
        ]
        codebuild = f"arn:<AWS::Partition>:codebuild:{stack.region}:{stack.account}"
        logs = f"arn:<AWS::Partition>:logs:{stack.region}:{stack.account}"
        wildcard_findings = [
            # Object and key actions CDK Pipelines grants on its artifact bucket and key
            "Action::s3:Abort*",
            "Action::s3:DeleteObject*",
            "Action::s3:GetBucket*",
            "Action::s3:GetObject*",
            "Action::s3:List*",
            "Action::kms:GenerateDataKey*",
            "Action::kms:ReEncrypt*",
            f"Resource::<{artifact_bucket}.Arn>/*",
            # CodeBuild report groups and log groups of the pipeline's projects
            f"Resource::{codebuild}:report-group/*",
            f"Resource::{logs}:log-group:/aws/codebuild/*",
            # Role assumption by self-mutation, and actions with no resource-level scope
            f"Resource::arn:*:iam::{stack.account}:role/*",
            "Resource::*",
        ]
        for project in project_ids:
            wildcard_findings.extend([
                f"Resource::{codebuild}:report-group/<{project}>-*",
                f"Resource::{logs}:log-group:/aws/codebuild/<{project}>:*",
            ])

        nag_suppress(
            pipeline,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "CDK Pipelines generates these grants for the pipeline, "
                              "source, synth, self-mutation and asset roles. They are "
                              "scoped to the pipeline's artifact bucket and key, its "
                              "CodeBuild projects, and the CDK bootstrap roles.",
                    "appliesTo": partition_variants(wildcard_findings)
                },
                {
                    "id": "AwsSolutions-CB3",
                    "reason": "Privileged mode is required for Docker-based Lambda "
                              "asset bundling during synth and self-mutation."
                },
                {
                    "id": "AwsSolutions-CB4",
                    "reason": "The CodeBuild projects use the default AWS managed "
                              "encryption; the pipeline artifacts are encrypted with "
                              "the pipeline's KMS key."
                }
            ]
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
