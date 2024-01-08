# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import tempfile
import shutil
from pathlib import Path


def create_archive(ignored_files_directories: list, zip_name='zip_file') -> str:
    """This definition will update files based on the fileReplacement key within the config.yaml file
    then this function will zip the contents.

    Args:
        ignored_files_directories (list) (optional): List of files or directories that need to be ignored
        zip_name (str) (optional): Zip file name

    Returns:
       :str: Location of zip (archived) file
    """

    # Setting up array with a None value
    if ignored_files_directories is None:
        ignored_files_directories = []

    # Adding standard ignored files/directories to variable
    ignored_files_directories.extend((
        "__pycache__",
        "cdk.out",
        ".git",
        ".DS_Store",
        ".venv",
        ".python-version"
    ))

    root_dir = Path(__file__).parents[1]
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a copy of the directory
        shutil.copytree(
            root_dir,
            os.path.join(tmpdir, zip_name),
            # UPDATE this section if there are additional pattern that need to be ignored
            ignore=shutil.ignore_patterns(*ignored_files_directories)
        )

        # Create Zip File
        shutil.make_archive(
            os.path.join('cdk.out/', zip_name),
            'zip',
            os.path.join(tmpdir, zip_name)
        )

    return os.path.join('cdk.out/', zip_name+".zip")
