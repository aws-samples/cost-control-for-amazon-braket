# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from constructs import Construct
from aws_cdk import (Stack, aws_events, aws_iam)


class AmazonBraketCostBusStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:

        event_bus_name = kwargs.pop('event_bus_name')
        braket_regions = kwargs.pop('braket_regions')

        super().__init__(scope, construct_id, **kwargs)

        event_bus = aws_events.EventBus(
            self,
            'braket-central-bus',
            event_bus_name=event_bus_name
        )
        event_bus.add_to_resource_policy(aws_iam.PolicyStatement(
            sid='restrict-regions',
            effect=aws_iam.Effect.ALLOW,
            principals=[aws_iam.AccountRootPrincipal()],
            actions=['events:PutEvents'],
            resources=[event_bus.event_bus_arn],
            conditions={
                'ArnEquals': {
                    'aws:SourceArn': [
                        'arn:aws:events:{region}:{account_id}:event-bus/default'.format(
                            region=region,
                            account_id=self.account
                        ) for region in braket_regions
                    ]
                }
            }

        ))
