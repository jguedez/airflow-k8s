# Copyright 2021 jguedez
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

from charm import AirflowCharm
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(AirflowCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_get_common_airflow_layer(self):
        expected = {
            "summary": "test-container layer",
            "description": "pebble config layer for test-container",
            "services": {
                "test-container": {
                    "override": "replace",
                    "summary": "test-container",
                    "command": "/entrypoint test-command",
                    "startup": "enabled",
                    "environment": {
                        "AIRFLOW__CORE__EXECUTOR": "LocalExecutor",
                        "AIRFLOW__CORE__FERNET_KEY": "",
                        "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION": "true",
                        "AIRFLOW__CORE__LOAD_EXAMPLES": "true",
                        "AIRFLOW__API__AUTH_BACKEND": "airflow.api.auth.backend.basic_auth",
                    },
                }
            },
        }
        self.assertEqual(
            self.harness.charm._get_common_airflow_layer("test-container", "test-command"),
            expected,
        )
