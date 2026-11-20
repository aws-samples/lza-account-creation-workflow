# Developing

How to run the checks this project uses before you open a pull request.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
```

Use Python 3.11 or later. The pipeline synthesizes the CDK app on Python
3.11, so code must not rely on newer syntax such as f-string expressions that
span several lines.

## Unit tests

```bash
CDK_DEFAULT_ACCOUNT=012345678901 CDK_DEFAULT_REGION=us-east-1 PYTHONPATH=. \
  python -m pytest tests/unit -q
```

The CDK template tests in `tests/unit/test_security_patch_templates.py`
synthesize both stacks with the `cdk.json` context and with asset bundling
turned off, so they do not need Docker. They also run cdk-nag
`AwsSolutionsChecks` and fail on any unsuppressed error.

AWS calls are mocked with moto 5 (`from moto import mock_aws`).

## Static checks

```bash
bandit -c .bandit -r app/lambda_src app/lambda_layer scripts
pylint app pipeline --fail-under=9.0
pycodestyle --max-line-length=120 app pipeline
shellcheck scripts/scan.sh
```

To check that the code still compiles on the pipeline's Python version:

```bash
python3.11 -m compileall -q app pipeline tests scripts app.py
```

## Dependency audit

```bash
pip install pip-audit
pip-audit -r requirements.txt -r requirements-test.txt
```

Each Lambda function has its own `requirements.txt` under
`app/lambda_src/`; audit those too when you change them.

## CloudFormation dependency templates

The templates in `dependencies/` are deployed by LZA, not by CDK. Check them
with CFN Guard and the registry rule `IAM_NO_INLINE_POLICY_CHECK`:

```bash
cfn-guard validate -r iam_no_inline_policy_check.guard -d dependencies
```

The rule is in the
[aws-guard-rules-registry](https://github.com/aws-cloudformation/aws-guard-rules-registry/blob/main/rules/aws/iam/iam_no_inline_policy_check.guard).

## cdk-nag suppressions

Write cdk-nag `appliesTo` entries that name a partition through
`partition_variants` in `app/cdk_helpers/nag_helper.py`. `cdk.json` sets
`@aws-cdk/core:enablePartitionLiterals`, so synthesized ARNs contain the
literal partition, and an entry that only uses `<AWS::Partition>` does not
match.

The project stays on cdk-nag 2.x. cdk-nag 3 removes `NagSuppressions`, which
every suppression here uses.

## Synth

```bash
cdk synth
```

Docker must be running for Lambda asset bundling, and the two SSM parameters
from the README prerequisites must exist in the target account.
