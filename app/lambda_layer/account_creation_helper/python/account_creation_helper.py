# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
from dataclasses import dataclass
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class CodeBuildExecutionInfoNotFound(Exception):
    """Exception raised when CodeBuild execution info is not found."""


def assume_role_arn(role_arn, role_session_name=os.getenv('AWS_LAMBDA_FUNCTION_NAME', "assume_role_arn_function")):
    """
    Assume the provided IAM role and return AWS credentials.

    Args:
        role_arn (str): ARN of the IAM role to assume.
        role_session_name (str): Name for the assumed role session.

    Returns:
        dict: AWS credentials for the assumed role.
    """
    LOGGER.info(f"Assuming Role:{role_arn}")
    sts_client = boto3.client(service_name='sts')

    assumed_role_object = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=role_session_name
    )

    assumed_credentials = {
        "aws_access_key_id": assumed_role_object['Credentials']['AccessKeyId'],
        "aws_secret_access_key": assumed_role_object['Credentials']['SecretAccessKey'],
        "aws_session_token": assumed_role_object['Credentials']['SessionToken']
    }
    return assumed_credentials


@dataclass
class HelperCodePipeline:
    """Helper class for working with AWS CodePipeline."""
    pipeline_name: str

    def __post_init__(self):
        self.cp_client = boto3.client('codepipeline')

    def get(self):
        """
        Get information about the pipeline. 

        Returns:
            dict: Pipeline information.
        """
        return self.cp_client.get_pipeline(
            name=self.pipeline_name
        )

    def status(self, execution_id: str) -> str:
        """
        Get the status of a pipeline execution.

        Args:
            execution_id (str): The CodePipeline execution ID.

        Returns:
            str: The status of the execution.
        """
        _execution = self.cp_client.get_pipeline_execution(
            pipelineName=self.pipeline_name,
            pipelineExecutionId=execution_id
        )
        return _execution['pipelineExecution']['status']

    def start_execution(self) -> str:
        """
        Start the CodePipeline release execution.

        Returns:
            str: The CodePipeline execution ID.
        """
        return self.cp_client.start_pipeline_execution(
            name=self.pipeline_name
        )['pipelineExecutionId']

    def get_failed_action(self, execution_id: str) -> dict:
        """
        Retrieve information about a failed action in a pipeline execution.

        Args:
            execution_id (str): The CodePipeline execution ID.

        Returns:  
            dict: Information about the failed action.
        """
        _executed_actions = self.cp_client.list_action_executions(
            pipelineName=self.pipeline_name,
            filter={
                'pipelineExecutionId': execution_id
            }
        )
        result = next(iter(
            [action for action in _executed_actions['actionExecutionDetails'] if action['status'] == 'Failed']), {})
        LOGGER.debug('Failed action found: %s', result)
        return result


@dataclass
class HelperCodeBuild:
    """Helper class for working with failed CodeBuild executions."""
    build_id: str

    def __post_init__(self):
        self.cb_client = boto3.client('codebuild')
        self.build_info = self._get_codebuild_output()

    def _get_codebuild_output(self) -> dict:
        """
        Get output information for a CodeBuild execution.

        Returns:
            dict: CodeBuild execution information.
        """
        LOGGER.debug('Getting info for build id: %s', self.build_id)
        return next(
            iter(self.cb_client.batch_get_builds(ids=[self.build_id]).get('builds')), None)

    def get_failed_phase_info(self) -> dict:
        """
        Get information about a failed phase in a CodeBuild execution.

        Raises:
            CodeBuildExecutionInfoNotFound: If no failed phase is found.

        Returns:
            dict: Information about the failed phase.
        """
        LOGGER.debug('Gathering failed phase')
        if self.build_info:
            result = next(iter([phase for phase in self.build_info['phases'] if phase.get(
                'phaseStatus') == 'FAILED']), None)
            if result:
                del (
                    result['startTime'],
                    result['endTime'],
                    result['durationInSeconds']
                )
                return result
        raise CodeBuildExecutionInfoNotFound(
            f'There were no phases with status of failed found in build {self.build_id}')
