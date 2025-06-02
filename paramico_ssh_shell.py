import time
from typing import Optional

import paramiko
from paramiko.channel import Channel
from paramiko.client import SSHClient


class SSHConnection:
    def __init__(self, host, username, password, port=22, buffer_size=4096):
        self.host: str = host
        self.username: str = username
        self.password: str = password
        self.port: int = port
        self.buffer_size: int = buffer_size
        self._ssh_client: Optional["SSHClient"] = None
        self._shell: Optional["Channel"] = None

    def connect(self, disable_pagination: bool = False) -> None:
        try:
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh_client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                look_for_keys=False
            )
            self._shell = self._ssh_client.invoke_shell()
            time.sleep(1)
            self._flush_buffer()
            if disable_pagination:
                self._shell.send('terminal length 0\n')
                time.sleep(1)
        except Exception as e:
            raise ConnectionError(f"[!] SSH connection failed: {e}")

    def reconnect(self, retry_count=3, retry_interval=2) -> None:
        print(f"[*] Attempting to reconnect to {self.host}...")
        for attempt in range(1, retry_count + 1):
            try:
                self.disconnect()
                self.connect()
                print(f"[+] Reconnected on attempt {attempt}.")
                return
            except Exception as e:
                print(f"[!] Attempt {attempt} failed: {e}")
                time.sleep(retry_interval)
        raise ConnectionError("[!] Reconnection attempts exhausted.")

    def _flush_buffer(self):
        if self._shell and self._shell.recv_ready():
            self._shell.recv(self.buffer_size)

    def send_command(self, command: str, wait_time=1.0):
        if not self.is_connected:
            raise ConnectionError("SSH connection is not active.")
        self._shell.send(s=command + '\n')
        time.sleep(wait_time)
        output = ''
        while self._shell.recv_ready():
            output += self._shell.recv(nbytes=self.buffer_size).decode(errors='ignore')
            time.sleep(0.1)
        return output.strip()

    def disconnect(self) -> None:
        """Disconnects active SSH connection."""
        if self._shell:
            self._shell.close()
            self._shell = None
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None

    @property
    def is_connected(self) -> bool:
        """Indicates whether SSH connection still active."""
        return self._ssh_client is not None and self._shell is not None


class ShellInterface:
    def __init__(self, connection: "SSHConnection", prompt='#'):
        self.connection = connection
        self.prompt = prompt
        self._connect()

    def _connect(self) -> None:
        if not self.connection.is_connected:
            self.connection.connect()

    def __del__(self) -> None:
        self.connection.disconnect()

    def run_cmd(self, command: str, retry_count: int = 0) -> str:
        """Run command with retry on failure."""
        attempts = 1 if not retry_count else retry_count
        for attempt in range(attempts):
            try:
                return self.connection.send_command(command=command)
            except Exception as e:
                print(f"[!] Command failed: {e}")
                attempt += 1
                self.connection.reconnect()
        raise RuntimeError(f"[!] Failed to run command after '{retry_count}' retries.")

    def interact(self) -> None:
        """Optional interactive loop."""
        try:
            print(f"\n[+] Connected to {self.connection.host}. Type commands or 'exit' to quit.\n")
            while True:
                cmd = input(f"{self.connection.host}{self.prompt} ").strip()
                if cmd.lower() in ['exit', 'quit']:
                    break
                output = self.run_cmd(command=cmd)
                for line in parse_cmd_output(output=output):
                    print(line)
        except Exception as e:
            print(f"[!] Error: {e}")


def parse_cmd_output(output: str) -> list[str]:
    """Trivial shell output parser.

    It just splits lines and removes empty entries.
    """
    return [line.strip() for line in output.splitlines() if line.strip()]


# ===== MAIN EXECUTION =====
if __name__ == "__main__":
    conn = SSHConnection(
        host="192.168.2.184",
        username="testuser",
        password="12345"
    )

    shell = ShellInterface(connection=conn, prompt='$')

    # Non-interactive usage
    output = shell.run_cmd(command="uname -a", retry_count=2)
    print("\nParsed Output:")
    print(parse_cmd_output(output=output), sep="\n")
