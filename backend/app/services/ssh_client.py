from typing import Optional

import paramiko

from app.config import settings


class SSHConfigurationMissingError(RuntimeError):
    pass


class SSHUnreachableError(RuntimeError):
    pass


class SSHAuthenticationError(RuntimeError):
    pass

class SSHClient:
    """Simple wrapper around paramiko SSH client.
    Reads SSH connection settings from the application configuration. Secrets never leave
    this process and are not included in exception messages or API responses.
    """

    def __init__(self) -> None:
        self.host = settings.ssh_host
        self.user = settings.ssh_user
        self.password = settings.ssh_password
        self.key_path = settings.ssh_key_path
        self.port = settings.ssh_port
        self.timeout = settings.ssh_connect_timeout
        if not self.host or not self.user or (not self.key_path and not self.password):
            raise SSHConfigurationMissingError("SSH host, user, and key or password are required")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            self._connect()
        except paramiko.AuthenticationException as exc:
            self.client.close()
            raise SSHAuthenticationError("SSH authentication failed") from exc
        except (paramiko.BadHostKeyException, paramiko.SSHException, OSError, TimeoutError) as exc:
            self.client.close()
            raise SSHUnreachableError("SSH host is unreachable or refused the connection") from exc

    def _connect(self) -> None:
        if self.key_path:
            self.client.connect(self.host, port=self.port, username=self.user, key_filename=self.key_path, timeout=self.timeout, banner_timeout=self.timeout, auth_timeout=self.timeout, allow_agent=False, look_for_keys=False)
        else:
            self.client.connect(self.host, port=self.port, username=self.user, password=self.password, timeout=self.timeout, banner_timeout=self.timeout, auth_timeout=self.timeout, allow_agent=False, look_for_keys=False)

    def exec_command(self, command: str, input_data: Optional[str] = None) -> str:
        """Execute a command on the remote host.
        If ``input_data`` is provided, it is sent to the command's stdin.
        Returns the command's stdout as a string.
        """
        stdin, stdout, stderr = self.client.exec_command(command, timeout=self.timeout)
        if input_data:
            stdin.write(input_data)
            stdin.channel.shutdown_write()
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode()
        err = stderr.read().decode()
        if exit_status != 0 or err:
            raise RuntimeError("SSH command failed")
        return out

    def close(self) -> None:
        self.client.close()
