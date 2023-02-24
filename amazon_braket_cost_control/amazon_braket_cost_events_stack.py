# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from constructs import Construct
from aws_cdk import (Stack, aws_events, aws_events_targets)


class AmazonBraketCostEventsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        event_bus_name = kwargs.pop('event_bus_name')
        primary_region = kwargs.pop('primary_region')

        super().__init__(scope, construct_id, **kwargs)

        event_bus_target = aws_events_targets.EventBus(
            aws_events.EventBus.from_event_bus_arn(
                self,
                'braket-event-bus',
                'arn:aws:events:{region}:{account_id}:event-bus/{event_bus_name}'.format(
                    account_id=self.account,
                    region=primary_region,
                    event_bus_name=event_bus_name
                )
            )
        )

        braket_rule = aws_events.Rule(
            self,
            'braket-rule',
            event_pattern=aws_events.EventPattern(
                source=['aws.braket'],
            ),
            enabled=True,
            rule_name='braket-service-events'
        )
        braket_rule.add_target(event_bus_target)

        cloudtrail_rule = aws_events.Rule(
            self,
            'cloudtrail-rule',
            event_pattern=aws_events.EventPattern(
                source=['aws.braket'],
                detail_type=['AWS API Call via CloudTrail'],
                detail={
                    'eventSource': ['braket.amazonaws.com'],
                    'eventName': ['CreateQuantumTask']
                }
            ),
            enabled=True,
            rule_name='braket-cloudtrail-events'
        )
        cloudtrail_rule.add_target(event_bus_target)
