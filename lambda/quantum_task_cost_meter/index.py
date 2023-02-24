# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
from decimal import Decimal
from dateutil import parser
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.parser import event_parser
from models import CostMeterStreamModel, TaskTableRecordModel

ALL_TIME = 'all_time'

cloudwatch = boto3.client('cloudwatch')
dynamodb = boto3.client('dynamodb')
cost_table_name = os.environ['COST_TABLE_NAME']

logger = Logger(log_uncaught_exceptions=True)


@event_parser(model=CostMeterStreamModel)
@logger.inject_lambda_context()
def handler(event: CostMeterStreamModel, context: LambdaContext) -> None:
    try:
        for record in event.Records:
            data: TaskTableRecordModel = record.dynamodb.NewImage
            task_execution = data.task_execution.S
            user_arn = data.user_identity.S
            device_arn = data.device_arn.S
            month = parser.parse(task_execution).strftime('%Y-%m')
            month_user = '{month}_{user}'.format(month=month, user=user_arn)
            month_device = '{month}_{device}'.format(month=month, device=device_arn)
            bins = [ALL_TIME, month, month_user, month_device]
            aggregated_cost = {}
            for cost_bin in bins:
                response = dynamodb.update_item(
                    TableName=cost_table_name,
                    Key={'bin': {'S': cost_bin}},
                    UpdateExpression='SET cost = if_not_exists(cost, :initial_cost) + :task_cost, last_task_execution = :task_execution',
                    ExpressionAttributeValues={
                        ':task_cost': {'N': data.cost.N},
                        ':initial_cost': {'N': '0'},
                        ':task_execution': {'S': task_execution},
                    },
                    ReturnValues='ALL_NEW'
                )
                aggregated_cost[response['Attributes']['bin']['S']] = response['Attributes']['cost']['N']
            logger.info('Aggregate cost', extra=aggregated_cost)
            timestamp = parser.parse(task_execution).timestamp()
            task_cost = Decimal(data.cost.N)
            cloudwatch.put_metric_data(
                Namespace='/aws/braket',
                MetricData=[
                    {
                        'MetricName': 'QuantumTaskCost',
                        'Timestamp': timestamp,
                        'Value': task_cost,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'User Identity', 'Value': user_arn},
                            {'Name': 'Device', 'Value': device_arn}
                        ]
                    },
                    {
                        'MetricName': 'QuantumTaskCost',
                        'Timestamp': timestamp,
                        'Value': task_cost,
                        'Unit': 'Count',
                    },
                    {
                        'MetricName': 'AggregatedQuantumTaskCostAllTime',
                        'Timestamp': timestamp,
                        'Value': Decimal(aggregated_cost[ALL_TIME]),
                        'Unit': 'Count',
                    },
                    {
                        'MetricName': 'AggregatedQuantumTaskCostMonth',
                        'Timestamp': timestamp,
                        'Value': Decimal(aggregated_cost[month]),
                        'Unit': 'Count',
                    },
                    {
                        'MetricName': 'AggregatedQuantumTaskCostMonth',
                        'Timestamp': timestamp,
                        'Value': Decimal(aggregated_cost[month_user]),
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'User Identity', 'Value': user_arn}
                        ]
                    },
                    {
                        'MetricName': 'AggregatedQuantumTaskCostMonth',
                        'Timestamp': timestamp,
                        'Value': Decimal(aggregated_cost[month_device]),
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'Device', 'Value': device_arn}
                        ]
                    },
                ]
            )
    except Exception as e:
        logger.exception(e)
        raise
