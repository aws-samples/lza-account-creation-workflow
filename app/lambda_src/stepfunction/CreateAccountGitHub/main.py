# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
import time

import boto3
import yaml
from botocore.exceptions import ClientError
from github import Github, GithubException

from account_creation_helper import HelperCodePipeline

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

# Module-level boto3 clients (reused across invocations)
SECRETS_CLIENT = boto3.client('secretsmanager')

# Module-level secret cache with TTL
_cached_secret = None
_cache_expiry = 0
_SECRET_CACHE_TTL = 300  # 5 minutes


class AccountNameExistsException(Exception):
    """Raised when account name already exists and force_update is False."""


class OrganizationalUnitNotFoundException(Exception):
    """Raised when the target OU is not found in organization-config.yaml."""


class MissingEnvironmentVariableException(Exception):
    """Raised when a required environment variable is not set."""


def _get_github_pat() -> str:
    """Retrieve GitHub Personal Access Token from AWS Secrets Manager.

    Uses module-level caching with TTL to reduce API calls.

    Returns:
        str: The GitHub Personal Access Token.

    Raises:
        ClientError: If Secrets Manager call fails.
        KeyError: If secret does not contain expected key.
    """
    global _cached_secret, _cache_expiry  # noqa: PLW0603

    if _cached_secret and time.time() < _cache_expiry:
        return _cached_secret

    secret_name = os.environ.get('GITHUB_SECRET_NAME', 'GitHubPATSecret')
    LOGGER.info("Retrieving GitHub PAT from Secrets Manager: %s", secret_name)

    response = SECRETS_CLIENT.get_secret_value(SecretId=secret_name)
    secret_string = response['SecretString']

    # Support both plain string and JSON-formatted secrets
    try:
        secret_dict = json.loads(secret_string)
        # Look for common key names
        pat = (
            secret_dict.get('pat')
            or secret_dict.get('token')
            or secret_dict.get('github_pat')
            or secret_dict.get('personal_access_token')
        )
        if not pat:
            # If JSON but no recognized key, use first value
            pat = next(iter(secret_dict.values()))
    except (json.JSONDecodeError, StopIteration):
        # Plain string secret
        pat = secret_string

    _cached_secret = pat
    _cache_expiry = time.time() + _SECRET_CACHE_TTL

    LOGGER.info("GitHub PAT retrieved and cached successfully")
    return pat


def _build_root_email_address(account_name: str) -> str:
    """Build the root email address from environment variable prefix and domain.

    Args:
        account_name: The name of the account being created.

    Returns:
        The email to be used as the root address for the new account.

    Raises:
        MissingEnvironmentVariableException: If prefix or domain env vars are missing.
    """
    try:
        prefix = os.environ["ROOT_EMAIL_PREFIX"]
        domain = os.environ["ROOT_EMAIL_DOMAIN"]
    except KeyError as key_error:
        raise MissingEnvironmentVariableException(
            f"The environment variable {key_error} was not found but is required"
        ) from key_error

    domain = domain.replace("@", "")
    account_name = account_name.replace(" ", "-")
    root_email = f"{prefix}+{account_name}@{domain}"
    LOGGER.info("Built root account email address as: %s", root_email)
    return root_email


def _validate_ou_in_config(org_config_content: str, target_ou_name: str) -> None:
    """Validate the target OU exists in the organization-config.yaml content.

    Args:
        org_config_content: Raw YAML content of organization-config.yaml.
        target_ou_name: Target OU for the account creation.

    Raises:
        OrganizationalUnitNotFoundException: If OU not found in config.
    """
    org_config = yaml.safe_load(org_config_content)
    config_orgs = [org["name"] for org in org_config["organizationalUnits"]]

    if target_ou_name not in config_orgs:
        raise OrganizationalUnitNotFoundException(
            f"The target OU '{target_ou_name}' for account creation is not found "
            f"in organization-config.yaml. Available OUs: {config_orgs}"
        )


def _update_accounts_config(
    accounts_config_content: str,
    account_info: dict,
    force_update: bool = False
) -> str:
    """Update accounts-config.yaml content with new account entry.

    Args:
        accounts_config_content: Raw YAML content of accounts-config.yaml.
        account_info: Account information dict with AccountName, AccountEmail,
            and ManagedOrganizationalUnit.
        force_update: If True, overwrite existing account with same name.

    Returns:
        Updated YAML content as string.

    Raises:
        AccountNameExistsException: If account name exists and force_update is False.
    """
    account_config = yaml.safe_load(accounts_config_content)

    config_info = {
        "name": account_info["AccountName"],
        "description": account_info["AccountName"],
        "email": account_info["AccountEmail"],
        "organizationalUnit": account_info["ManagedOrganizationalUnit"],
    }

    update_index = -1
    for index, item in enumerate(account_config["workloadAccounts"]):
        if item["name"] == config_info["name"]:
            update_index = index

    if update_index >= 0 and force_update:
        LOGGER.info(
            "Account '%s' already exists in config, force updating",
            config_info["name"]
        )
        account_config["workloadAccounts"][update_index] = config_info
    elif update_index >= 0 and not force_update:
        raise AccountNameExistsException(
            f"The accounts-config.yaml already contains an account with the name of "
            f"'{account_info['AccountName']}' and the force-update flag is False"
        )
    else:
        LOGGER.info("Appending new account '%s' to config", config_info["name"])
        account_config["workloadAccounts"].append(config_info)

    return yaml.dump(account_config, default_flow_style=False)


def _create_github_pr(account_info: dict, force_update: bool) -> str:
    """Create a GitHub pull request with the updated accounts-config.yaml.

    Reads the current config from the configured GitHub repo, validates the OU,
    updates the accounts config, creates a feature branch, commits the change,
    and opens a pull request.

    Args:
        account_info: Account information dict from the Step Function event.
        force_update: Whether to overwrite an existing account entry.

    Returns:
        The URL of the created pull request.

    Raises:
        GithubException: If GitHub API calls fail.
        OrganizationalUnitNotFoundException: If target OU is invalid.
        AccountNameExistsException: If account exists and force_update is False.
    """
    pat = _get_github_pat()
    github_client = Github(pat)

    repo_owner = os.environ.get('GITHUB_REPO_OWNER', '')
    repo_name = os.environ.get('LZA_CONFIG_REPO_NAME', 'aws-accelerator-config')
    base_branch = os.environ.get('GITHUB_REPO_BRANCH', 'main')

    # Construct full repo name (owner/repo)
    full_repo_name = f"{repo_owner}/{repo_name}" if repo_owner else repo_name
    LOGGER.info("Connecting to GitHub repository: %s", full_repo_name)

    repo = github_client.get_repo(full_repo_name)

    # Read organization-config.yaml to validate OU
    LOGGER.info("Reading organization-config.yaml from branch '%s'", base_branch)
    org_config_file = repo.get_contents(
        "organization-config.yaml", ref=base_branch
    )
    org_config_content = org_config_file.decoded_content.decode('utf-8')

    _validate_ou_in_config(org_config_content, account_info["ManagedOrganizationalUnit"])

    # Read current accounts-config.yaml
    LOGGER.info("Reading accounts-config.yaml from branch '%s'", base_branch)
    accounts_config_file = repo.get_contents(
        "accounts-config.yaml", ref=base_branch
    )
    accounts_config_content = accounts_config_file.decoded_content.decode('utf-8')

    # Update the accounts config
    updated_content = _update_accounts_config(
        accounts_config_content, account_info, force_update
    )

    # Create feature branch
    account_name_slug = account_info["AccountName"].lower().replace(" ", "-")
    branch_name = f"account-creation/{account_name_slug}"
    LOGGER.info("Creating feature branch: %s", branch_name)

    # Get the SHA of the base branch head
    base_ref = repo.get_branch(base_branch)
    base_sha = base_ref.commit.sha

    # Create the new branch reference
    ref_path = f"refs/heads/{branch_name}"
    try:
        repo.create_git_ref(ref=ref_path, sha=base_sha)
        LOGGER.info("Created branch ref: %s", ref_path)
    except GithubException as e:
        # Branch may already exist from a previous attempt; update it
        if e.status == 422:
            LOGGER.info(
                "Branch '%s' already exists, updating with new commit",
                branch_name
            )
            existing_ref = repo.get_git_ref(f"heads/{branch_name}")
            existing_ref.edit(sha=base_sha, force=True)
        else:
            raise

    # Commit updated accounts-config.yaml to feature branch
    commit_message = (
        f"feat: add account '{account_info['AccountName']}'\n\n"
        f"Account: {account_info['AccountName']}\n"
        f"Email: {account_info['AccountEmail']}\n"
        f"OU: {account_info['ManagedOrganizationalUnit']}\n"
        f"Force Update: {force_update}"
    )

    repo.update_file(
        path="accounts-config.yaml",
        message=commit_message,
        content=updated_content,
        sha=accounts_config_file.sha,
        branch=branch_name
    )
    LOGGER.info("Committed updated accounts-config.yaml to branch '%s'", branch_name)

    # Create pull request
    pr_title = f"Account Creation: {account_info['AccountName']}"
    pr_body = (
        f"## New Account Request\n\n"
        f"| Field | Value |\n"
        f"|-------|-------|\n"
        f"| **Account Name** | {account_info['AccountName']} |\n"
        f"| **Email** | {account_info['AccountEmail']} |\n"
        f"| **Organizational Unit** | {account_info['ManagedOrganizationalUnit']} |\n"
        f"| **Force Update** | {force_update} |\n"
        f"| **Support DL** | {account_info.get('SupportDL', 'N/A')} |\n\n"
        f"---\n"
        f"*Created by LZA Account Creation Workflow*"
    )

    LOGGER.info("Creating pull request: %s -> %s", branch_name, base_branch)
    pull_request = repo.create_pull(
        title=pr_title,
        body=pr_body,
        head=branch_name,
        base=base_branch
    )
    LOGGER.info("Pull request created: %s", pull_request.html_url)

    return pull_request.html_url


def lambda_handler(event, context):
    """Create/setup account(s) via GitHub PR to LZA config repository.

    Updates the accounts-config.yaml in the configured GitHub repository
    by creating a feature branch and pull request, then starts the LZA
    CodePipeline.

    Args:
        event: Event information passed in by AWS Step Functions.
        context: Lambda Function context information.

    Returns:
        dict: Payload values passed to the next step in the Step Function.
    """
    LOGGER.info("Event received: %s", json.dumps(event))
    payload = {}

    try:
        # Extract account info from event (handles retry scenario)
        if event.get('Payload'):
            account_info = event['Payload']['AccountInfo']
        else:
            account_info = event['AccountInfo']

        update_needed = account_info.get('ForceUpdate', 'false')

        # Generate root email if not provided
        if not account_info.get('AccountEmail'):
            account_info['AccountEmail'] = _build_root_email_address(
                account_name=account_info['AccountName']
            )

        if account_info.get('BypassCreation') == 'false':
            # Setup CodePipeline helper
            code_pipeline = HelperCodePipeline(
                os.getenv('LZA_CODEPIPELINE_NAME', 'AWSAccelerator-Pipeline')
            )

            LOGGER.info("Processing account creation for: %s", account_info['AccountName'])

            # Create GitHub PR with updated config
            force_update_bool = update_needed == 'true'
            pr_url = _create_github_pr(account_info, force_update_bool)

            LOGGER.info("GitHub PR created successfully: %s", pr_url)

            # Start LZA pipeline after PR creation
            LOGGER.info("Starting LZA CodePipeline execution")
            pipeline_execution_id = code_pipeline.start_execution()
            pipeline_execution_status = code_pipeline.status(pipeline_execution_id)

            payload['CodePipeline'] = {
                'CodePipelineRunStatus': pipeline_execution_status,
                'CodePipelineExecutionId': pipeline_execution_id
            }
            payload['GitHub'] = {
                'PullRequestUrl': pr_url
            }

            # Set Run Status to see if SC is updating or creating
            payload['ServiceCatalogEvent'] = {}
            if update_needed == 'true':
                payload['ServiceCatalogEvent']['ServiceCatalogRunStatus'] = "Update"
            else:
                payload['ServiceCatalogEvent']['ServiceCatalogRunStatus'] = "Create"

        elif account_info.get('BypassCreation') == 'true':
            LOGGER.info("Bypassing Account Creation...")

        # Add AccountInfo to payload
        payload['AccountInfo'] = account_info

        LOGGER.info("Payload: %s", json.dumps(payload, default=str))
        return payload

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        LOGGER.error(
            "AWS API error [%s]: %s", error_code, error_message
        )
        raise RuntimeError(
            f"AWS API error [{error_code}]: {error_message}"
        ) from e

    except GithubException as e:
        LOGGER.error(
            "GitHub API error [status=%s]: %s", e.status, e.data
        )
        raise RuntimeError(
            f"GitHub API error [status={e.status}]: {e.data}"
        ) from e

    except (AccountNameExistsException, OrganizationalUnitNotFoundException) as e:
        LOGGER.error("Validation error: %s", str(e))
        raise RuntimeError(str(e)) from e

    except (KeyError, ValueError) as e:
        LOGGER.error("Data error: %s", str(e))
        raise RuntimeError(f"Invalid event data: {e}") from e
