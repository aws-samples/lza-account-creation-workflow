# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import re
import logging
import json
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

STS_CLIENT = boto3.client("sts")
SF_CLIENT = boto3.client("stepfunctions")

# Validation patterns
ACCOUNT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{1,48}[a-zA-Z0-9]$')
YAML_SPECIAL_CHARS = re.compile(r'[{}[\],:&*#?|\-<>=!%@\\]')
OU_PATH_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-/]{0,126}[a-zA-Z0-9]$')


class ValidationError(Exception):
    """Raised when input validation fails."""


def validate_account_name(account_name: str) -> None:
    """Validate account name meets requirements.

    Args:
        account_name: The account name to validate.

    Raises:
        ValidationError: If account name is invalid.
    """
    if not account_name:
        raise ValidationError("account_name is required")
    if len(account_name) < 3 or len(account_name) > 50:
        raise ValidationError(
            "account_name must be between 3 and 50 characters"
        )
    if not ACCOUNT_NAME_PATTERN.match(account_name):
        raise ValidationError(
            "account_name must contain only alphanumeric characters "
            "and hyphens, and must start/end with alphanumeric"
        )
    if YAML_SPECIAL_CHARS.search(account_name):
        raise ValidationError(
            "account_name contains invalid special characters"
        )


def validate_managed_org_unit(managed_org_unit: str) -> None:
    """Validate managed org unit path.

    Args:
        managed_org_unit: The OU path to validate.

    Raises:
        ValidationError: If OU path is invalid.
    """
    if not managed_org_unit:
        raise ValidationError("managed_org_unit is required")
    if len(managed_org_unit) > 128:
        raise ValidationError(
            "managed_org_unit must be 128 characters or fewer"
        )
    if not OU_PATH_PATTERN.match(managed_org_unit):
        raise ValidationError(
            "managed_org_unit must contain only alphanumeric "
            "characters, hyphens, and forward slashes"
        )


def generate_sf_exec_name(account_name: str) -> str:
    """Generate a unique Step Function execution name.

    Uses timestamp-based naming to avoid unbounded pagination
    of execution history.

    Args:
        account_name: The account name to use as base.

    Returns:
        str: A unique execution name.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{account_name}-{timestamp}"


def build_error_response(status_code: int, error_code: str, message: str, field: str = None) -> dict:
    """Build a structured error response.

    Args:
        status_code: HTTP status code.
        error_code: Machine-readable error code.
        message: Human-readable error message.
        field: Optional field name that caused the error.

    Returns:
        dict: API Gateway response with structured error.
    """
    error_body = {
        "error": {
            "code": error_code,
            "message": message
        }
    }
    if field:
        error_body["error"]["field"] = field

    return {
        "statusCode": status_code,
        "body": json.dumps(error_body),
        "isBase64Encoded": False,
        "headers": {"content-type": "application/json"}
    }


def lambda_handler(event, context):
    """
    Handles requests to initiate a Step Function execution for account creation.

    Processes incoming requests from API Gateway or direct invocation,
    validates parameters, and starts a Step Function execution.

    Args:
        event (dict): The event passed by Lambda.
        context (object): Lambda Context runtime methods and attributes.

    Returns:
        dict: API response with execution ARN or error details.
    """
    LOGGER.info("RunStepFunction invoked")
    LOGGER.debug("Event keys: %s", list(event.keys()) if isinstance(event, dict) else "non-dict")

    # Parse request body
    if event.get('body'):
        try:
            params = json.loads(event['body'])
        except (json.JSONDecodeError, TypeError) as err:
            return build_error_response(
                400, "INVALID_JSON", f"Request body is not valid JSON: {err}"
            )
    elif isinstance(event, dict):
        params = event
    else:
        return build_error_response(
            400, "INVALID_REQUEST", "Unable to parse request"
        )

    try:
        # REQUIRED fields with validation
        account_name = params.get('account_name')
        support_dl = params.get('support_dl')
        managed_org_unit = params.get('managed_org_unit')

        if not support_dl:
            raise ValidationError("support_dl is required")

        validate_account_name(account_name)
        validate_managed_org_unit(managed_org_unit)

        # Active Directory Group(s)
        ad_integration = params.get('ad_integration')

        # OPTIONAL
        account_email = params.get('account_email')
        region = params.get('region', os.environ.get('AWS_REGION', 'us-east-1'))
        force_update = params.get('force_update', "false")
        bypass_creation = params.get('bypass_creation', "false")
        additional_tags = params.get('account_tags')

        # Setup required tags
        account_tags = [
            {"Key": "account-name", "Value": account_name},
            {"Key": "vendor", "Value": "aws"},
            {"Key": "product-version", "Value": "1.0.0"},
            {"Key": "support-dl", "Value": support_dl}
        ]

        if additional_tags:
            account_tags.extend(additional_tags)

        # Setup Step Function input
        sf_input = {
            "AccountInfo": {
                "ForceUpdate": force_update,
                "AccountName": account_name,
                "AccountEmail": account_email,
                "SupportDL": support_dl,
                "ManagedOrganizationalUnit": managed_org_unit,
                "AccountTags": account_tags,
                "BypassCreation": bypass_creation
            }
        }

        if ad_integration:
            sf_input['AccountInfo']['ADIntegration'] = ad_integration

        # Build state machine ARN
        current_account_id = STS_CLIENT.get_caller_identity()["Account"]
        statemachine_arn = (
            f"arn:aws:states:{region}:{current_account_id}"
            f":stateMachine:{os.environ['STEPFUNCTION_NAME']}"
        )

        # Generate unique execution name (timestamp-based, no pagination needed)
        sf_exec_name = generate_sf_exec_name(account_name)

        # Start execution with collision retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                start_exec_response = SF_CLIENT.start_execution(
                    stateMachineArn=statemachine_arn,
                    name=sf_exec_name,
                    input=json.dumps(sf_input),
                )
                break
            except SF_CLIENT.exceptions.ExecutionAlreadyExists:
                if attempt >= max_retries - 1:
                    return build_error_response(
                        500, "EXECUTION_CONFLICT",
                        "Unable to generate unique execution name after retries"
                    )
                # Append attempt number for uniqueness
                sf_exec_name = f"{account_name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{attempt + 1}"
                LOGGER.debug(
                    "Execution name collision, retrying with: %s",
                    sf_exec_name
                )

        # Build success response
        response_body = {
            "StepFunctionExecutionArn": start_exec_response['executionArn']
        }

        return {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }

    except ValidationError as err:
        LOGGER.warning("Validation error: %s", err)
        return build_error_response(
            400, "VALIDATION_ERROR", str(err)
        )
    except KeyError as err:
        LOGGER.error("Missing required parameter: %s", err)
        return build_error_response(
            400, "MISSING_PARAMETER", f"Missing required parameter: {err}"
        )
    except ClientError as err:
        LOGGER.error("AWS API error: %s", err)
        return build_error_response(
            500, "AWS_ERROR", "Internal service error"
        )
    except Exception as err:
        LOGGER.exception("Unexpected error in RunStepFunction")
        return build_error_response(
            500, "INTERNAL_ERROR", "Internal service error"
        )
