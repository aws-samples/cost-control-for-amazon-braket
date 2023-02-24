# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import boto3
from datetime import timedelta, datetime
from braket.aws import AwsQuantumTask
from braket.tracking import tracker
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.parser import event_parser
from models import TaskLoggerModel, QuantumTaskStateModel, CreateQuantumTaskModel

ttl_attribute_name = os.environ['TTL_ATTRIBUTE_NAME']
task_item_ttl_days = os.environ['TASK_ITEM_TTL_DAYS']
tasks_table_name = os.environ['TASKS_TABLE_NAME']
dynamodb = boto3.client('dynamodb')

logger = Logger(log_uncaught_exceptions=True)


@logger.inject_lambda_context()
@event_parser(model=TaskLoggerModel)
def handler(event: TaskLoggerModel, context: LambdaContext) -> None:
    try:
        logger.info(
            'Parse event',
            time=event.time,
            task_status=event.get_status(),
            device=event.get_device_arn(),
            task_arn=event.get_task_arn()
        )

        if event.get_status() == 'INITIALIZED':
            record_task_user_identity(event_time=event.time, task_data=event.detail)
        elif event.get_status() == 'RUNNING' and event.is_qpu_task():
            task_cost = calculate_qpu_task_cost(task_data=event.detail)
            record_task_cost(event_time=event.time, task_cost=task_cost, task_data=event.detail)
        elif event.get_status() == 'COMPLETED' and event.is_simulator_task():
            task_cost = calculate_simulator_task_cost(task_data=event.detail)
            record_task_cost(event_time=event.time, task_cost=task_cost, task_data=event.detail)
    except Exception as e:
        logger.exception(e)
        raise


def calculate_qpu_task_cost(task_data: QuantumTaskStateModel) -> str:
    task = get_task_from_arn(arn=task_data.quantumTaskArn)
    details = {
        'status': task_data.status,
        'device': task_data.deviceArn,
        'job_task': 'jobArn' in task.metadata(),
        'shots': task_data.shots,
    }
    # noinspection PyProtectedMember
    task_cost = tracker._get_qpu_task_cost(task_arn=task_data.quantumTaskArn, details=details).to_eng_string()
    logger.info('Calculate cost', cost=task_cost, extra=details)
    return task_cost


def calculate_simulator_task_cost(task_data: QuantumTaskStateModel) -> str:
    task = get_task_from_arn(arn=task_data.quantumTaskArn)
    execution_duration = task.result().additional_metadata.simulatorMetadata.executionDuration
    details = {
        'status': task_data.status,
        'device': task_data.deviceArn,
        'job_task': 'jobArn' in task.metadata(),
        'execution_duration': str(execution_duration),
        'billed_duration': max(timedelta(milliseconds=execution_duration), tracker.MIN_SIMULATOR_DURATION)
    }
    # noinspection PyProtectedMember
    task_cost = tracker._get_simulator_task_cost(task_arn=task_data.quantumTaskArn, details=details).to_eng_string()
    logger.info('Calculate cost', cost=task_cost, extra=details)
    return task_cost


def get_task_from_arn(arn: str) -> AwsQuantumTask:
    # noinspection PyProtectedMember
    aws_session = AwsQuantumTask._aws_session_for_task_arn(task_arn=arn)
    aws_session.add_braket_user_agent(os.environ['SOLUTION_ID'])
    return AwsQuantumTask(arn=arn, aws_session=aws_session)


def record_task_cost(event_time: datetime, task_cost: str, task_data: QuantumTaskStateModel) -> None:
    task_status = task_data.status
    device_arn = task_data.deviceArn
    task_arn = task_data.quantumTaskArn
    shots = task_data.shots
    task_ttl = str((event_time + timedelta(days=int(task_item_ttl_days))).timestamp())
    event_time = event_time.isoformat(sep='T')
    logger.info(
        'Record cost',
        time=event_time,
        task_status=task_status,
        device=device_arn,
        task_arn=task_arn,
        task_cost=task_cost
    )
    try:
        dynamodb.update_item(
            TableName=tasks_table_name,
            Key={'task_arn': {'S': task_arn}},
            UpdateExpression='SET task_execution = :task_execution, device_arn = :device_arn, shots = :shots, cost = :cost, #ttl = :task_ttl',
            ExpressionAttributeNames={
                '#ttl': ttl_attribute_name
            },
            ExpressionAttributeValues={
                ':task_execution': {'S': event_time},
                ':device_arn': {'S': device_arn},
                ':shots': {'N': str(shots)},
                ':cost': {'N': task_cost},
                ':task_ttl': {'N': task_ttl}
            },
            ConditionExpression='attribute_not_exists(cost)',
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        logger.debug(
            'Attribute already exists',
            time=event_time,
            task_status=task_status,
            device=device_arn,
            task_arn=task_arn,
            task_cost=task_cost
        )


def record_task_user_identity(event_time: datetime, task_data: CreateQuantumTaskModel) -> None:
    task_status = task_data.responseElements.status
    task_arn = task_data.responseElements.quantumTaskArn
    user_identity = task_data.userIdentity.arn
    device_arn = task_data.requestParameters.deviceArn
    event_time = event_time.isoformat(sep='T')
    logger.info(
        'Record user identity',
        time=event_time,
        task_status=task_status,
        device=device_arn,
        task_arn=task_arn,
        user_identity=user_identity
    )
    try:
        dynamodb.update_item(
            TableName=tasks_table_name,
            Key={'task_arn': {'S': task_arn}},
            UpdateExpression='SET user_identity = :user_identity, device_arn = :device_arn, task_creation = :task_creation',
            ExpressionAttributeValues={
                ':user_identity': {'S': user_identity},
                ':device_arn': {'S': device_arn},
                ':task_creation': {'S': event_time},
            },
            ConditionExpression='attribute_not_exists(user_identity)',
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        logger.debug(
            'Attribute already exists',
            time=event_time,
            task_status=task_status,
            device=device_arn,
            task_arn=task_arn,
            user_identity=user_identity
        )
