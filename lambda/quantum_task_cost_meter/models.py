# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from decimal import Decimal
from typing import List
from aws_lambda_powertools.utilities.parser.models import DynamoDBStreamModel, DynamoDBStreamRecordModel, DynamoDBStreamChangedRecordModel
from aws_lambda_powertools.utilities.parser import BaseModel


class TaskTableRecordModel(BaseModel):
    task_execution: str
    user_identity: str
    device_arn: str
    cost: Decimal


class CostMeterChangedRecordModel(DynamoDBStreamChangedRecordModel):
    NewImage: TaskTableRecordModel


class CostMeterRecordModel(DynamoDBStreamRecordModel):
    dynamodb: CostMeterChangedRecordModel


class CostMeterStreamModel(DynamoDBStreamModel):
    Records: List[CostMeterRecordModel]