import os
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.data_classes import event_source, CloudWatchDashboardCustomWidgetEvent
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

logger = Logger(log_uncaught_exceptions=True)

cost_explorer = boto3.client('ce')

DOCS = """
## Braket Cost Explorer Report Custom Widget
Queries the AWS Cost Explorer API to get Braket and SageMaker cost and usage information.
Displays these information in a CloudWatch dashboard custom widget.
"""

MONITORED_SERVICES_INFO = {
    'Amazon Braket': {
        'comment': "Includes Braket resource costs like <b>quantum tasks</b>, <b>hybrid jobs</b>, and device <b>reservations</b> (see <a href='https://aws.amazon.com/braket/pricing/'>Amazon Braket Pricing</a>).",
        'amount': '$0.00'
    },
    'Amazon SageMaker': {
        'comment': "Includes costs for <b>Amazon Braket Managed Notebook instances</b> but also all other SageMaker resources consumed (see <a href='https://aws.amazon.com/sagemaker/pricing/'>Amazon SageMaker Pricing</a>).",
        'amount': '$0.00'
    },
    'AWS Cost Explorer': {
        'comment': "Includes costs for the <b>GetCostAndUsage</b> API used to display cost data in this widget but also for all other invocations of the AWS Cost Explorer API (see <a href='https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/'>AWS Cost Explorer Pricing</a>).",
        'amount': '$0.00'
    }
}
SOLUTION_RESOURCES_INFO = "Tagged resources used by the cost control solution<sup>**</sup>."


@event_source(data_class=CloudWatchDashboardCustomWidgetEvent)
@logger.inject_lambda_context()
def handler(event: CloudWatchDashboardCustomWidgetEvent, context: LambdaContext) -> str:
    try:
        logger.info(event.raw_event)
        if 'describe' in event:
            return DOCS

        metric = 'UnblendedCost'
        end_date = date.today()
        if end_date.day == 1:
            end_date = end_date - timedelta(days=1)
        start_date = end_date.replace(day=1).isoformat()
        end_date = end_date.isoformat()
        response = cost_explorer.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=[metric],
            Filter={
                'Or': [
                    {
                        'Dimensions': {
                            'Key': 'SERVICE',
                            'Values': list(MONITORED_SERVICES_INFO.keys()),
                        }
                    },
                    {
                        'Tags': {
                            'Key': 'solution',
                            'Values': ['BraketCostControlSolution/1.0.0'],
                        }
                    }
                ]
            },
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )
        response_time = response['ResponseMetadata']['HTTPHeaders']['date']
        for result in response['ResultsByTime']:
            for group in result['Groups']:
                service = group['Keys'][0]
                amount = '$' + str(Decimal(group['Metrics'][metric]['Amount']).quantize(Decimal('.01'), ROUND_HALF_UP))
                comment = SOLUTION_RESOURCES_INFO
                if MONITORED_SERVICES_INFO.get(service) and MONITORED_SERVICES_INFO.get(service).get('comment'):
                    comment = MONITORED_SERVICES_INFO.get(service).get('comment')
                MONITORED_SERVICES_INFO[service] = {
                    'amount': amount,
                    'comment': comment
                }

        html = f"""<br>Retrieved using the 
        <a href='https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html'>GetCostAndUsage</a> API 
        with start date <b>{start_date}</b> and end date <b>{end_date}</b>. Response timestamp: {response_time}.
        """
        html += "<br><br><table>"
        html += f"<tr><th>Service</th><th>Amount*</th><th>Additional Information</th></tr>"

        for key, value in MONITORED_SERVICES_INFO.items():
            html += f"""
            <tr>
            <td>{key}</td>
            <td>{value.get('amount')}</td>
            <td>{value.get('comment')}</td>
            </tr>
            """

        html += "</table>"
        html += f"""
        <br> <b><sup>*</sup></b>: The table shows <i>unblended</i> costs rounded to $0.01. 
        See <a href='https://aws.amazon.com/blogs/aws-cloud-financial-management/understanding-your-aws-cost-datasets-a-cheat-sheet/'>this blogpost</a> for more information about AWS cost datasets.
        <br> <b><sup>**</sup></b>: To monitor charges for these resources, you need to first <a href='https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html'>activate user-defined cost allocation tags</a> for the tag key "{os.environ['TAG_KEY']}".
        """
        return html
    except Exception as e:
        logger.exception(e)
        raise
