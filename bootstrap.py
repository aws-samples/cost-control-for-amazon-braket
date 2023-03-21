# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os

context_file = open('cdk.json')
context_data = json.load(context_file)
account_id = context_data['context']['awsAccountId']
braket_regions = context_data['context']['braketRegions']

for region in braket_regions:
    print(f'Bootstrapping your AWS environment: account {account_id}, region {region}')
    os.system(f'cdk bootstrap aws://{account_id}/{region}')

context_file.close()
