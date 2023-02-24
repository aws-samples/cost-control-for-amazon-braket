# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from braket.circuits import Circuit
from braket.aws import AwsDevice

bell = Circuit().h(0).cnot(control=0, target=1)
shots = 100

sv1_device = AwsDevice('arn:aws:braket:::device/quantum-simulator/amazon/sv1')
sv1_task = sv1_device.run(bell, shots=shots)
print('SV1 task', sv1_task.state(), sv1_task.id)

ionq_device = AwsDevice('arn:aws:braket:::device/qpu/ionq/ionQdevice')
ionq_task = ionq_device.run(bell, shots=shots)
print('IonQ task', ionq_task.state(), ionq_task.id)

rigetti_device = AwsDevice('arn:aws:braket:us-west-1::device/qpu/rigetti/Aspen-M-3')
rigetti_task = rigetti_device.run(bell, shots=shots)
print('Rigetti task', rigetti_task.state(), rigetti_task.id)

oqc_device = AwsDevice('arn:aws:braket:eu-west-2::device/qpu/oqc/Lucy')
oqc_task = oqc_device.run(bell, shots=shots)
print('OQC task', oqc_task.state(), oqc_task.id)
