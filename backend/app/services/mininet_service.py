import random
from datetime import datetime
from app.models.mininet import MininetTelemetry, NodeTelemetry, LinkTelemetry

class MininetService:
    @staticmethod
    def get_mock_telemetry() -> MininetTelemetry:
        """
        Simulates fetching real-time telemetry data from the Mininet instance 
        running on the Ubuntu VM.
        """
        nodes = [
            NodeTelemetry(
                node_id="Router-1941", 
                cpu_usage_pct=round(random.uniform(15.0, 45.0), 2), 
                mem_usage_pct=round(random.uniform(30.0, 60.0), 2), 
                status="online"
            ),
            NodeTelemetry(
                node_id="PC-PT", 
                cpu_usage_pct=round(random.uniform(5.0, 20.0), 2), 
                mem_usage_pct=round(random.uniform(20.0, 40.0), 2), 
                status="online"
            ),
        ]
        
        links = [
            LinkTelemetry(
                source="Router-1941", 
                target="PC-PT", 
                latency_ms=round(random.uniform(0.5, 2.5), 2), 
                throughput_mbps=round(random.uniform(800.0, 950.0), 2), 
                packet_loss_pct=round(random.uniform(0.0, 0.1), 4), 
                status="active"
            )
        ]
        
    @staticmethod
    def get_real_telemetry() -> MininetTelemetry:
        """Fetch real telemetry from the Ubuntu VM via SSH.
        This method uses the SSHClient utility to execute a remote script
        that returns JSON matching the MininetTelemetry model.
        """
        from app.services.ssh_client import SSHClient
        ssh = SSHClient()
        # The remote script should output JSON telemetry data
        output = ssh.exec_command("python3 /home/ubuntu/get_telemetry.py")
        # Parse the JSON into the Pydantic model
        import json
        data = json.loads(output)
        return MininetTelemetry(**data)

