# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Tests for the SSM config helpers used by the CDK stacks."""

import aws_cdk as cdk
from aws_cdk.assertions import Annotations, Match

from app.cdk_helpers.helper import (
    LZA_SSM_VALUE_PATTERNS,
    PLACEHOLDER_ARN,
    PLACEHOLDER_VALUE,
    get_ssm_parameter_names,
    get_ssm_value,
    validate_ssm_config_value,
)

ACCOUNT = "012345678901"
REGION = "us-east-1"
NAME = "/test/param"


def _stack(value=None):
    """Creates a stack whose SSM lookup for NAME returns value, if given."""
    context = {"aws:cdk:bundling-stacks": []}
    if value is not None:
        context[
            f"ssm:account={ACCOUNT}:parameterName={NAME}:region={REGION}"
        ] = value
    app = cdk.App(context=context)
    return cdk.Stack(
        app, "S", env=cdk.Environment(account=ACCOUNT, region=REGION)
    )


def test_get_ssm_value_returns_placeholder_before_lookup_is_resolved():
    """The first pass returns a placeholder and adds no error."""
    stack = _stack()
    assert get_ssm_value(stack, NAME) == PLACEHOLDER_VALUE
    assert not Annotations.from_stack(stack).find_error("*", Match.any_value())


def test_get_ssm_value_returns_resolved_value():
    """A resolved value is returned unchanged."""
    stack = _stack("my-bucket")
    assert get_ssm_value(stack, NAME) == "my-bucket"


def test_get_ssm_value_empty_adds_error_naming_parameter():
    """An empty resolved value adds an error that names the parameter."""
    stack = _stack("")
    get_ssm_value(stack, NAME)
    errors = Annotations.from_stack(stack).find_error(
        "*", Match.string_like_regexp(f".*{NAME}.*")
    )
    assert errors


def test_validate_ssm_config_value_flags_invalid_and_skips_placeholders():
    """Invalid values add an error; placeholders and valid values do not."""
    pattern, description = LZA_SSM_VALUE_PATTERNS["lzaConfigBucketName"]
    stack = _stack()
    validate_ssm_config_value(
        stack, NAME, PLACEHOLDER_VALUE, pattern, description
    )
    validate_ssm_config_value(
        stack, NAME, PLACEHOLDER_ARN, pattern, description
    )
    validate_ssm_config_value(
        stack, NAME, "good-bucket-name", pattern, description
    )
    assert not Annotations.from_stack(stack).find_error("*", Match.any_value())
    validate_ssm_config_value(stack, NAME, "Bad_Bucket!", pattern, description)
    assert Annotations.from_stack(stack).find_error(
        "*", Match.string_like_regexp(f".*{NAME}.*")
    )


def test_get_ssm_parameter_names_only_for_s3_source():
    """Names come from SSM: values and only when the LZA source is S3."""
    config = {
        "lzaPipelineKmsKeyArn": "SSM:/a/kms",
        "lzaConfigBucketName": "SSM:/a/bucket",
    }
    assert get_ssm_parameter_names(config, LZA_SSM_VALUE_PATTERNS) == [
        "/a/kms",
        "/a/bucket",
    ]
    assert not get_ssm_parameter_names(
        {**config, "lzaPipelineSource": "GitHub"}, LZA_SSM_VALUE_PATTERNS
    )
    assert not get_ssm_parameter_names(
        {"lzaConfigBucketName": "plain"}, LZA_SSM_VALUE_PATTERNS
    )
