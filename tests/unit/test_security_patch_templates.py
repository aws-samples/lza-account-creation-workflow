# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# pylint: disable=redefined-outer-name
"""Regression tests for the scanner findings fix.

The application and pipeline stacks are synthesized without Docker (the
"aws:cdk:bundling-stacks" context is empty) with the feature flags of
cdk.json, and the template is checked for each finding. SSM lookups are fed
through CDK context values.
"""

import copy
import json
import os
import re
import shutil
import subprocess  # nosec B404
from pathlib import Path
from unittest import mock

import pytest
import yaml
import aws_cdk as cdk
from aws_cdk.assertions import Annotations, Match, Template

from app.app_stack import AccountCreationWorkflowStack
from pipeline.pipeline_stack import PipelineStack

ROOT = Path(__file__).parents[2]
ACCOUNT = "012345678901"
REGION = "us-east-1"
KMS_PARAM = "/lza-account-creation-workflow/lza-pipeline-kms-key-arn"
BUCKET_PARAM = "/lza-account-creation-workflow/lza-config-bucket-name"
KMS_ARN = (
    f"arn:aws:kms:{REGION}:{ACCOUNT}:key/11111111-2222-3333-4444-555555555555"
)
BUCKET = f"aws-accelerator-config-{ACCOUNT}-{REGION}"
DEPENDENCY_FILES = [
    "account-tagging-to-ssm-parameter-role.yaml",
    "global-resource-event-rule.yaml",
]
FUNCTIONS_WITH_HELPER_LAYER = [
    "CheckForRunningProcesses",
    "CreateAccountS3",
    "GetAccountStatus",
]


def _ssm_context_key(name: str) -> str:
    """Returns the CDK context key of an SSM lookup."""
    return f"ssm:account={ACCOUNT}:parameterName={name}:region={REGION}"


def _load_config() -> dict:
    """Loads a fresh copy of the deploy configuration."""
    with open(
        ROOT / "configs" / "deploy-config.yaml", encoding="utf-8"
    ) as cfg:
        return copy.deepcopy(yaml.safe_load(cfg))


def _app(ssm_values: dict = None) -> cdk.App:
    """Creates an app without Docker bundling and with SSM lookup results.

    The feature flags of cdk.json are loaded so the synthesized templates
    match a real deployment (for example literal partitions in ARNs).
    """
    with open(ROOT / "cdk.json", encoding="utf-8") as cdk_json:
        context = dict(json.load(cdk_json)["context"])
    context["aws:cdk:bundling-stacks"] = []
    for name, value in (
        ssm_values
        if ssm_values is not None
        else {KMS_PARAM: KMS_ARN, BUCKET_PARAM: BUCKET}
    ).items():
        context[_ssm_context_key(name)] = value
    return cdk.App(context=context)


def _env() -> cdk.Environment:
    """Returns the test environment."""
    return cdk.Environment(account=ACCOUNT, region=REGION)


def _app_stack(ssm_values: dict = None, config: dict = None):
    """Synthesizes the application stack."""
    app = _app(ssm_values)
    return AccountCreationWorkflowStack(
        app, "AppStack", config=config or _load_config(), env=_env()
    )


@pytest.fixture(scope="module", autouse=True)
def no_aws_calls():
    """Replaces the API Gateway get_account call that runs at synth time."""
    patcher = mock.patch("app.option_api_gateway.boto3.client")
    client = patcher.start()
    client.return_value.get_account.return_value = {}
    yield
    patcher.stop()


@pytest.fixture(scope="module")
def app_stack():
    """Application stack with both SSM parameters resolved."""
    return _app_stack()


@pytest.fixture(scope="module")
def app_template(app_stack):
    """Template of the application stack."""
    return Template.from_stack(app_stack)


@pytest.fixture(scope="module")
def pipeline_template():
    """Template of the pipeline stack."""
    app = _app()
    stack = PipelineStack(
        app, "PipelineStack", config=_load_config(), env=_env()
    )
    return Template.from_stack(stack)


def _policy_statements(template: Template, function_name: str) -> list:
    """Returns the IAM statements of a function's role policy."""
    statements = []
    for logical_id, resource in template.find_resources(
        "AWS::IAM::Policy"
    ).items():
        if f"rLambdaFunction{function_name}ServiceRole" in logical_id:
            statements += resource["Properties"]["PolicyDocument"]["Statement"]
    assert statements, f"no policy found for {function_name}"
    return statements


def _as_list(value) -> list:
    """Wraps a single value in a list."""
    return value if isinstance(value, list) else [value]


# FR2: explicit log groups instead of the log-retention custom resource
def test_no_log_retention_custom_resource(app_template):
    """No Custom::LogRetention resource or log-retention role remains."""
    assert not app_template.find_resources("Custom::LogRetention")
    assert "rLogRetentionRole" not in json.dumps(app_template.to_json())


def test_each_function_has_explicit_log_group(app_template):
    """Every function writes to its own two-month log group, no fixed name."""
    functions = app_template.find_resources("AWS::Lambda::Function")
    log_groups = app_template.find_resources("AWS::Logs::LogGroup")
    assert functions
    targets = set()
    for resource in functions.values():
        log_group_ref = resource["Properties"]["LoggingConfig"]["LogGroup"][
            "Ref"
        ]
        group = log_groups[log_group_ref]["Properties"]
        # No fixed name: no collision with an existing /aws/lambda group
        assert "LogGroupName" not in group
        assert group["RetentionInDays"] == 60
        targets.add(log_group_ref)
    # Each function has its own group
    assert len(targets) == len(functions)


# FR3 / FR4: scoped Lambda roles from the SSM-sourced values
def test_create_account_s3_role_uses_exact_bucket_and_key(app_template):
    """CreateAccountS3 is scoped to the config bucket and the LZA key."""
    statements = _policy_statements(app_template, "CreateAccountS3")
    resources = [
        res for stmt in statements for res in _as_list(stmt["Resource"])
    ]
    assert KMS_ARN in resources
    assert f":s3:::{BUCKET}" in json.dumps(statements)
    assert "key/*" not in json.dumps(statements)
    for stmt in statements:
        if any(
            act.startswith(("s3:", "kms:")) for act in _as_list(stmt["Action"])
        ):
            assert "*" not in _as_list(stmt["Resource"])


def test_create_additional_resources_role_has_documented_wildcards_only(
    app_template,
):
    """Only the APIs without resource-level support use a wildcard resource."""
    statements = _policy_statements(app_template, "CreateAdditionalResources")
    for stmt in statements:
        if "*" in _as_list(stmt["Resource"]):
            actions = _as_list(stmt["Action"])
            assert all(
                act.startswith(("iam:CreateAccountAlias", "tag:"))
                for act in actions
            )
        if any(
            act.startswith("organizations:")
            for act in _as_list(stmt["Action"])
        ):
            assert "*" not in _as_list(stmt["Resource"])


def test_return_response_role_is_scoped(app_template):
    """ReturnResponse allows KMS and SNS only on the topic and its key."""
    statements = _policy_statements(app_template, "ReturnResponse")
    for stmt in statements:
        if any(
            act.startswith(("sns:", "kms:"))
            for act in _as_list(stmt["Action"])
        ):
            assert "*" not in json.dumps(stmt["Resource"])


# FR4.3: failure naming the parameter
@pytest.mark.parametrize(
    "name,value",
    [(KMS_PARAM, ""), (BUCKET_PARAM, ""), (KMS_PARAM, "not-an-arn")],
)
def test_empty_or_invalid_ssm_value_adds_error_naming_parameter(name, value):
    """An empty or invalid value adds a CDK error that names the parameter."""
    values = {KMS_PARAM: KMS_ARN, BUCKET_PARAM: BUCKET, name: value}
    stack = _app_stack(values)
    errors = Annotations.from_stack(stack).find_error(
        "*", Match.string_like_regexp(f".*{re.escape(name)}.*")
    )
    assert errors


def test_resolved_values_add_no_ssm_error(app_stack):
    """Valid values add no error that mentions an SSM parameter."""
    errors = Annotations.from_stack(app_stack).find_error(
        "*", Match.string_like_regexp(".*SSM parameter.*")
    )
    assert not errors


def test_unresolved_lookup_placeholder_adds_no_error():
    """The first-pass placeholder does not count as an invalid value."""
    stack = _app_stack(ssm_values={})
    errors = Annotations.from_stack(stack).find_error(
        "*", Match.string_like_regexp(".*SSM parameter.*")
    )
    assert not errors


def test_missing_config_key_adds_error():
    """A config without the SSM keys reports which key is missing."""
    config = _load_config()
    del config["appInfrastructure"]["lzaPipelineKmsKeyArn"]
    stack = _app_stack(config=config)
    assert Annotations.from_stack(stack).find_error(
        "*", Match.string_like_regexp(".*lzaPipelineKmsKeyArn.*")
    )


def test_app_stack_has_no_unsuppressed_cdk_nag_errors(app_stack):
    """cdk-nag AwsSolutionsChecks reports no unsuppressed error."""
    errors = Annotations.from_stack(app_stack).find_error(
        "*", Match.string_like_regexp("AwsSolutions-.*")
    )
    assert not errors


# FR8.3 / FR8.4
def test_helper_layer_is_attached_to_functions_that_import_it(app_template):
    """The account_creation_helper layer is on the three functions."""
    layers = [
        key
        for key in app_template.find_resources("AWS::Lambda::LayerVersion")
        if "Accountcreationhelper" in key
        or "AccountCreationHelper" in key.replace("_", "")
    ]
    assert layers
    functions = app_template.find_resources("AWS::Lambda::Function")
    for name in FUNCTIONS_WITH_HELPER_LAYER:
        function = next(
            res
            for res in functions.values()
            if res["Properties"].get("FunctionName") == name
        )
        assert any(
            layer in json.dumps(function["Properties"]["Layers"])
            for layer in layers
        ), name


def test_get_account_status_batch_get_builds_is_scoped(app_template):
    """GetAccountStatus can read only the decommission and LZA builds."""
    statements = _policy_statements(app_template, "GetAccountStatus")
    builds = [
        stmt
        for stmt in statements
        if "codebuild:BatchGetBuilds" in _as_list(stmt["Action"])
    ]
    assert builds
    for stmt in builds:
        resources = _as_list(stmt["Resource"])
        assert "*" not in resources
        assert all(":project/" in json.dumps(res) for res in resources)


# FR6: pipeline access logging
def test_access_log_bucket_properties(pipeline_template):
    """The access-log bucket is SSE-S3, private, SSL-only and expires logs."""
    buckets = pipeline_template.find_resources(
        "AWS::S3::Bucket",
        {
            "Properties": {
                "LifecycleConfiguration": {
                    "Rules": [Match.object_like({"ExpirationInDays": 90})]
                }
            }
        },
    )
    assert len(buckets) == 1
    props = next(iter(buckets.values()))["Properties"]
    assert (
        props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0][
            "ServerSideEncryptionByDefault"
        ]["SSEAlgorithm"]
        == "AES256"
    )
    assert props["PublicAccessBlockConfiguration"]["BlockPublicAcls"] is True
    assert (
        props["PublicAccessBlockConfiguration"]["RestrictPublicBuckets"]
        is True
    )


def test_pipeline_buckets_log_to_access_log_bucket(pipeline_template):
    """Source and artifact buckets log to the access-log bucket."""
    buckets = pipeline_template.find_resources("AWS::S3::Bucket")
    with_logging = {
        key: res
        for key, res in buckets.items()
        if "LoggingConfiguration" in res["Properties"]
    }
    assert len(with_logging) == 2
    assert len(buckets) == 3
    destinations = {
        json.dumps(
            res["Properties"]["LoggingConfiguration"]["DestinationBucketName"]
        )
        for res in with_logging.values()
    }
    assert len(destinations) == 1
    assert next(iter(destinations)) not in [
        json.dumps(k) for k in with_logging
    ]


def test_unused_pipeline_bucket_is_removed(pipeline_template):
    """PipelineS3Bucket no longer exists."""
    assert "PipelineS3Bucket" not in json.dumps(pipeline_template.to_json())


def test_synth_role_reads_only_the_two_ssm_parameters(pipeline_template):
    """The synth role can read exactly the two LZA SSM parameters."""
    statements = []
    for resource in pipeline_template.find_resources(
        "AWS::IAM::Policy"
    ).values():
        statements += resource["Properties"]["PolicyDocument"]["Statement"]
    ssm_statements = [
        s for s in statements if "ssm:GetParameter" in _as_list(s["Action"])
    ]
    assert len(ssm_statements) == 1
    expected = [
        f":ssm:{REGION}:{ACCOUNT}:parameter{KMS_PARAM}",
        f":ssm:{REGION}:{ACCOUNT}:parameter{BUCKET_PARAM}",
    ]
    resources = [
        json.dumps(res) for res in _as_list(ssm_statements[0]["Resource"])
    ]
    assert len(resources) == 2
    for tail in expected:
        assert [res for res in resources if tail + '"' in res]


def test_pipeline_stack_has_no_unsuppressed_cdk_nag_errors():
    """cdk-nag reports no unsuppressed error on the pipeline stack."""
    app = _app()
    stack = PipelineStack(
        app, "PipelineStackNag", config=_load_config(), env=_env()
    )
    errors = Annotations.from_stack(stack).find_error(
        "*", Match.string_like_regexp("AwsSolutions-.*")
    )
    assert not errors


# FR5: removed config-log role
def test_config_log_role_is_removed(app_template):
    """The role template, config key and env variable are gone."""
    assert not (
        ROOT / "dependencies" / "config-log-validation-role.yaml"
    ).exists()
    assert "lzaConfigLogValidationRole" not in json.dumps(_load_config())
    assert "ASSUMED_CONFIG_LOG_ROLE_NAME" not in json.dumps(
        app_template.to_json()
    )
    assert "config-log-validation" not in json.dumps(app_template.to_json())


# FR7: no inline IAM policies in dependency templates
@pytest.mark.parametrize("file_name", DEPENDENCY_FILES)
def test_dependency_templates_have_no_inline_policies(file_name):
    """The role uses a managed policy instead of a Policies list."""
    text = (ROOT / "dependencies" / file_name).read_text(encoding="utf-8")
    assert not re.search(r"^\s+Policies:", text, re.MULTILINE)
    assert "AWS::IAM::ManagedPolicy" in text


# FR1: Bandit no longer reports B608
@pytest.mark.skipif(
    shutil.which("bandit") is None, reason="bandit is not installed"
)
def test_bandit_reports_no_b608_in_lambda_source():
    """Bandit finds no hardcoded SQL expression in the Lambda source."""
    result = subprocess.run(  # nosec B603
        [
            "bandit",
            "-c",
            str(ROOT / ".bandit"),
            "--recursive",
            "-f",
            "json",
            str(ROOT / "app" / "lambda_src"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    report = json.loads(result.stdout)
    assert not [r for r in report["results"] if r["test_id"] == "B608"]
    assert report["metrics"]["_totals"]["SEVERITY.HIGH"] == 0
