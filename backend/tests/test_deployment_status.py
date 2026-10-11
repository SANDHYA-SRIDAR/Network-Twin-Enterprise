import asyncio
import unittest
from unittest.mock import patch

from app.api.deployment import deployment_status
from app.services.ssh_client import (
    SSHAuthenticationError,
    SSHConfigurationMissingError,
    SSHUnreachableError,
)


class DeploymentStatusTests(unittest.TestCase):
    def run_status(self):
        return asyncio.run(deployment_status())

    def test_missing_configuration_is_classified(self):
        with patch("app.api.deployment.SSHClient", side_effect=SSHConfigurationMissingError()):
            result = self.run_status()
        self.assertFalse(result["connected"])
        self.assertEqual(result["vm_status"], "Configuration Missing")

    def test_unreachable_host_is_classified(self):
        with patch("app.api.deployment.SSHClient", side_effect=SSHUnreachableError()):
            result = self.run_status()
        self.assertFalse(result["connected"])
        self.assertEqual(result["vm_status"], "Unreachable")

    def test_authentication_failure_is_classified(self):
        with patch("app.api.deployment.SSHClient", side_effect=SSHAuthenticationError()):
            result = self.run_status()
        self.assertFalse(result["connected"])
        self.assertEqual(result["vm_status"], "Authentication Failed")

    def test_ssh_success_but_mininet_check_failure_is_not_ready(self):
        client = unittest.mock.Mock()
        client.exec_command.side_effect = RuntimeError("command failed")
        with patch("app.api.deployment.SSHClient", return_value=client):
            result = self.run_status()
        self.assertTrue(result["connected"])
        self.assertEqual(result["vm_status"], "Connected")
        self.assertEqual(result["mininet_status"], "Mininet Not Ready")
        client.close.assert_called_once()

    def test_success_preserves_legacy_connected_field(self):
        client = unittest.mock.Mock()
        client.exec_command.return_value = "/usr/bin/mn\n"
        with patch("app.api.deployment.SSHClient", return_value=client):
            result = self.run_status()
        self.assertTrue(result["connected"])
        self.assertEqual(result["vm_status"], "Connected")
        self.assertEqual(result["mininet_status"], "Ready")


if __name__ == "__main__":
    unittest.main()
