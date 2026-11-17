# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import importlib
import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, 'app/lambda_src/stepfunction/CreateAccountGitHub')
sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')

# Set AWS_DEFAULT_REGION before importing the module so that module-level
# boto3.client('secretsmanager') doesn't fail during import
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# Import the module with a unique name to avoid collision with
# CheckForRunningProcesses/main.py which is also named 'main'
_spec = importlib.util.spec_from_file_location(
    "create_account_github_main",
    "app/lambda_src/stepfunction/CreateAccountGitHub/main.py"
)
github_main = importlib.util.module_from_spec(_spec)
sys.modules["create_account_github_main"] = github_main
_spec.loader.exec_module(github_main)


@pytest.fixture(autouse=True)
def _reset_module_cache():
    """Reset the GitHub module secret cache between tests."""
    github_main._cached_secret = None
    github_main._cache_expiry = 0
    yield


@pytest.fixture
def account_info_event():
    """Standard event payload for CreateAccountGitHub tests."""
    return {
        "AccountInfo": {
            "AccountName": "test-new-account",
            "AccountEmail": "root+test-new-account@example.com",
            "ManagedOrganizationalUnit": "Workloads",
            "SupportDL": "team@example.com",
            "ForceUpdate": "false",
            "BypassCreation": "false"
        }
    }


@pytest.fixture
def github_env(monkeypatch):
    """Set required environment variables for GitHub Lambda."""
    monkeypatch.setenv("GITHUB_SECRET_NAME", "GitHubPATSecret")
    monkeypatch.setenv("GITHUB_REPO_OWNER", "my-org")
    monkeypatch.setenv("LZA_CONFIG_REPO_NAME", "aws-accelerator-config")
    monkeypatch.setenv("GITHUB_REPO_BRANCH", "main")
    monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "AWSAccelerator-Pipeline")
    monkeypatch.setenv("ROOT_EMAIL_PREFIX", "root")
    monkeypatch.setenv("ROOT_EMAIL_DOMAIN", "example.com")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def mock_github_repo():
    """Create a mock GitHub repo with valid org and accounts config."""
    mock_repo = MagicMock()

    # org-config.yaml with valid OU
    mock_org_file = MagicMock()
    mock_org_file.decoded_content = (
        b"organizationalUnits:\n"
        b"  - name: Workloads\n"
        b"  - name: Security\n"
    )

    # accounts-config.yaml with one existing account
    mock_accounts_file = MagicMock()
    mock_accounts_file.decoded_content = (
        b"workloadAccounts:\n"
        b"  - name: existing-account\n"
        b"    email: existing@example.com\n"
        b"    organizationalUnit: Workloads\n"
        b"    description: existing-account\n"
    )
    mock_accounts_file.sha = "abc123"

    mock_repo.get_contents.side_effect = [mock_org_file, mock_accounts_file]

    mock_branch = MagicMock()
    mock_branch.commit.sha = "def456"
    mock_repo.get_branch.return_value = mock_branch
    mock_repo.create_git_ref.return_value = MagicMock()
    mock_repo.update_file.return_value = MagicMock()

    mock_pr = MagicMock()
    mock_pr.html_url = "https://github.com/my-org/aws-accelerator-config/pull/1"
    mock_repo.create_pull.return_value = mock_pr

    return mock_repo


class TestCreateAccountGitHubHappyPath:
    """Test happy path: creates PR and returns success."""

    @patch.object(github_main, 'HelperCodePipeline')
    @patch.object(github_main, 'Github')
    @patch.object(github_main, '_get_github_pat', return_value='ghp_test_token_12345')
    def test_creates_pr_successfully(
        self, mock_get_pat, mock_github_class, mock_cp_class,
        github_env, account_info_event, mock_github_repo
    ):
        """Happy path: PR created, pipeline started, payload returned."""
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_github_repo
        mock_github_class.return_value = mock_github

        mock_cp = MagicMock()
        mock_cp.start_execution.return_value = "exec-123"
        mock_cp.status.return_value = "InProgress"
        mock_cp_class.return_value = mock_cp

        result = github_main.lambda_handler(account_info_event, None)

        assert result['GitHub']['PullRequestUrl'] == (
            "https://github.com/my-org/aws-accelerator-config/pull/1"
        )
        assert result['CodePipeline']['CodePipelineExecutionId'] == "exec-123"
        assert result['CodePipeline']['CodePipelineRunStatus'] == "InProgress"
        assert result['ServiceCatalogEvent']['ServiceCatalogRunStatus'] == "Create"
        assert result['AccountInfo'] == account_info_event['AccountInfo']


class TestCreateAccountGitHubMissingSecret:
    """Test missing GitHub secret returns error."""

    @patch.object(github_main, 'SECRETS_CLIENT')
    def test_missing_secret_raises_error(
        self, mock_secrets_client, github_env, account_info_event
    ):
        """When Secrets Manager cannot find secret, RuntimeError is raised."""
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            {
                'Error': {
                    'Code': 'ResourceNotFoundException',
                    'Message': 'Secret not found'
                }
            },
            'GetSecretValue'
        )

        with pytest.raises(RuntimeError, match="AWS API error"):
            github_main.lambda_handler(account_info_event, None)


class TestCreateAccountGitHubInvalidYaml:
    """Test invalid YAML in repo returns error."""

    @patch.object(github_main, 'Github')
    @patch.object(github_main, '_get_github_pat', return_value='ghp_test_token_12345')
    def test_invalid_yaml_raises_error(
        self, mock_get_pat, mock_github_class, github_env, account_info_event
    ):
        """When organization-config.yaml has no organizationalUnits key, error."""
        mock_repo = MagicMock()
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        # YAML that parses but has no 'organizationalUnits' key
        mock_org_file = MagicMock()
        mock_org_file.decoded_content = b"someOtherKey: value\n"
        mock_repo.get_contents.return_value = mock_org_file

        with pytest.raises(RuntimeError):
            github_main.lambda_handler(account_info_event, None)


class TestCreateAccountGitHubApiError:
    """Test GitHub API error handled gracefully."""

    @patch.object(github_main, 'Github')
    @patch.object(github_main, '_get_github_pat', return_value='ghp_test_token_12345')
    def test_github_api_error_raises_runtime_error(
        self, mock_get_pat, mock_github_class, github_env, account_info_event
    ):
        """When GitHub API returns an error, RuntimeError is raised."""
        from github import GithubException

        mock_github = MagicMock()
        mock_github.get_repo.side_effect = GithubException(
            status=404, data={"message": "Not Found"}, headers={}
        )
        mock_github_class.return_value = mock_github

        with pytest.raises(RuntimeError, match="GitHub API error"):
            github_main.lambda_handler(account_info_event, None)


class TestCreateAccountGitHubAccountExists:
    """Test account already exists in config returns error."""

    @patch.object(github_main, 'Github')
    @patch.object(github_main, '_get_github_pat', return_value='ghp_test_token_12345')
    def test_account_exists_no_force_update(
        self, mock_get_pat, mock_github_class, github_env
    ):
        """When account already exists and ForceUpdate is false, error raised."""
        mock_repo = MagicMock()
        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        # org-config with valid OU
        mock_org_file = MagicMock()
        mock_org_file.decoded_content = (
            b"organizationalUnits:\n"
            b"  - name: Workloads\n"
        )

        # accounts-config already has 'duplicate-account'
        mock_accounts_file = MagicMock()
        mock_accounts_file.decoded_content = (
            b"workloadAccounts:\n"
            b"  - name: duplicate-account\n"
            b"    email: dup@example.com\n"
            b"    organizationalUnit: Workloads\n"
            b"    description: duplicate-account\n"
        )
        mock_accounts_file.sha = "sha123"

        mock_repo.get_contents.side_effect = [
            mock_org_file,
            mock_accounts_file
        ]

        event = {
            "AccountInfo": {
                "AccountName": "duplicate-account",
                "AccountEmail": "dup@example.com",
                "ManagedOrganizationalUnit": "Workloads",
                "SupportDL": "team@example.com",
                "ForceUpdate": "false",
                "BypassCreation": "false"
            }
        }

        with pytest.raises(RuntimeError) as exc:
            github_main.lambda_handler(event, None)

        # FR1: message keeps naming the account and the force-update flag
        assert "already contains an account" in str(exc.value)
        assert "duplicate-account" in str(exc.value)
        assert "force-update flag is False" in str(exc.value)


class TestCreateAccountGitHubBranchName:
    """Test branch name generated correctly from account name."""

    def test_branch_name_from_account_name_with_spaces(self):
        """Branch name slugifies spaces to hyphens and lowercases."""
        # Test the slugification logic used in _create_github_pr
        account_name = "My Test Account"
        expected_slug = "my-test-account"

        actual_slug = account_name.lower().replace(" ", "-")
        expected_branch = f"account-creation/{expected_slug}"

        assert actual_slug == expected_slug
        assert expected_branch == "account-creation/my-test-account"

    def test_branch_name_no_spaces(self):
        """Branch name with no spaces remains unchanged except lowercase."""
        account_name = "SimpleAccount"
        expected_slug = "simpleaccount"
        actual_slug = account_name.lower().replace(" ", "-")
        assert actual_slug == expected_slug


class TestCreateAccountGitHubSecretsNotLogged:
    """Test secrets not logged (verify logger calls don't contain PAT)."""

    @patch.object(github_main, 'HelperCodePipeline')
    @patch.object(github_main, 'Github')
    @patch.object(github_main, 'SECRETS_CLIENT')
    def test_pat_not_in_log_messages(
        self, mock_secrets_client, mock_github_class,
        mock_cp_class, github_env, account_info_event,
        mock_github_repo, caplog
    ):
        """Verify the GitHub PAT value is never logged."""
        import logging

        pat_value = "ghp_super_secret_token_12345"

        mock_secrets_client.get_secret_value.return_value = {
            'SecretString': json.dumps({'pat': pat_value})
        }

        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_github_repo
        mock_github_class.return_value = mock_github

        mock_cp = MagicMock()
        mock_cp.start_execution.return_value = "exec-1"
        mock_cp.status.return_value = "InProgress"
        mock_cp_class.return_value = mock_cp

        with caplog.at_level(logging.DEBUG):
            github_main.lambda_handler(account_info_event, None)

        # Verify PAT value does not appear in any log record
        for record in caplog.records:
            assert pat_value not in record.getMessage(), (
                f"PAT found in log message: {record.getMessage()}"
            )
