# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Tags,
    Aspects,
    pipelines,
    aws_iam as iam,
    aws_s3 as s3,
    aws_codepipeline_actions as codepipeline_actions
)
from cdk_nag import NagSuppressions, AwsSolutionsChecks
from pipeline.pipeline_app_stage import PipelineAppStage


class PipelineStack(cdk.Stack):
    """
    CDK Stack for the deployment pipeline.

    This stack sets up the CodePipeline for building and deploying the application.
    It includes the source, build, and deployment stages, along with necessary resources
    such as S3 buckets and IAM roles.
    """

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
            self.construct_prefix+"SourceS3Bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            bucket_name=src_bucket_name,
            enforce_ssl=True,
            versioned=True
        )

        NagSuppressions.add_resource_suppressions(
            self.source_bucket,
            [
                {
                    "id": "AwsSolutions-S1",
                    "reason": "The S3 Bucket has server access logs disabled."
                }
            ]
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
        region = stack.region
        account = stack.account

        pipeline_name = config['deployInfrastructure']['codepipeline']['pipelineName']

        # Create an S3 bucket CodePipeline Artifacts
        self.pipeline_bucket = s3.Bucket(
            self,
            self.construct_prefix+"PipelineS3Bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            bucket_name=f"{pipeline_name}-{region}-{account}",
            enforce_ssl=True
        )

        NagSuppressions.add_resource_suppressions(
            self.pipeline_bucket,
            [
                {
                    "id": "AwsSolutions-S1",
                    "reason": "The S3 Bucket has server access logs disabled."
                }
            ]
        )

        # Create a Pipeline
        source = pipelines.CodePipelineSource.s3(
            bucket=self.source_bucket,
            object_key="zipped/source.zip",
            action_name="Source",
            trigger=codepipeline_actions.S3Trigger.EVENTS
        )
        pipeline = pipelines.CodePipeline(
            self,
            self.construct_prefix+"CodePipeline",
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

        # Cleanup CodePipeline Artifact Bucket during Cfn Stack Deletion
        pipeline_bucket = pipeline.pipeline.artifact_bucket
        pipeline_bucket.apply_removal_policy(RemovalPolicy.DESTROY)

        NagSuppressions.add_resource_suppressions(
            pipeline,
            [
                {
                    "id": "AwsSolutions-S1",
                    "reason": "The S3 Bucket has server access logs disabled."
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "The IAM entity contains wildcard permissions and does not " \
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

        # Create Source S3 Bucket
        self.create_pipeline_source_bucket(config=config)

        # CodePipeline Setup
        self.create_pipeline(config=config)

        # Add tags to all resources created
        tags = json.loads(json.dumps(config["tags"]))
        for key, value in tags.items():
            Tags.of(self).add(key, value)

        Aspects.of(self).add(AwsSolutionsChecks())
