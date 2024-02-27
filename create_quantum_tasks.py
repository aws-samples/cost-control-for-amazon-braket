# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from braket.circuits import Circuit
from braket.aws import AwsDevice
from braket.devices import Devices

bell = Circuit().h(0).cnot(control=0, target=1)
shots = 100

device_arns = [
    Devices.Amazon.SV1,
    Devices.IonQ.Harmony,
    Devices.Rigetti.AspenM3,
    Devices.OQC.Lucy,
]

for device_arn in device_arns:
    device = AwsDevice(arn=device_arn)
    try:
        task = device.run(bell, shots=shots)
        print('{device_name} task {task_state} {task_arn}'.format(
            device_name=device.name,
            task_state=task.state(),
            task_arn=task.id)
        )
    except Exception as e:
        print('{device_name}: {error}'.format(device_name=device.name, error=e))
