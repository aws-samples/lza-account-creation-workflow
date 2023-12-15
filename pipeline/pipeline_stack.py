# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
import aws_cdk as cdk
from constructs import Construct
import cdk_nag
from aws_cdk import (
    pipelines,
    aws_codecommit as codecommit
)
from pipeline.pipeline_app_stage import PipelineAppStage
from pipeline.pipeline_helper import create_archive
from pipeline.cdk_nag_suppression import pipeline_nag_suppression


class PipelineStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a zip file to all CodeCommit to import
        archive_file = create_archive(
            ignored_files_directories=config.get("deployInfrastructure", {}).get("codecommit", {}).get('ignoredFilesDirectories', [])
        )

        # Create CodeCommit repository with solution contents
        repository = codecommit.Repository(
            self, "rCodeCommitRepository",
            repository_name=config['deployInfrastructure']['codecommit']['repositoryName'],
            code=codecommit.Code.from_zip_file(
                file_path=archive_file,
                branch='main'
            )
        )

        source = pipelines.CodePipelineSource.code_commit(repository, "main")

        pipeline = pipelines.CodePipeline(
            self, "rCodePipeline",
            pipeline_name=config['deployInfrastructure']['codepipeline']['pipelineName'],
            docker_enabled_for_self_mutation=True,
            docker_enabled_for_synth=True,
            enable_key_rotation=True,
            cross_account_keys=True,
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

        # Add tags to all resources created
        tags = json.loads(json.dumps(config['tags']))
        for key, value in tags.items():
            cdk.Tags.of(self).add(key, value)

        # Force CDK to build pipeline beforing running CFN NAG
        pipeline.build_pipeline()

        cdk.Aspects.of(self).add(cdk_nag.AwsSolutionsChecks())
        pipeline_nag_suppression(scope=self, stack_name=cdk.Stack.of(self).stack_name)
