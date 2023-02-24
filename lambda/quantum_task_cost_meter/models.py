# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from typing import List
from aws_lambda_powertools.utilities.parser.models import DynamoDBStreamModel, DynamoDBStreamRecordModel, DynamoDBStreamChangedRecordModel
from aws_lambda_powertools.utilities.parser import BaseModel


class DynamoDbStringAttribute(BaseModel):
    S: str


class DynamoDbNumberAttribute(BaseModel):
    N: str


class TaskTableRecordModel(BaseModel):
    task_execution: DynamoDbStringAttribute
    user_identity: DynamoDbStringAttribute
    device_arn: DynamoDbStringAttribute
    cost: DynamoDbNumberAttribute


class CostMeterChangedRecordModel(DynamoDBStreamChangedRecordModel):
    NewImage: TaskTableRecordModel


class CostMeterRecordModel(DynamoDBStreamRecordModel):
    dynamodb: CostMeterChangedRecordModel


class CostMeterStreamModel(DynamoDBStreamModel):
    Records: List[CostMeterRecordModel]