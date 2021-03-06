#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from system_test import testcase
from system_test.tests import ActionTest
from system_test.actions import BaseActions


@testcase(groups=['system_test', 'system_test.redeploy_after_reset'])
class RedeployAfterReset(ActionTest, BaseActions):
    """Case deploy Environment

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        6. Run OSTF
    """

    actions_order = [
        'prepare_admin_node_with_slaves',
        'create_env',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'health_check',
        'reset_cluster',
        'network_check',
        'deploy_cluster',
        'network_check',
        'health_check',
    ]
