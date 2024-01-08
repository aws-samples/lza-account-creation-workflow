# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_kms as kms
)


def create_sns_topic(scope, sns_name: str, key: kms.IKey, subscribers_email: list = None) -> sns.ITopic:

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
