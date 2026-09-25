import paramiko
import io
from typing import Optional

class SSHClient:
    """Simple wrapper around paramiko SSH client.
    Reads connection settings from environment variables:
    SSH_HOST, SSH_USER, SSH_KEY_PATH (optional, defaults to password auth via SSH_PASSWORD).
    """

    def __init__(self) -> None:
        import os
        self.host = os.getenv("SSH_HOST", "127.0.0.1")
        self.user = os.getenv("SSH_USER", "ubuntu")
        self.password = os.getenv("SSH_PASSWORD")
        self.key_path = os.getenv("SSH_KEY_PATH")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._connect()

    def _connect(self) -> None:
        if self.key_path:
            self.client.connect(self.host, username=self.user, key_filename=self.key_path)
        else:
            self.client.connect(self.host, username=self.user, password=self.password)

    def exec_command(self, command: str, input_data: Optional[str] = None) -> str:
        """Execute a command on the remote host.
        If ``input_data`` is provided, it is sent to the command's stdin.
        Returns the command's stdout as a string.
        """
        stdin, stdout, stderr = self.client.exec_command(command)
        if input_data:
            stdin.write(input_data)
            stdin.channel.shutdown_write()
        out = stdout.read().decode()
        err = stderr.read().decode()
        if err:
            raise RuntimeError(f"SSH command error: {err}")
        return out

    def close(self) -> None:
        self.client.close()
