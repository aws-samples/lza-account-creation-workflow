# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import tempfile
import logging
import shutil
from pathlib import Path
import yaml
import boto3

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)
logger.setLevel(logging.INFO)
logger.info("Starting...")


def create_archive(config: dict, zip_name="source") -> str:
    """
    Create an archive of the source code, excluding specified files and directories.

    Args:
        config (dict): Application configuration.
        zip_name (str): The name of the zip archive (default: "source").

    Returns:
        str: The full path of the created archive file.

    The function creates a temporary directory, copies the source code into it
    (excluding specified files and directories), creates a zip archive of the
    temporary directory, and returns the full path of the created archive file.
    """
    logger.info("Creating archive")
    # Setting up array with a None value
    ignored_files_directories = config["deployInfrastructure"]['sourceCode'].get(
        "ignoreFilesDirectories", []
    )

    # Adding standard ignored files/directories to variable
    ignored_files_directories.extend(
        (
            "__pycache__",
            "cdk.out",
            ".git",
            ".DS_Store",
            ".venv",
            ".python-version",
            "dist",
            "node_modules",
        )
    )
    logger.info("Ignoring the following in archive file %s", ignored_files_directories)

    root_dir = Path(__file__).parents[1]
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a copy of the directory
        shutil.copytree(
            root_dir,
            os.path.join(tmpdir, zip_name),
            ignore=shutil.ignore_patterns(*ignored_files_directories),
        )
        # Create Zip File
        shutil.make_archive(
            os.path.join(zip_name), "zip", os.path.join(tmpdir, zip_name)
        )

    arch_file_path = os.path.join(tmpdir, zip_name + ".zip")
    logger.info("Archive Path: %s", arch_file_path)
    return arch_file_path


def get_pipeline_s3_bucket_name(src_bucket_prefix: str, client: object) -> str:
    """
    Retrieve the name of an S3 bucket that matches a given prefix.

    Args:
        src_bucket_prefix (str): The prefix to search for in bucket names.
            This is typically a string that partially matches the desired bucket name.
        client (object): An initialized boto3 S3 client object used to interact
            with the AWS S3 service. This client should have the necessary
            permissions to list buckets.

    Returns:
        str: The name of the first S3 bucket found that contains the specified prefix.
            If no matching bucket is found, the function implicitly returns None.
    """
    paginator = client.get_paginator('list_buckets')
    for buckets in paginator.paginate():
        for bucket in buckets['Buckets']:
            if src_bucket_prefix in bucket['Name']:
                return bucket['Name']


def execute_codepipeline(pipeline_name: str, client: object) -> None:
    """
    Start the execution of a CodePipeline.

    Args:
        cli (object): An initialized boto3 CodePipeline client object used to
            interact with the AWS CodePipeline service. This client should have
            the necessary permissions to start a pipeline execution.

    Returns:
        None
    """
    logger.info("Executing Pipeline: %s", pipeline_name)
    exec_response = client.start_pipeline_execution(
        name=pipeline_name
    )
    logger.info("Pipeline Execution Id: %s", exec_response['pipelineExecutionId'])


if __name__ == "__main__":
    # Main function to upload the source code archive to the pipeline source S3 bucket.

    # The function reads the application configuration, creates a source code archive using
    # create_archive(), and uploads the archive to the specified S3 bucket.

    # It handles any exceptions and logs appropriate messages.

    # The function reads the application configuration, creates a source code archive using
    # create_archive(), and uploads the archive to the specified S3 bucket.

    # It handles any exceptions and logs appropriate messages.
    S3_CLIENT = boto3.client("s3")
    CP_CLIENT = boto3.client("codepipeline")

    try:
        CONFIG_FILE_PATH = "./configs/deploy-config.yaml"
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            deploy_config = yaml.load(f, Loader=yaml.SafeLoader)

        SRC_BUCKET_PREFIX = deploy_config['deployInfrastructure']['codepipeline']['sourceBucketPrefix']
        CODEPIPELINE_NAME = deploy_config['deployInfrastructure']['codepipeline']['pipelineName']

        archive_file_path = create_archive(config=deploy_config)
        archive_file_name = archive_file_path.split("/")[-1]

        pipeline_bucket_name = get_pipeline_s3_bucket_name(
            src_bucket_prefix=SRC_BUCKET_PREFIX,
            client=S3_CLIENT
        )

        logger.info("Uploading %s to %s", "zipped/"+archive_file_name, pipeline_bucket_name)
        response = S3_CLIENT.upload_file(
            Filename=archive_file_name,
            Bucket=pipeline_bucket_name,
            Key="zipped/"+archive_file_name
        )

        execute_codepipeline(
            pipeline_name=CODEPIPELINE_NAME,
            client=CP_CLIENT
        )

    except Exception as e:
        logger.error("Error: %s", e)
        raise e
