# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.data_classes import event_source, EventBridgeEvent

topic_arn = os.environ['TOPIC_ARN']
policy_arn = os.environ['POLICY_ARN']
roles = list(filter(None, os.environ['ROLES'].strip().split(',')))
groups = list(filter(None, os.environ['GROUPS'].strip().split(',')))
users = list(filter(None, os.environ['USERS'].strip().split(',')))

sns = boto3.client('sns')
iam = boto3.client('iam')

logger = Logger(log_uncaught_exceptions=True)


@event_source(data_class=EventBridgeEvent)
@logger.inject_lambda_context()
def handler(event: EventBridgeEvent, context: LambdaContext) -> None:
    try:
        alarm_name = event.detail['alarmName']
        alarm_state = event.detail['state']
        logger.info('Alarm action triggered', alarm_name=alarm_name, alarm_state=alarm_state)
        if alarm_state['value'] == 'ALARM':
            for role in roles:
                logger.info('Attach policy {} to role {}'.format(policy_arn, role))
                iam.attach_role_policy(RoleName=role, PolicyArn=policy_arn)
            for group in groups:
                logger.info('Attach policy {} to group {}'.format(policy_arn, group))
                iam.attach_group_policy(GroupName=group, PolicyArn=policy_arn)
            for user in users:
                logger.info('Attach policy {} to user {}'.format(policy_arn, user))
                iam.attach_user_policy(UserName=user, PolicyArn=policy_arn)
            sns.publish(
                TopicArn=topic_arn,
                Subject='Amazon Braket Cost Control Policy Attached',
                Message='An Amazon CloudWatch alarm state change triggered attachment of policy {} to roles [{}], groups [{}] and users [{}].'.format(
                    policy_arn,
                    ','.join(roles),
                    ','.join(groups),
                    ','.join(users)
                )
            )
        elif alarm_state['value'] == 'OK':
            for role in roles:
                logger.info('Detach policy {} from role {}'.format(policy_arn, role))
                iam.detach_role_policy(RoleName=role, PolicyArn=policy_arn)
            for group in groups:
                logger.info('Detach policy {} from group {}'.format(policy_arn, group))
                iam.detach_group_policy(GroupName=group, PolicyArn=policy_arn)
            for user in users:
                logger.info('Detach policy {} from user {}'.format(policy_arn, user))
                iam.detach_user_policy(UserName=user, PolicyArn=policy_arn)
            sns.publish(
                TopicArn=topic_arn,
                Subject='Amazon Braket Cost Control Policy Detached',
                Message='An Amazon CloudWatch alarm state change triggered detachment of policy {} to roles [{}], groups [{}] and users [{}].'.format(
                    policy_arn,
                    ','.join(roles),
                    ','.join(groups),
                    ','.join(users)
                )
            )
    except Exception as e:
        logger.exception(e)
        raise
