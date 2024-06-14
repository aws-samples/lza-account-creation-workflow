# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from cdk_nag import NagSuppressions


def pipeline_nag_suppression(scope, stack_name: str):
    """
    Generate suppressions for CDK Nag linting rules.

    Args:
        scope (Construct): The scope in which to define this construct's resources.
        stack_name (str): The name of the stack.

    Returns: 
        None

    This function adds suppressions for CDK Nag linting rules to ignore known issues in the pipeline. 
    It suppresses rules related to IAM permissions, CodeBuild privileged mode, and S3 access logging.
    """
    # Stack Level Suppression
    NagSuppressions.add_stack_suppressions(
        scope,
        [{
            "id": 'AwsSolutions-IAM5',
            "reason": 'The IAM entity contains wildcard permissions and does not have a cdk-nag' \
                ' rule suppression with evidence for those permission.'
        }]
    )

    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/{stack_name}/rCodePipelineS3Bucket/Resource",
        [{
            "id": 'AwsSolutions-S1',
            "reason": 'The S3 Bucket has server access logs disabled.'
        }]
    )
    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/{stack_name}/rCodePipeline/UpdatePipeline/SelfMutation/Resource",
        [{
            "id": 'AwsSolutions-CB3',
            "reason": 'The CodeBuild project has privileged mode enabled.'
        }]
    )
    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/{stack_name}/rCodePipeline/Pipeline/Build/Synth/CdkBuildProject/Resource",
        [{
            "id": 'AwsSolutions-CB3',
            "reason": 'The CodeBuild project has privileged mode enabled.'
        }]
    )
    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/{stack_name}/rCodePipeline/Assets/DockerAsset1/Resource",
        [{
            "id": 'AwsSolutions-CB3',
            "reason": 'The CodeBuild project has privileged mode enabled.'
        }]
    )
    NagSuppressions.add_resource_suppressions_by_path(
        scope, f"/{stack_name}/rCodePipeline/Pipeline/ArtifactsBucket/Resource",
        [{
            "id": 'AwsSolutions-S1',
            "reason": 'The S3 Bucket has server access logs disabled.'
        }]
    )
