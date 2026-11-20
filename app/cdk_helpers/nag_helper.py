# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import Acknowledgment, Validations
from constructs import IConstruct
from cdk_nag import AwsSolutionsChecks

PARTITION_PLACEHOLDER = "<AWS::Partition>"
# Partitions listed in the "@aws-cdk/core:target-partitions" context of cdk.json
LITERAL_PARTITIONS = ("aws", "aws-cn")


def partition_variants(applies_to: list) -> list:
    """
    Expands cdk-nag appliesTo entries so they match in both partition modes.

    With "@aws-cdk/core:enablePartitionLiterals" CDK renders the partition of
    an ARN as a literal (for example "aws"). Without it, the ARN holds the
    "AWS::Partition" token, which cdk-nag shows as "<AWS::Partition>". Each
    entry that contains the token is returned together with its literal forms.
    Entries without the token are returned unchanged.

    Args:
        applies_to (list): The appliesTo entries written with the token.

    Returns:
        list: The entries with the token form and the literal partition forms.
    """
    expanded = []
    for entry in applies_to:
        expanded.append(entry)
        if PARTITION_PLACEHOLDER in entry:
            expanded.extend(
                entry.replace(PARTITION_PLACEHOLDER, partition)
                for partition in LITERAL_PARTITIONS
            )
    return expanded


def nag_suppress(construct: IConstruct, suppressions: list) -> None:
    """
    Acknowledges cdk-nag findings on a construct and everything under it.

    cdk-nag 3 uses CDK's Validations.acknowledge() instead of NagSuppressions.
    Each suppression is a dict with "id", "reason" and an optional
    "appliesTo" list. A rule with appliesTo is acknowledged once per finding,
    as "<rule>[<finding>]"; a rule without it is acknowledged by its id.

    Args:
        construct (IConstruct): The construct the findings belong to.
        suppressions (list): The suppressions, in the cdk-nag 2 dict format.
    """
    acknowledgments = []
    for suppression in suppressions:
        applies_to = suppression.get("appliesTo")
        if applies_to:
            acknowledgments.extend(
                Acknowledgment(id=f"{suppression['id']}[{finding}]", reason=suppression["reason"])
                for finding in applies_to
            )
        else:
            acknowledgments.append(
                Acknowledgment(id=suppression["id"], reason=suppression["reason"])
            )
    Validations.of(construct).acknowledge(*acknowledgments)


def enable_nag_checks(app: IConstruct) -> None:
    """
    Runs the cdk-nag AwsSolutions checks on every stack of the app.

    cdk-nag 3 is a CDK policy validation plugin. A plugin checks the whole
    app, so it is registered once, on the app. Synth fails with a validation
    report when a finding is not acknowledged.

    Args:
        app (IConstruct): The CDK app.
    """
    Validations.of(app).add_plugins(AwsSolutionsChecks(app))
