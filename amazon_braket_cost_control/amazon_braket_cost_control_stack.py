# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pathlib
from aws_cdk import (
    Duration,
    Stack,
    aws_cloudwatch,
    aws_cloudwatch_actions,
    aws_dynamodb,
    aws_events,
    aws_events_targets,
    aws_iam,
    aws_lambda,
    aws_lambda_event_sources,
    aws_logs,
    aws_sns,
    aws_sns_subscriptions
)
from constructs import Construct
from cdk_nag import NagSuppressions


class AmazonBraketCostControlStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        tag_key = kwargs.pop('tag_key')
        solution_id = kwargs.pop('solution_id')
        event_bus_name = kwargs.pop('event_bus_name')
        task_item_ttl_days = kwargs.pop('task_item_ttl_days')
        notification_email_address = kwargs.pop('notification_email_address')
        all_time_cost_limit = kwargs.pop('all_time_cost_limit')
        monthly_cost_limit = kwargs.pop('monthly_cost_limit')
        role_names_to_control = kwargs.pop('role_names_to_control')
        group_names_to_control = kwargs.pop('group_names_to_control')
        user_names_to_control = kwargs.pop('user_names_to_control')

        super().__init__(scope, construct_id, **kwargs)

        braket_event_bus = aws_events.EventBus.from_event_bus_name(self, 'braket-event-bus', event_bus_name)

        task_creation_rule = aws_events.Rule(
            self,
            'braket-task-creation-rule',
            event_pattern=aws_events.EventPattern(
                source=['aws.braket'],
                detail_type=['AWS API Call via CloudTrail'],
                detail={
                    'eventSource': ['braket.amazonaws.com'],
                    'eventName': ['CreateQuantumTask'],
                    'errorCode': [{"exists": False}]
                }
            ),
            enabled=True,
            rule_name='braket-cost-control-task-creation',
            event_bus=braket_event_bus
        )
        task_state_change_rule = aws_events.Rule(
            self,
            'braket-task-state-change-rule',
            event_pattern=aws_events.EventPattern(
                source=['aws.braket'],
                detail_type=['Braket Task State Change'],
                detail={
                    'eventName': ['MODIFY'],
                    'status': ['RUNNING', 'COMPLETED']
                }
            ),
            enabled=True,
            rule_name='braket-cost-control-task-state-change',
            event_bus=braket_event_bus
        )

        ttl_attribute_name = 'task_ttl'
        tasks_table = aws_dynamodb.Table(
            self,
            'tasks-table',
            table_name='braket-cost-control-tasks',
            partition_key=aws_dynamodb.Attribute(
                name='task_arn',
                type=aws_dynamodb.AttributeType.STRING
            ),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=aws_dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            time_to_live_attribute=ttl_attribute_name
        )

        cost_table = aws_dynamodb.Table(
            self,
            'cost-table',
            table_name='braket-cost-control-summary',
            partition_key=aws_dynamodb.Attribute(
                name='bin',
                type=aws_dynamodb.AttributeType.STRING
            ),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        aws_managed_lambda_execution_role = aws_iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
        log_retention_role = aws_iam.Role(
            self,
            'log-retention-role',
            role_name='braket-log-retention-role',
            assumed_by=aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            path='/service-role/',
            managed_policies=[aws_managed_lambda_execution_role],
            inline_policies={'log-retention-policy': aws_iam.PolicyDocument(statements=[
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=[
                        'logs:DeleteRetentionPolicy',
                        'logs:PutRetentionPolicy'
                    ],
                    resources=['*']
                ),
            ])}
        ).without_policy_updates()
        NagSuppressions.add_resource_suppressions(
            construct=log_retention_role,
            suppressions=[
                {'id': 'AwsSolutions-IAM4', 'reason': 'Intentional use of AWSLambdaBasicExecutionRole'},
                {'id': 'AwsSolutions-IAM5', 'reason': 'Used wildcards required for functionality'},
            ],
        )

        task_logger_lambda_role = aws_iam.Role(
            self,
            'task-logger-lambda-role',
            role_name='braket-cost-control-task-logger',
            assumed_by=aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            path='/service-role/',
            managed_policies=[aws_managed_lambda_execution_role],
            inline_policies={'task-logger-policy': aws_iam.PolicyDocument(statements=[
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['braket:GetQuantumTask'],
                    resources=['arn:aws:braket:*:{}:quantum-task/*'.format(self.account)]
                ),
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['s3:GetObject'],
                    resources=['arn:aws:s3:::*/*']
                ),
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['dynamodb:UpdateItem'],
                    resources=[tasks_table.table_arn]
                )
            ])}
        )
        NagSuppressions.add_resource_suppressions(
            construct=task_logger_lambda_role,
            suppressions=[
                {'id': 'AwsSolutions-IAM4', 'reason': 'Intentional use of AWSLambdaBasicExecutionRole'},
                {'id': 'AwsSolutions-IAM5', 'reason': 'Used wildcards required for functionality'},
            ],
        )
        task_logger_lambda = aws_lambda.DockerImageFunction(
            self,
            'task-logger-lambda',
            function_name='braket-cost-control-task-logger',
            role=task_logger_lambda_role,
            code=aws_lambda.DockerImageCode.from_image_asset(
                directory=pathlib.Path(__file__)
                .parent
                .parent
                .joinpath('lambda')
                .joinpath('quantum_task_logger')
                .resolve()
                .as_posix(),
            ),
            architecture=aws_lambda.Architecture.ARM_64,
            log_retention=aws_logs.RetentionDays.ONE_MONTH,
            log_retention_role=log_retention_role,
            environment={
                'TAG_KEY': tag_key,
                'SOLUTION_ID': solution_id,
                'TASKS_TABLE_NAME': tasks_table.table_name,
                'TASK_ITEM_TTL_DAYS': task_item_ttl_days,
                'TTL_ATTRIBUTE_NAME': ttl_attribute_name,
                'LOG_LEVEL': 'DEBUG',
                'POWERTOOLS_SERVICE_NAME': 'task logger'
            },
            memory_size=512,
            timeout=Duration.seconds(120),
        )
        task_state_change_rule.add_target(aws_events_targets.LambdaFunction(task_logger_lambda))
        task_creation_rule.add_target(aws_events_targets.LambdaFunction(task_logger_lambda))

        cost_meter_lambda_role = aws_iam.Role(
            self,
            'cost-meter-lambda-role',
            role_name='braket-cost-control-meter',
            assumed_by=aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            path='/service-role/',
            managed_policies=[aws_managed_lambda_execution_role],
            inline_policies={'cost-meter-policy': aws_iam.PolicyDocument(statements=[
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['dynamodb:UpdateItem'],
                    resources=[cost_table.table_arn]
                ),
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['cloudwatch:PutMetricData'],
                    resources=['*']
                ),
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['dynamodb:ListStreams'],
                    resources=['*']
                ),
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=[
                        'dynamodb:DescribeStream',
                        'dynamodb:GetRecords',
                        'dynamodb:GetShardIterator',
                    ],
                    resources=[tasks_table.table_stream_arn]
                ),
            ])}
        ).without_policy_updates()
        NagSuppressions.add_resource_suppressions(
            construct=cost_meter_lambda_role,
            suppressions=[
                {'id': 'AwsSolutions-IAM4', 'reason': 'Intentional use of AWSLambdaBasicExecutionRole'},
                {'id': 'AwsSolutions-IAM5', 'reason': 'Used wildcards required for functionality'},
            ]
        )
        cost_meter_lambda = aws_lambda.DockerImageFunction(
            self,
            'cost-meter-lambda',
            function_name='braket-cost-control-meter',
            role=cost_meter_lambda_role,
            code=aws_lambda.DockerImageCode.from_image_asset(
                directory=pathlib.Path(__file__)
                .parent
                .parent
                .joinpath('lambda')
                .joinpath('quantum_task_cost_meter')
                .resolve()
                .as_posix()
            ),
            architecture=aws_lambda.Architecture.ARM_64,
            log_retention=aws_logs.RetentionDays.ONE_MONTH,
            log_retention_role=log_retention_role,
            environment={
                'COST_TABLE_NAME': cost_table.table_name,
                'LOG_LEVEL': 'DEBUG',
                'POWERTOOLS_SERVICE_NAME': 'cost meter'
            },
            timeout=Duration.seconds(60),
            events=[
                aws_lambda_event_sources.DynamoEventSource(
                    tasks_table,
                    batch_size=5,
                    bisect_batch_on_error=True,
                    max_batching_window=Duration.seconds(1),
                    retry_attempts=10,
                    starting_position=aws_lambda.StartingPosition.TRIM_HORIZON,
                    filters=[
                        aws_lambda.FilterCriteria.filter({
                            'eventName': aws_lambda.FilterRule.is_equal('MODIFY'),
                            'dynamodb': {
                                'NewImage': {
                                    'cost': {'N': aws_lambda.FilterRule.exists()},
                                    'user_identity': {'S': aws_lambda.FilterRule.exists()}
                                }
                            }
                        })
                    ],
                    enabled=True
                )
            ]
        )
        NagSuppressions.add_resource_suppressions(
            construct=cost_meter_lambda_role,
            suppressions=[
                {'id': 'AwsSolutions-IAM4', 'reason': 'Intentional use of AWSLambdaBasicExecutionRole'},
                {'id': 'AwsSolutions-IAM5', 'reason': 'Used wildcards required for functionality'},
            ]
        )

        notification_topic = aws_sns.Topic(
            self,
            'notification-topic',
            topic_name='braket-cost-control-notification',
        )
        NagSuppressions.add_resource_suppressions(
            construct=notification_topic,
            suppressions=[
                {'id': 'AwsSolutions-SNS2', 'reason': 'No sensitive data is delivered on this topic and data is published via Email'},
            ]
        )
        notification_topic.add_subscription(aws_sns_subscriptions.EmailSubscription(notification_email_address))
        notification_topic.add_to_resource_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.DENY,
            principals=[aws_iam.AnyPrincipal()],
            actions=['sns:Publish'],
            resources=[notification_topic.topic_arn],
            conditions={
                'Bool': {'aws:SecureTransport': False}
            }
        ))
        notification_topic.add_to_resource_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            principals=[aws_iam.ServicePrincipal('cloudwatch.amazonaws.com')],
            actions=['sns:Publish'],
            resources=[notification_topic.topic_arn]
        ))

        cost_control_enforcement_policy = aws_iam.ManagedPolicy(
            self,
            'cost-control-enforcement-policy',
            managed_policy_name='braket-cost-control-enforcement',
            statements=[
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.DENY,
                    actions=['braket:CreateQuantumTask'],
                    resources=['*']
                )
            ]
        )

        cost_control_lambda_role = aws_iam.Role(
            self,
            'cost-control-lambda-role',
            role_name='braket-cost-control-action',
            assumed_by=aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            path='/service-role/',
            managed_policies=[aws_managed_lambda_execution_role],
            inline_policies={'cost-control-policy': aws_iam.PolicyDocument(statements=[
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=[
                        'iam:AttachRolePolicy',
                        'iam:AttachGroupPolicy',
                        'iam:AttachUserPolicy',
                        'iam:DetachRolePolicy',
                        'iam:DetachGroupPolicy',
                        'iam:DetachUserPolicy',
                    ],
                    resources=['*']
                ),
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=['sns:Publish'],
                    resources=[notification_topic.topic_arn]
                ),

            ])}
        )
        NagSuppressions.add_resource_suppressions(
            construct=cost_control_lambda_role,
            suppressions=[
                {'id': 'AwsSolutions-IAM4', 'reason': 'Intentional use of AWSLambdaBasicExecutionRole'},
                {'id': 'AwsSolutions-IAM5', 'reason': 'Used wildcards required for functionality'},
            ]
        )
        cost_control_lambda = aws_lambda.DockerImageFunction(
            self,
            'cost-control-lambda',
            function_name='braket-cost-control-action',
            role=cost_control_lambda_role,
            code=aws_lambda.DockerImageCode.from_image_asset(
                directory=pathlib.Path(__file__)
                .parent
                .parent
                .joinpath('lambda')
                .joinpath('quantum_task_cost_control')
                .resolve()
                .as_posix()
            ),
            architecture=aws_lambda.Architecture.ARM_64,
            log_retention=aws_logs.RetentionDays.ONE_MONTH,
            log_retention_role=log_retention_role,
            environment={
                'TOPIC_ARN': notification_topic.topic_arn,
                'POLICY_ARN': cost_control_enforcement_policy.managed_policy_arn,
                'ROLES': ','.join(role_names_to_control),
                'GROUPS': ','.join(group_names_to_control),
                'USERS': ','.join(user_names_to_control),
                'LOG_LEVEL': 'DEBUG',
                'POWERTOOLS_SERVICE_NAME': 'cost control'
            },
            timeout=Duration.seconds(60)
        )
        notification_topic.add_to_resource_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            principals=[aws_iam.ArnPrincipal(cost_control_lambda_role.role_arn)],
            actions=['sns:Publish'],
            resources=[notification_topic.topic_arn]
        ))

        cost_explorer_lambda_role = aws_iam.Role(
            self,
            'cost-explorer-lambda-role',
            role_name='braket-cost-explorer-report',
            assumed_by=aws_iam.ServicePrincipal('lambda.amazonaws.com'),
            path='/service-role/',
            managed_policies=[aws_managed_lambda_execution_role],
            inline_policies={'cost-control-policy': aws_iam.PolicyDocument(statements=[
                aws_iam.PolicyStatement(
                    effect=aws_iam.Effect.ALLOW,
                    actions=[
                        'ce:GetCost*',
                    ],
                    resources=['*']
                ),
            ])}
        )
        NagSuppressions.add_resource_suppressions(
            construct=cost_explorer_lambda_role,
            suppressions=[
                {'id': 'AwsSolutions-IAM4', 'reason': 'Intentional use of AWSLambdaBasicExecutionRole'},
                {'id': 'AwsSolutions-IAM5', 'reason': 'Used wildcards required for functionality'},
            ]
        )
        cost_explorer_lambda = aws_lambda.DockerImageFunction(
            self,
            'cost-explorer-lambda',
            function_name='braket-cost-explorer-report',
            role=cost_explorer_lambda_role,
            code=aws_lambda.DockerImageCode.from_image_asset(
                directory=pathlib.Path(__file__)
                .parent
                .parent
                .joinpath('lambda')
                .joinpath('cost_explorer_report')
                .resolve()
                .as_posix()
            ),
            architecture=aws_lambda.Architecture.ARM_64,
            log_retention=aws_logs.RetentionDays.ONE_MONTH,
            log_retention_role=log_retention_role,
            environment={
                'TAG_KEY': tag_key,
                'SOLUTION_ID': solution_id
            },
            timeout=Duration.seconds(60)
        )

        aws_logs.QueryDefinition(
            self,
            'braket-cost-control-logs-query',
            query_definition_name='braket-cost-control-logs-query',
            query_string=aws_logs.QueryString(
                fields=['@timestamp', 'function_name', 'level', 'message', '@message'],
                sort='@timestamp asc',
                filter='@message not like /(START|END|REPORT)./',
            ),
            log_groups=[
                task_logger_lambda.log_group,
                cost_meter_lambda.log_group,
                cost_control_lambda.log_group
            ]
        )

        task_cost_metric = aws_cloudwatch.Metric(
            namespace='/aws/braket',
            metric_name='QuantumTaskCost',
            period=Duration.days(1),
            statistic='Sum',
            unit=aws_cloudwatch.Unit.COUNT
        )
        task_cost_all_time_aggregate_metric = aws_cloudwatch.Metric(
            namespace='/aws/braket',
            metric_name='AggregatedQuantumTaskCostAllTime',
            period=Duration.minutes(1),
            statistic='Maximum',
            unit=aws_cloudwatch.Unit.COUNT
        )
        task_cost_monthly_aggregate_metric = aws_cloudwatch.Metric(
            namespace='/aws/braket',
            metric_name='AggregatedQuantumTaskCostMonth',
            period=Duration.minutes(1),
            statistic='Maximum',
            unit=aws_cloudwatch.Unit.COUNT
        )
        task_logger_lambda_metric = task_logger_lambda.metric_errors().with_(
            color=aws_cloudwatch.Color.RED,
            period=Duration.minutes(1)
        )
        cost_meter_lambda_metric = cost_meter_lambda.metric_errors().with_(
            color=aws_cloudwatch.Color.RED,
            period=Duration.minutes(1)
        )
        cost_control_lambda_metric = cost_control_lambda.metric_errors().with_(
            color=aws_cloudwatch.Color.RED,
            period=Duration.minutes(1)
        )

        task_cost_alarm_all_time = task_cost_all_time_aggregate_metric.create_alarm(
            self,
            'cost-control-alarm-all-time',
            alarm_name='Quantum Task Cost All-Time Aggregate',
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            threshold=float(all_time_cost_limit),
            evaluation_periods=(task_cost_all_time_aggregate_metric.period.to_minutes() * 60 * 24),
            datapoints_to_alarm=1,
            treat_missing_data=aws_cloudwatch.TreatMissingData.IGNORE,
            actions_enabled=True,
        )
        task_cost_alarm_monthly = task_cost_monthly_aggregate_metric.create_alarm(
            self,
            'cost-control-alarm-monthly',
            alarm_name='Quantum Task Cost Monthly Aggregate',
            threshold=float(monthly_cost_limit),
            evaluation_periods=(task_cost_monthly_aggregate_metric.period.to_minutes() * 60 * 24),
            datapoints_to_alarm=1,
            treat_missing_data=aws_cloudwatch.TreatMissingData.IGNORE,
            actions_enabled=True,
        )
        task_logger_lambda_alarm = task_logger_lambda_metric.create_alarm(
            self,
            'task-logger-lambda-alarm',
            alarm_name='Lambda Invocation Task Logger',
            threshold=1,
            evaluation_periods=(task_logger_lambda_metric.period.to_minutes() * 60),
            datapoints_to_alarm=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=aws_cloudwatch.TreatMissingData.NOT_BREACHING,
            actions_enabled=True,
        )
        cost_meter_lambda_alarm = cost_meter_lambda_metric.create_alarm(
            self,
            'cost-meter-lambda-alarm',
            alarm_name='Lambda Invocation Cost Meter',
            threshold=1,
            evaluation_periods=(cost_meter_lambda_metric.period.to_minutes() * 60),
            datapoints_to_alarm=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=aws_cloudwatch.TreatMissingData.NOT_BREACHING,
            actions_enabled=True,
        )
        cost_control_lambda_alarm = cost_control_lambda_metric.create_alarm(
            self,
            'cost-control-lambda-alarm',
            alarm_name='Lambda Invocation Cost Control Action',
            threshold=1,
            evaluation_periods=(cost_control_lambda_metric.period.to_minutes() * 60),
            datapoints_to_alarm=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=aws_cloudwatch.TreatMissingData.NOT_BREACHING,
            actions_enabled=True,
        )
        task_creation_rule_invocation_alarm = aws_cloudwatch.Alarm(
            self,
            'task-creation-rule-invocation-alarm',
            alarm_name='Braket Task Creation Rule Invocation Failures',
            threshold=1,
            evaluation_periods=60,
            datapoints_to_alarm=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=aws_cloudwatch.TreatMissingData.NOT_BREACHING,
            actions_enabled=True,
            metric=aws_cloudwatch.Metric(
                namespace='AWS/Events',
                metric_name='FailedInvocations',
                dimensions_map={'RuleName': task_creation_rule.rule_name},
                period=Duration.minutes(1),
                statistic='Maximum',
                unit=aws_cloudwatch.Unit.COUNT
            )
        )
        task_state_change_rule_invocation_alarm = aws_cloudwatch.Alarm(
            self,
            'task-state-change-rule-invocation-alarm',
            alarm_name='Braket Task State Change Rule Invocation Failures',
            threshold=1,
            evaluation_periods=60,
            datapoints_to_alarm=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=aws_cloudwatch.TreatMissingData.NOT_BREACHING,
            actions_enabled=True,
            metric=aws_cloudwatch.Metric(
                namespace='AWS/Events',
                metric_name='FailedInvocations',
                dimensions_map={'RuleName': task_state_change_rule.rule_name},
                period=Duration.minutes(1),
                statistic='Maximum',
                unit=aws_cloudwatch.Unit.COUNT
            )
        )

        task_cost_alarm_all_time.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))
        task_cost_alarm_monthly.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))
        task_logger_lambda_alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))
        cost_meter_lambda_alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))
        cost_control_lambda_alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))
        task_creation_rule_invocation_alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))
        task_state_change_rule_invocation_alarm.add_alarm_action(aws_cloudwatch_actions.SnsAction(notification_topic))

        dashboard = aws_cloudwatch.Dashboard(
            self,
            'cost-control-dashboard',
            dashboard_name='AmazonBraketCostControl',
            period_override=aws_cloudwatch.PeriodOverride.AUTO,
            start='-P1W',

        )
        dashboard.add_widgets(
            aws_cloudwatch.TextWidget(
                markdown=f"""
# Amazon Braket Cost Dashboard
This Amazon CloudWatch dashboard is created as part of the open-source cost control solution for Amazon Braket and provides a single view for your 
estimated resource costs related to your usage of Amazon Braket in this AWS account. Keep in mind that cost data displayed here are estimates and that
the AWS Billing Console provides access to a suite of features helping you set up your billing, retrieve and pay invoices, and analyze, organize, 
plan, and optimize your costs.

[button:Blog Post](https://aws.amazon.com/blogs/quantum-computing/introducing-a-cost-control-solution-for-amazon-braket/) 
[button:GitHub Repository](https://github.com/aws-samples/cost-control-for-amazon-braket)
[button:primary:AWS AWS Billing Console](https://us-east-1.console.aws.amazon.com/costmanagement)

``

## AWS Cost Explorer Data
Widgets in this section display data retrieved from the AWS Cost Explorer API. You need to enable AWS Cost Explorer in your account before you can 
use it. See the [AWS Cost Explorer documentation](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) to learn about the
process of enabling Cost Explorer and about the refresh rate of your cost data.
                """,
                width=24,
                height=6,
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.CustomWidget(
                title='AWS Cost Explorer Data Month-to-Date',
                function_arn=cost_explorer_lambda.function_arn,
                width=24,
                height=11
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.TextWidget(
                markdown="""
## Near Real-Time Quantum Task Cost Estimation
Near real-time cost estimates of on-demand simulator and quantum processing unit tasks - created either individually or in the context of an Amazon Braket Hybrid Job 
execution - recorded by the open-source cost control solution for Amazon Braket.
                """,
                width=24,
                height=2,
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.AlarmStatusWidget(
                title='Budget Alarm Status',
                alarms=[
                    task_cost_alarm_all_time,
                    task_cost_alarm_monthly,
                ],
                width=24,
                height=2,
            ),
        )
        dashboard.add_widgets(
            aws_cloudwatch.GaugeWidget(
                live_data=True,
                title='Quantum Task Cost All-Time Aggregate [$]',
                metrics=[task_cost_all_time_aggregate_metric],
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=float(all_time_cost_limit), label='$', show_units=True),
                legend_position=aws_cloudwatch.LegendPosition.HIDDEN,
                set_period_to_time_range=False,
                width=6,
                height=6,
            ),
            aws_cloudwatch.AlarmWidget(
                alarm=task_cost_alarm_all_time,
                title='Quantum Task Cost All-Time Aggregate',
                width=18,
                height=6,
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, label='$', show_units=True),
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.GaugeWidget(
                live_data=True,
                title='Quantum Task Cost Monthly Aggregate [$]',
                metrics=[task_cost_monthly_aggregate_metric],
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=float(monthly_cost_limit), label='$', show_units=True),
                legend_position=aws_cloudwatch.LegendPosition.HIDDEN,
                set_period_to_time_range=False,
                width=6,
                height=6,
            ),
            aws_cloudwatch.AlarmWidget(
                alarm=task_cost_alarm_monthly,
                title='Quantum Task Cost Monthly Aggregate',
                width=18,
                height=6,
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, label='$', show_units=True),
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.GraphWidget(
                live_data=True,
                title='Quantum Task Cost Per Day',
                left=[task_cost_metric],
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, label='$', show_units=True),
                set_period_to_time_range=True,
                width=8,
                height=6,
                view=aws_cloudwatch.GraphWidgetView.TIME_SERIES,
                stacked=True,
                legend_position=aws_cloudwatch.LegendPosition.HIDDEN,
            ),
            aws_cloudwatch.GraphWidget(
                live_data=True,
                title='Monthly Aggregate Of Recently Active Users [$]',
                left=[aws_cloudwatch.MathExpression(
                    label='TotalTaskCost',
                    expression='SELECT MAX(AggregatedQuantumTaskCostMonth) FROM SCHEMA(\"/aws/braket\", \"User Identity\") GROUP BY \"User Identity\"'
                )],
                set_period_to_time_range=True,
                width=8,
                height=6,
                view=aws_cloudwatch.GraphWidgetView.PIE
            ),
            aws_cloudwatch.GraphWidget(
                live_data=True,
                title='Monthly Aggregate Of Recently Used Devices [$]',
                left=[aws_cloudwatch.MathExpression(
                    label='TotalTaskCost',
                    expression='SELECT MAX(AggregatedQuantumTaskCostMonth) FROM SCHEMA(\"/aws/braket\", \"Device\") GROUP BY \"Device\"'
                )],
                set_period_to_time_range=True,
                width=8,
                height=6,
                view=aws_cloudwatch.GraphWidgetView.PIE
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.TextWidget(
                markdown="""
## Operational Metrics
Metrics in this section help you monitor the open-source cost control solution is up and running, and operating as expected.
                """,
                width=24,
                height=2,
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.AlarmStatusWidget(
                title='Operational Alarm Status',
                alarms=[
                    task_logger_lambda_alarm,
                    cost_meter_lambda_alarm,
                    cost_control_lambda_alarm,
                    task_state_change_rule_invocation_alarm,
                    task_creation_rule_invocation_alarm
                ],
                width=24,
                height=2,
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.AlarmWidget(
                title='{} Lambda Invocation Errors'.format(task_logger_lambda.function_name),
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=1.5, show_units=True),
                alarm=task_logger_lambda_alarm,
                width=8,
                height=4
            ),
            aws_cloudwatch.AlarmWidget(
                title='{} Lambda Invocation Errors'.format(cost_meter_lambda.function_name),
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=1.5, show_units=True),
                alarm=cost_meter_lambda_alarm,
                width=8,
                height=4
            ),
            aws_cloudwatch.AlarmWidget(
                title='{} Lambda Invocation Errors'.format(cost_control_lambda.function_name),
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=1.5, show_units=True),
                alarm=cost_control_lambda_alarm,
                width=8,
                height=4
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.GraphWidget(
                title='Average Event Ingestion-To-Invocation Latency',
                left=[
                    aws_cloudwatch.Metric(
                        namespace='AWS/Events',
                        metric_name='IngestionToInvocationStartLatency',
                        period=Duration.hours(1),
                        statistic='Average',
                        unit=aws_cloudwatch.Unit.COUNT
                    )
                ],
                live_data=True,
                view=aws_cloudwatch.GraphWidgetView.TIME_SERIES,
                width=8,
                height=4
            ),
            aws_cloudwatch.AlarmWidget(
                title='Task Creation Event Rule Failed Invocations',
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=1.5, label='Count', show_units=True),
                alarm=task_creation_rule_invocation_alarm,
                width=8,
                height=4
            ),
            aws_cloudwatch.AlarmWidget(
                title='Task State Change Event Rule Failed Invocations',
                left_y_axis=aws_cloudwatch.YAxisProps(min=0, max=1.5, label='Count', show_units=True),
                alarm=task_state_change_rule_invocation_alarm,
                width=8,
                height=4
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.GraphWidget(
                title='{} Consumed Read/Write Capacity Units'.format(tasks_table.table_name),
                left=[
                    aws_cloudwatch.Metric(
                        namespace='AWS/DynamoDB',
                        metric_name='ConsumedReadCapacityUnits',
                        dimensions_map={'TableName': tasks_table.table_name},
                        period=Duration.days(1),
                        statistic='Sum',
                        unit=aws_cloudwatch.Unit.COUNT
                    ),
                    aws_cloudwatch.Metric(
                        namespace='AWS/DynamoDB',
                        metric_name='ConsumedWriteCapacityUnits',
                        dimensions_map={'TableName': tasks_table.table_name},
                        period=Duration.days(1),
                        statistic='Sum',
                        unit=aws_cloudwatch.Unit.COUNT
                    )
                ],
                live_data=True,
                width=8,
                height=4,
                view=aws_cloudwatch.GraphWidgetView.TIME_SERIES
            ),
            aws_cloudwatch.GraphWidget(
                title='{} Consumed Read/Write Capacity Units'.format(cost_table.table_name),
                left=[
                    aws_cloudwatch.Metric(
                        namespace='AWS/DynamoDB',
                        metric_name='ConsumedReadCapacityUnits',
                        dimensions_map={'TableName': cost_table.table_name},
                        period=Duration.days(1),
                        statistic='Sum',
                        unit=aws_cloudwatch.Unit.COUNT
                    ),
                    aws_cloudwatch.Metric(
                        namespace='AWS/DynamoDB',
                        metric_name='ConsumedWriteCapacityUnits',
                        dimensions_map={'TableName': cost_table.table_name},
                        period=Duration.days(1),
                        statistic='Sum',
                        unit=aws_cloudwatch.Unit.COUNT
                    )
                ],
                live_data=True,
                width=8,
                height=4,
                view=aws_cloudwatch.GraphWidgetView.TIME_SERIES
            ),
            aws_cloudwatch.GraphWidget(
                title='SNS Email Notifications',
                left=[
                    aws_cloudwatch.Metric(
                        namespace='AWS/SNS',
                        metric_name='NumberOfNotificationsDelivered',
                        dimensions_map={'TopicName': notification_topic.topic_name},
                        period=Duration.hours(1),
                        statistic='Sum',
                        unit=aws_cloudwatch.Unit.COUNT
                    ),
                    aws_cloudwatch.Metric(
                        namespace='AWS/SNS',
                        metric_name='NumberOfNotificationsFailed',
                        dimensions_map={'TopicName': notification_topic.topic_name},
                        period=Duration.hours(1),
                        statistic='Sum',
                        unit=aws_cloudwatch.Unit.COUNT
                    ),
                ],
                live_data=True,
                width=8,
                height=4,
                view=aws_cloudwatch.GraphWidgetView.TIME_SERIES
            ),
        )
        dashboard.add_widgets(
            aws_cloudwatch.LogQueryWidget(
                title='{} Memory Consumption [MB]'.format(task_logger_lambda.function_name),
                log_group_names=[task_logger_lambda.log_group.log_group_name],
                query_lines=[
                    'fields @message',
                    'filter @type = "REPORT"',
                    'stats '
                    'max(@maxMemoryUsed / 1024 / 1024) as max,'
                    'avg(@maxMemoryUsed / 1024 / 1024) as avg,'
                    'min(@maxMemoryUsed / 1024 / 1024) as min'
                ],
                view=aws_cloudwatch.LogQueryVisualizationType.TABLE,
                width=8,
                height=3,
            ),
            aws_cloudwatch.LogQueryWidget(
                title='{} Memory Consumption [MB]'.format(cost_meter_lambda.function_name),
                log_group_names=[cost_meter_lambda.log_group.log_group_name],
                query_lines=[
                    'fields @message',
                    'filter @type = "REPORT"',
                    'stats '
                    'max(@maxMemoryUsed / 1024 / 1024) as max,'
                    'avg(@maxMemoryUsed / 1024 / 1024) as avg,'
                    'min(@maxMemoryUsed / 1024 / 1024) as min'
                ],
                view=aws_cloudwatch.LogQueryVisualizationType.TABLE,
                width=8,
                height=3,
            ),
            aws_cloudwatch.LogQueryWidget(
                title='{} Memory Consumption [MB]'.format(cost_control_lambda.function_name),
                log_group_names=[cost_control_lambda.log_group.log_group_name],
                query_lines=[
                    'fields @message',
                    'filter @type = "REPORT"',
                    'stats '
                    'max(@maxMemoryUsed / 1024 / 1024) as max,'
                    'avg(@maxMemoryUsed / 1024 / 1024) as avg,'
                    'min(@maxMemoryUsed / 1024 / 1024) as min'
                ],
                view=aws_cloudwatch.LogQueryVisualizationType.TABLE,
                width=8,
                height=3,
            )
        )
        dashboard.add_widgets(
            aws_cloudwatch.LogQueryWidget(
                title='{} Execution Duration [s]'.format(task_logger_lambda.function_name),
                log_group_names=[task_logger_lambda.log_group.log_group_name],
                query_lines=[
                    'fields @message',
                    'filter @type = "REPORT"',
                    'stats '
                    'max(@billedDuration / 1000) as max,'
                    'avg(@billedDuration / 1000) as avg,'
                    'min(@billedDuration / 1000) as min'
                ],
                view=aws_cloudwatch.LogQueryVisualizationType.TABLE,
                width=8,
                height=3,
            ),
            aws_cloudwatch.LogQueryWidget(
                title='{} Execution Duration [s]'.format(cost_meter_lambda.function_name),
                log_group_names=[cost_meter_lambda.log_group.log_group_name],
                query_lines=[
                    'fields @message',
                    'filter @type = "REPORT"',
                    'stats '
                    'max(@billedDuration / 1000) as max,'
                    'avg(@billedDuration / 1000) as avg,'
                    'min(@billedDuration / 1000) as min'
                ],
                view=aws_cloudwatch.LogQueryVisualizationType.TABLE,
                width=8,
                height=3,
            ),
            aws_cloudwatch.LogQueryWidget(
                title='{} Execution Duration [s]'.format(cost_control_lambda.function_name),
                log_group_names=[cost_control_lambda.log_group.log_group_name],
                query_lines=[
                    'fields @message',
                    'filter @type = "REPORT"',
                    'stats '
                    'max(@billedDuration / 1000) as max,'
                    'avg(@billedDuration / 1000) as avg,'
                    'min(@billedDuration / 1000) as min'
                ],
                view=aws_cloudwatch.LogQueryVisualizationType.TABLE,
                width=8,
                height=3,
            )
        )

        alarm_state_change_rule = aws_events.Rule(
            self,
            'alarm-state-change-rule',
            event_pattern=aws_events.EventPattern(
                source=['aws.cloudwatch'],
                detail_type=['CloudWatch Alarm State Change'],
                resources=[
                    task_cost_alarm_all_time.alarm_arn,
                    task_cost_alarm_monthly.alarm_arn,
                ]
            ),
            enabled=True,
            rule_name='braket-cost-control-alarm-state-change',
        )
        alarm_state_change_rule.add_target(aws_events_targets.LambdaFunction(cost_control_lambda))
