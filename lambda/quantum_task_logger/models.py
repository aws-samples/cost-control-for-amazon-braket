# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from typing import Union
from aws_lambda_powertools.utilities.parser.models import EventBridgeModel
from aws_lambda_powertools.utilities.parser import BaseModel


class UserIdentityModel(BaseModel):
    arn: str


class ResponseElementsModel(BaseModel):
    quantumTaskArn: str
    status: str


class RequestParametersModel(BaseModel):
    deviceArn: str


class CreateQuantumTaskModel(BaseModel):
    userIdentity: UserIdentityModel
    responseElements: ResponseElementsModel
    requestParameters: RequestParametersModel


class QuantumTaskStateModel(BaseModel):
    shots: int
    status: str
    quantumTaskArn: str
    eventName: str
    deviceArn: str


class TaskLoggerModel(EventBridgeModel):
    detail: Union[QuantumTaskStateModel, CreateQuantumTaskModel]

    def get_status(self):
        return self.detail.status if isinstance(self.detail, QuantumTaskStateModel) else self.detail.responseElements.status

    def get_device_arn(self):
        return self.detail.deviceArn if isinstance(self.detail, QuantumTaskStateModel) else self.detail.requestParameters.deviceArn

    def get_device_type(self):
        device_arn = self.get_device_arn()
        return device_arn.split('/')[1]

    def is_qpu_task(self):
        return self.get_device_type() == 'qpu'

    def is_simulator_task(self):
        return self.get_device_type() == 'quantum-simulator'

    def get_task_arn(self):
        return self.detail.quantumTaskArn if isinstance(self.detail, QuantumTaskStateModel) else self.detail.responseElements.quantumTaskArn
