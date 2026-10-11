import unittest

from app.models.network import IPConfiguration, InterfaceDefinition, LinkDefinition, NetworkDefinition, NodeDefinition
from app.services.network_validation import validate_network_definition


class NetworkSchemaTests(unittest.TestCase):
    def test_valid_network_passes_validation(self):
        network = NetworkDefinition(
            name="Test LAN",
            nodes=[
                NodeDefinition(
                    id="r1",
                    name="Core Router",
                    device_type="router",
                    interfaces=[
                        InterfaceDefinition(
                            id="eth0",
                            name="eth0",
                            type="ethernet",
                            ip_configuration=IPConfiguration(ip_address="10.0.0.1", subnet_mask="255.255.255.0", gateway="10.0.0.254"),
                        )
                    ],
                ),
                NodeDefinition(
                    id="pc1",
                    name="Client",
                    device_type="pc",
                    interfaces=[
                        InterfaceDefinition(
                            id="eth0",
                            name="eth0",
                            type="ethernet",
                            ip_configuration=IPConfiguration(ip_address="10.0.0.2", subnet_mask="255.255.255.0", gateway="10.0.0.254"),
                        )
                    ],
                ),
            ],
            links=[
                LinkDefinition(id="l1", source_node_id="r1", target_node_id="pc1", cable_type="straight-through", bandwidth_mbps=1000, delay_ms=1, packet_loss_pct=0)
            ],
        )
        self.assertEqual(validate_network_definition(network), [])

    def test_invalid_ip_and_duplicate_link_fail_validation(self):
        network = NetworkDefinition(
            name="Broken",
            nodes=[
                NodeDefinition(
                    id="n1",
                    name="Bad node",
                    device_type="switch",
                    interfaces=[
                        InterfaceDefinition(
                            id="eth0",
                            name="eth0",
                            ip_configuration=IPConfiguration(ip_address="10.0.0.1", subnet_mask="255.255.255.0", gateway="10.0.0.5"),
                        )
                    ],
                ),
                NodeDefinition(
                    id="n2",
                    name="Bad node 2",
                    device_type="pc",
                    interfaces=[
                        InterfaceDefinition(
                            id="eth0",
                            name="eth0",
                            ip_configuration=IPConfiguration(ip_address="10.0.0.1", subnet_mask="255.255.255.0", gateway="10.0.0.5"),
                        )
                    ],
                ),
            ],
            links=[
                LinkDefinition(id="l1", source_node_id="n1", target_node_id="n1", cable_type="straight-through", bandwidth_mbps=0, delay_ms=-1, packet_loss_pct=101)
            ],
        )
        errors = validate_network_definition(network)
        self.assertTrue(any(item.code == "duplicate_ip" for item in errors))
        self.assertTrue(any(item.code == "self_link" for item in errors))


if __name__ == "__main__":
    unittest.main()
