# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

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
