# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from amazon_braket_cost_control.amazon_braket_cost_bus_stack import AmazonBraketCostBusStack
from amazon_braket_cost_control.amazon_braket_cost_events_stack import AmazonBraketCostEventsStack
from amazon_braket_cost_control.amazon_braket_cost_control_stack import AmazonBraketCostControlStack

with open("_version.py") as f:
    version = f.readlines()[-1].split()[-1].strip("\"'")

app = cdk.App()

solution_id = '{}/{}'.format(app.node.try_get_context('solutionIdentifier'), version)
aws_account_id = app.node.try_get_context('awsAccountId')
primary_region = app.node.try_get_context('primaryRegion')
braket_regions = app.node.try_get_context('braketRegions')
task_item_ttl_days = app.node.try_get_context('taskItemTTLDays')
notification_email_address = app.node.try_get_context('notificationEmailAddress')
all_time_cost_limit = app.node.try_get_context('allTimeCostLimit')
monthly_cost_limit = app.node.try_get_context('monthlyCostLimit')
iam_role_names_to_control = app.node.try_get_context('iamRoleNamesToControl')
iam_group_names_to_control = app.node.try_get_context('iamGroupNamesToControl')
iam_user_names_to_control = app.node.try_get_context('iamUserNamesToControl')
event_bus_name = 'braket-cost-control-bus'

AmazonBraketCostBusStack(
    app,
    'AmazonBraketCentralEventBusStack',
    env=cdk.Environment(account=aws_account_id, region=primary_region),
    event_bus_name=event_bus_name,
    braket_regions=braket_regions
)

for region in braket_regions:
    AmazonBraketCostEventsStack(
        app,
        'AmazonBraketCostEventsStack-{region}'.format(region=region),
        env=cdk.Environment(account=aws_account_id, region=region),
        event_bus_name=event_bus_name,
        primary_region=primary_region
    )

AmazonBraketCostControlStack(
    app,
    'AmazonBraketCostControlStack',
    env=cdk.Environment(account=aws_account_id, region=primary_region),
    event_bus_name=event_bus_name,
    task_item_ttl_days=task_item_ttl_days,
    notification_email_address=notification_email_address,
    all_time_cost_limit=all_time_cost_limit,
    monthly_cost_limit=monthly_cost_limit,
    role_names_to_control=iam_role_names_to_control,
    group_names_to_control=iam_group_names_to_control,
    user_names_to_control=iam_user_names_to_control,
    solution_id=solution_id
)
cdk.Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
