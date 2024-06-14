# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import logging
import os
import shutil
from dataclasses import dataclass
from typing import List
import boto3
import git

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


@dataclass
class GHCodeCommit:
    """Helper class for working with CodeCommit actions
    """
    repository_name: str
    session: boto3.session.Session

    def __post_init__(self):
        self.cc_client = self.session.client('codecommit')

    def create_pull_request(self, title: str, source_ref: str, destination_ref: str) -> dict:
        """Creates an AWS CodeCommit Pull Request

        Args:
            title (str): Title of the pull request
            source_ref (str): AWS CodeCommit Source Reference
            destination_ref (str): AWS CodeCommit Destination Reference

        Returns:
            dict: _description_
        """
        return self.cc_client.create_pull_request(
            title=title,
            targets=[
                {
                    'repositoryName': self.repository_name,
                    'sourceReference': source_ref,
                    'destinationReference': destination_ref
                }
            ]
        )

    def create_repository(self) -> dict:
        """Create CodeCommit repository if it doesn't exist

        Returns:
            dict: Information about the newly created repository
        """
        try:
            return self.cc_client.create_repository(
                repositoryName=self.repository_name
            )
        except self.cc_client.exceptions.RepositoryNameExistsException as name_exists_exception:
            LOGGER.info('Repository %s already exists', self.repository_name)
            LOGGER.debug(name_exists_exception)

    def get_repository(self) -> dict:
        """Gets CodeCommit repository information if it exists

        Returns:
            dict: boto3 response
        """
        try:
            return self.cc_client.get_repository(
                repositoryName=self.repository_name
            )
        except self.cc_client.exceptions.RepositoryDoesNotExistException as not_exists_exception:
            LOGGER.error(
                'The repository %s does not exist, run create_repository() first or fix the name value', self.repository_name)
            LOGGER.debug(not_exists_exception)
            return {}

    def delete_repository(self) -> dict:
        """Delete AWS CodeCommit Repository

        Returns:
            dict: boto3 response
        """
        LOGGER.info("Deleting CodeCommit Repository: %s", self.repository_name)
        return self.cc_client.delete_repository(
            repositoryName=self.repository_name
        )

    def codecommit_git_url(self) -> str:
        """Generates CodeCommit Git URL

        Args:
            version (str): AWS CodeCommit Version (typically is v1)

        Returns:
            str: CodeCommit GIT URL
        """
        _region = self.cc_client.meta.region_name
        return f'codecommit::{_region}://{self.repository_name}'


@dataclass
class GHGit:
    """Helper class for git commands in a Lambda function using lambda-git
    """
    local_repo_path: str

    def __post_init__(self):
        self._repo = None

    def make_branch(self, branch_name: str) -> None:
        """Create a git branch in local repo and checkout the new branch

        Args:
            branch_name (str): The name of the new branch to create and checkout
        """
        LOGGER.info("Creating and Checking Out Branch: %s", branch_name)
        if not self._repo:
            self._repo = git.Repo(self.local_repo_path)
        branch = self._repo.create_head(branch_name)
        self.checkout(branch)

    def checkout(self, branch: git.refs.head.Head) -> None:
        """Run git checkout command on branch name

        Args:
            branch_name (str): The branch name to checkout
        """
        self._repo.head.reference = branch

    def clone(self, code_commit: GHCodeCommit) -> None:
        """Clone a CodeCommit repository to self.local_repo_path

        Args:
            code_commit (GHCodeCommit): The GHCodeCommit object with information about the repo to clone
        """
        self.delete_local_repo_folder()
        LOGGER.info('Cloning repo %s to %s',
                    code_commit.repository_name, self.local_repo_path)
        git_url = code_commit.codecommit_git_url()

        self._repo = git.Repo.clone_from(git_url, self.local_repo_path,
                                         allow_unsafe_protocols=True)
        LOGGER.info('Repo cloned: %s', self._repo.remotes)

    def create_commit(self, list_of_files_to_commit: List[str], commit_message: str, commit_author: str = 'Create_Account_Automation',
                      commit_email: str = 'do-not-reply@amazon.com') -> bool:
        """Create a commit in the local git branch

        Args:
            list_of_files_to_commit (List[str]): List of file paths to commit
            commit_message (str): A commit comment

        Returns:
            bool: True if successful
        """
        LOGGER.info('Committing repository: %s', self.local_repo_path)
        actor = git.Actor(commit_author, commit_email)
        self._repo.index.add(list_of_files_to_commit)
        self._repo.index.commit(commit_message, author=actor, committer=actor)

    def push(self):
        """Push commits to remote origin
        """
        logging.info('Pushing to origin')
        _origin = self._repo.remotes.origin
        _origin.push().raise_if_error()

    def delete_local_repo_folder(self) -> None:
        """Deletes the local repo folder self.local_repo_path
        """
        LOGGER.info("Deleting %s", self.local_repo_path)
        if os.path.exists(self.local_repo_path):
            shutil.rmtree(self.local_repo_path)
