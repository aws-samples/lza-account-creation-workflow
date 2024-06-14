# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_kms as kms
)


def create_sns_topic(scope, sns_name: str, key: kms.IKey, subscribers_email: list = None) -> sns.ITopic:
    """
    Creates an SNS topic.

    Args:
        scope (Construct): The CDK construct scope in which to define this topic. 
        sns_name (str): The name of the SNS topic.
        key (kms.IKey): The KMS key to encrypt the topic.
        subscribers_email (list, optional): List of subscriber email addresses. Defaults to None.

    Returns:
        sns.ITopic: The created SNS topic object.
    """
    # Create SNS Topic
    i_sns_topic = sns.Topic(
        scope, f"rSnsTopic{sns_name.title().replace('/','')}",
        display_name=sns_name,
        topic_name=sns_name,
        master_key=key
    )

    # Add subscribers emails to SNS Topic
    if subscribers_email:
        for email_address in subscribers_email:
            i_sns_topic.add_subscription(sns_subscriptions.EmailSubscription(email_address))

    return i_sns_topic
