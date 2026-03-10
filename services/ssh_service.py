"""SSH Service for remote server connections and command execution."""

import paramiko
from paramiko import RSAKey, Ed25519Key, ECDSAKey
import os
import json
import threading
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def load_private_key(key_path: str, password: Optional[str] = None) -> Any:
    """Load a private key file, trying multiple formats.

    Supports both old PEM format and newer OpenSSH format.

    Args:
        key_path: Path to the private key file
        password: Optional passphrase for encrypted keys

    Returns:
        A paramiko key object

    Raises:
        paramiko.SSHException: If key cannot be loaded
    """
    key_path = os.path.expanduser(key_path)

    # Try each key type in order (most common first)
    key_classes = [
        (Ed25519Key, "Ed25519"),
        (RSAKey, "RSA"),
        (ECDSAKey, "ECDSA"),
    ]

    last_error = None
    for key_class, key_name in key_classes:
        try:
            return key_class.from_private_key_file(key_path, password=password)
        except paramiko.SSHException as e:
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue

    # If all failed, raise the last error
    raise paramiko.SSHException(f"Could not load key: {last_error}")


@dataclass
class SlurmConfig:
    """SLURM configuration for job submission."""
    enabled: bool = False
    partition: str = ""
    time: str = "24:00:00"  # Default 24 hours
    cpus: int = 1
    memory: str = "8G"
    account: str = ""
    extra_options: str = ""  # Additional sbatch options

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "partition": self.partition,
            "time": self.time,
            "cpus": self.cpus,
            "memory": self.memory,
            "account": self.account,
            "extra_options": self.extra_options,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SlurmConfig":
        return cls(
            enabled=data.get("enabled", False),
            partition=data.get("partition", ""),
            time=data.get("time", "24:00:00"),
            cpus=data.get("cpus", 1),
            memory=data.get("memory", "8G"),
            account=data.get("account", ""),
            extra_options=data.get("extra_options", ""),
        )


@dataclass
class ServerConfig:
    """Configuration for a remote server."""
    name: str
    hostname: str
    username: str
    port: int = 22
    key_path: Optional[str] = None
    password: Optional[str] = None  # Not recommended, use keys
    work_dir: str = "~"
    description: str = ""
    scheduler: str = "none"  # none, slurm, pbs, lsf
    slurm_config: Optional[SlurmConfig] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hostname": self.hostname,
            "username": self.username,
            "port": self.port,
            "key_path": self.key_path,
            "work_dir": self.work_dir,
            "description": self.description,
            "scheduler": self.scheduler,
            "slurm_config": self.slurm_config.to_dict() if self.slurm_config else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServerConfig":
        slurm_data = data.get("slurm_config")
        return cls(
            name=data["name"],
            hostname=data["hostname"],
            username=data["username"],
            port=data.get("port", 22),
            key_path=data.get("key_path"),
            password=data.get("password"),
            work_dir=data.get("work_dir", "~"),
            description=data.get("description", ""),
            scheduler=data.get("scheduler", "none"),
            slurm_config=SlurmConfig.from_dict(slurm_data) if slurm_data else None,
        )


@dataclass
class PipelineRun:
    """Represents a running or completed pipeline."""
    run_id: str
    pipeline_name: str
    server_name: str
    status: str  # pending, running, completed, failed, cancelled
    started_at: datetime
    completed_at: Optional[datetime] = None
    work_dir: str = ""
    log_file: str = ""
    parameters: Dict = field(default_factory=dict)
    processes: List[Dict] = field(default_factory=list)
    error_message: str = ""
    slurm_job_id: Optional[str] = None  # SLURM job ID if submitted via SLURM

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "server_name": self.server_name,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "work_dir": self.work_dir,
            "log_file": self.log_file,
            "parameters": self.parameters,
            "processes": self.processes,
            "error_message": self.error_message,
            "slurm_job_id": self.slurm_job_id,
        }


class SSHService:
    """Service for managing SSH connections and remote command execution."""

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize the SSH service.

        Args:
            config_dir: Directory to store server configurations
        """
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(__file__), "..", "data", "ssh_config")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.servers_file = self.config_dir / "servers.json"
        self.runs_file = self.config_dir / "pipeline_runs.json"

        self._connections: Dict[str, paramiko.SSHClient] = {}
        self._lock = threading.Lock()

    # Server Management

    def get_servers(self) -> List[ServerConfig]:
        """Get all configured servers."""
        if not self.servers_file.exists():
            return []

        with open(self.servers_file, "r") as f:
            data = json.load(f)

        return [ServerConfig.from_dict(s) for s in data.get("servers", [])]

    def save_server(self, server: ServerConfig) -> None:
        """Save a server configuration."""
        servers = self.get_servers()

        # Update existing or add new
        existing_idx = next((i for i, s in enumerate(servers) if s.name == server.name), None)
        if existing_idx is not None:
            servers[existing_idx] = server
        else:
            servers.append(server)

        with open(self.servers_file, "w") as f:
            json.dump({"servers": [s.to_dict() for s in servers]}, f, indent=2)

    def delete_server(self, name: str) -> bool:
        """Delete a server configuration."""
        servers = self.get_servers()
        servers = [s for s in servers if s.name != name]

        with open(self.servers_file, "w") as f:
            json.dump({"servers": [s.to_dict() for s in servers]}, f, indent=2)

        # Close any existing connection
        self.disconnect(name)
        return True

    def get_server(self, name: str) -> Optional[ServerConfig]:
        """Get a server by name."""
        servers = self.get_servers()
        return next((s for s in servers if s.name == name), None)

    # Connection Management

    def connect(self, server_name: str) -> paramiko.SSHClient:
        """Get or create an SSH connection to a server."""
        with self._lock:
            if server_name in self._connections:
                # Check if connection is still alive
                try:
                    transport = self._connections[server_name].get_transport()
                    if transport and transport.is_active():
                        return self._connections[server_name]
                except:
                    pass
                # Connection dead, remove it
                del self._connections[server_name]

            server = self.get_server(server_name)
            if not server:
                raise ValueError(f"Server '{server_name}' not found")

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": server.hostname,
                "port": server.port,
                "username": server.username,
            }

            if server.key_path:
                key_path = os.path.expanduser(server.key_path)
                if os.path.exists(key_path):
                    connect_kwargs["key_filename"] = key_path
                    # Allow agent and look for keys as fallback
                    connect_kwargs["allow_agent"] = True
                    connect_kwargs["look_for_keys"] = True
            elif server.password:
                connect_kwargs["password"] = server.password
            else:
                # No explicit key or password - try SSH agent
                connect_kwargs["allow_agent"] = True
                connect_kwargs["look_for_keys"] = True

            client.connect(**connect_kwargs)
            self._connections[server_name] = client
            return client

    def disconnect(self, server_name: str) -> None:
        """Disconnect from a server."""
        with self._lock:
            if server_name in self._connections:
                try:
                    self._connections[server_name].close()
                except:
                    pass
                del self._connections[server_name]

    def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        with self._lock:
            for client in self._connections.values():
                try:
                    client.close()
                except:
                    pass
            self._connections.clear()

    def test_connection(self, server: ServerConfig) -> tuple[bool, str]:
        """Test connection to a server.

        Returns:
            Tuple of (success, message)
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": server.hostname,
                "port": server.port,
                "username": server.username,
                "timeout": 10,
            }

            if server.key_path:
                key_path = os.path.expanduser(server.key_path)
                if os.path.exists(key_path):
                    connect_kwargs["key_filename"] = key_path
                    # Allow agent and look for keys as fallback
                    connect_kwargs["allow_agent"] = True
                    connect_kwargs["look_for_keys"] = True
                else:
                    return False, f"SSH key not found: {key_path}"
            elif server.password:
                connect_kwargs["password"] = server.password
            else:
                # No explicit key or password - try SSH agent
                connect_kwargs["allow_agent"] = True
                connect_kwargs["look_for_keys"] = True

            client.connect(**connect_kwargs)

            # Test command execution
            stdin, stdout, stderr = client.exec_command("echo 'Connection successful' && hostname")
            output = stdout.read().decode().strip()

            client.close()
            return True, f"Connected successfully. Host: {output.split()[-1] if output else 'unknown'}"

        except paramiko.AuthenticationException:
            return False, "Authentication failed. Check username and SSH key/password."
        except paramiko.SSHException as e:
            return False, f"SSH error: {str(e)}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    # Command Execution

    def exec_command(
        self,
        server_name: str,
        command: str,
        timeout: int = 30
    ) -> tuple[int, str, str]:
        """Execute a command on a remote server.

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        client = self.connect(server_name)

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

        exit_code = stdout.channel.recv_exit_status()
        stdout_str = stdout.read().decode()
        stderr_str = stderr.read().decode()

        return exit_code, stdout_str, stderr_str

    def exec_command_async(
        self,
        server_name: str,
        command: str,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> paramiko.Channel:
        """Execute a command asynchronously (for long-running processes).

        Returns:
            The SSH channel for monitoring
        """
        client = self.connect(server_name)

        channel = client.get_transport().open_session()
        channel.exec_command(command)

        if on_output:
            def read_output():
                while not channel.exit_status_ready():
                    if channel.recv_ready():
                        data = channel.recv(1024).decode()
                        on_output(data)

            thread = threading.Thread(target=read_output)
            thread.daemon = True
            thread.start()

        return channel

    # Pipeline Management

    def launch_pipeline(
        self,
        server_name: str,
        pipeline_path: str,
        work_dir: str,
        params: Dict,
        webhook_url: Optional[str] = None,
        resume: bool = False,
        extra_args: str = "",
        use_slurm: bool = False,
        slurm_options: Optional[Dict] = None,
    ) -> PipelineRun:
        """Launch a Nextflow pipeline on a remote server.

        Args:
            server_name: Name of the server to run on
            pipeline_path: Path to the pipeline (main.nf or GitHub URL)
            work_dir: Working directory for the pipeline
            params: Dictionary of parameters
            webhook_url: URL for Nextflow weblog updates
            resume: Whether to resume a previous run
            extra_args: Additional Nextflow arguments
            use_slurm: Whether to submit via SLURM
            slurm_options: SLURM options (partition, time, cpus, memory, etc.)

        Returns:
            PipelineRun object with run information
        """
        import uuid

        run_id = str(uuid.uuid4())[:8]
        run_name = f"run_{run_id}"

        # Build parameter arguments
        param_args = []
        for key, value in params.items():
            if value is not None and value != "":
                # Handle boolean parameters
                if isinstance(value, bool):
                    if value:
                        param_args.append(f"--{key}")
                else:
                    param_args.append(f"--{key} '{value}'")

        # Build the Nextflow command
        nf_command_parts = [
            "nextflow", "run", pipeline_path,
            "-name", run_name,
        ]

        if webhook_url:
            nf_command_parts.extend(["-with-weblog", webhook_url])

        if resume:
            nf_command_parts.append("-resume")

        nf_command_parts.extend(param_args)

        if extra_args:
            nf_command_parts.append(extra_args)

        nf_command = " ".join(nf_command_parts)
        log_file = f"{work_dir}/{run_name}.log"
        slurm_job_id = None

        if use_slurm and slurm_options:
            # Submit via SLURM sbatch
            slurm_job_id = self._submit_slurm_job(
                server_name=server_name,
                run_name=run_name,
                work_dir=work_dir,
                command=nf_command,
                log_file=log_file,
                slurm_options=slurm_options,
            )
        else:
            # Run directly with nohup
            full_command = f"cd {work_dir} && nohup {nf_command} > {log_file} 2>&1 & echo $!"

            exit_code, stdout, stderr = self.exec_command(server_name, full_command, timeout=60)

            if exit_code != 0:
                raise RuntimeError(f"Failed to launch pipeline: {stderr}")

        # Create run record
        run = PipelineRun(
            run_id=run_id,
            pipeline_name=os.path.basename(pipeline_path),
            server_name=server_name,
            status="running",
            started_at=datetime.now(),
            work_dir=work_dir,
            log_file=log_file,
            parameters=params,
            slurm_job_id=slurm_job_id,
        )

        # Save run
        self._save_run(run)

        return run

    def _submit_slurm_job(
        self,
        server_name: str,
        run_name: str,
        work_dir: str,
        command: str,
        log_file: str,
        slurm_options: Dict,
    ) -> str:
        """Submit a job via SLURM sbatch.

        Returns:
            SLURM job ID
        """
        # Build sbatch script
        partition = slurm_options.get("partition", "")
        time_limit = slurm_options.get("time", "24:00:00")
        cpus = slurm_options.get("cpus", 1)
        memory = slurm_options.get("memory", "8G")
        account = slurm_options.get("account", "")
        extra = slurm_options.get("extra_options", "")

        sbatch_script = f"""#!/bin/bash
#SBATCH --job-name={run_name}
#SBATCH --output={log_file}
#SBATCH --error={log_file}
#SBATCH --time={time_limit}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={memory}
"""
        if partition:
            sbatch_script += f"#SBATCH --partition={partition}\n"
        if account:
            sbatch_script += f"#SBATCH --account={account}\n"
        if extra:
            sbatch_script += f"#SBATCH {extra}\n"

        sbatch_script += f"""
cd {work_dir}
{command}
"""

        # Write script to server and submit
        script_path = f"{work_dir}/{run_name}.sbatch"

        # Create script file
        create_script_cmd = f"cat > {script_path} << 'SBATCH_EOF'\n{sbatch_script}\nSBATCH_EOF"
        exit_code, _, stderr = self.exec_command(server_name, create_script_cmd, timeout=30)

        if exit_code != 0:
            raise RuntimeError(f"Failed to create SLURM script: {stderr}")

        # Submit job
        submit_cmd = f"sbatch {script_path}"
        exit_code, stdout, stderr = self.exec_command(server_name, submit_cmd, timeout=30)

        if exit_code != 0:
            raise RuntimeError(f"Failed to submit SLURM job: {stderr}")

        # Parse job ID from output (e.g., "Submitted batch job 12345")
        job_id = stdout.strip().split()[-1]
        return job_id

    # SLURM Job Management

    def get_slurm_queue(self, server_name: str, user_only: bool = True) -> List[Dict]:
        """Get SLURM queue status.

        Args:
            server_name: Name of the server
            user_only: Only show jobs for the current user

        Returns:
            List of job dictionaries
        """
        cmd = "squeue --format='%.18i %.9P %.50j %.8u %.8T %.10M %.9l %.6D %R' --noheader"
        if user_only:
            cmd += " --me"

        exit_code, stdout, stderr = self.exec_command(server_name, cmd, timeout=30)

        if exit_code != 0:
            return []

        jobs = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 8:
                jobs.append({
                    "job_id": parts[0],
                    "partition": parts[1],
                    "name": parts[2],
                    "user": parts[3],
                    "state": parts[4],
                    "time": parts[5],
                    "time_limit": parts[6],
                    "nodes": parts[7],
                    "nodelist": parts[8] if len(parts) > 8 else "",
                })

        return jobs

    def get_slurm_job_status(self, server_name: str, job_id: str) -> Optional[Dict]:
        """Get status of a specific SLURM job.

        Returns:
            Job info dictionary or None if not found
        """
        # First try squeue (for running/pending jobs)
        cmd = f"squeue -j {job_id} --format='%.18i %.9P %.50j %.8u %.8T %.10M %.9l %.6D %R' --noheader"
        exit_code, stdout, stderr = self.exec_command(server_name, cmd, timeout=30)

        if exit_code == 0 and stdout.strip():
            parts = stdout.strip().split()
            if len(parts) >= 5:
                return {
                    "job_id": parts[0],
                    "partition": parts[1],
                    "name": parts[2],
                    "user": parts[3],
                    "state": parts[4],
                    "time": parts[5] if len(parts) > 5 else "",
                }

        # Try sacct for completed jobs
        cmd = f"sacct -j {job_id} --format=JobID,JobName,State,ExitCode,Elapsed --noheader --parsable2"
        exit_code, stdout, stderr = self.exec_command(server_name, cmd, timeout=30)

        if exit_code == 0 and stdout.strip():
            for line in stdout.strip().split("\n"):
                parts = line.split("|")
                if len(parts) >= 3 and parts[0] == job_id:
                    return {
                        "job_id": parts[0],
                        "name": parts[1],
                        "state": parts[2],
                        "exit_code": parts[3] if len(parts) > 3 else "",
                        "elapsed": parts[4] if len(parts) > 4 else "",
                    }

        return None

    def cancel_slurm_job(self, server_name: str, job_id: str) -> tuple[bool, str]:
        """Cancel a SLURM job.

        Returns:
            Tuple of (success, message)
        """
        cmd = f"scancel {job_id}"
        exit_code, stdout, stderr = self.exec_command(server_name, cmd, timeout=30)

        if exit_code == 0:
            return True, f"Job {job_id} cancelled"
        else:
            return False, f"Failed to cancel job: {stderr}"

    def check_slurm_available(self, server_name: str) -> tuple[bool, str]:
        """Check if SLURM is available on the server."""
        try:
            exit_code, stdout, stderr = self.exec_command(
                server_name,
                "sinfo --version",
                timeout=10
            )
            if exit_code == 0:
                return True, stdout.strip()
            return False, "SLURM not found"
        except Exception as e:
            return False, str(e)

    def get_slurm_partitions(self, server_name: str) -> List[str]:
        """Get available SLURM partitions."""
        try:
            exit_code, stdout, stderr = self.exec_command(
                server_name,
                "sinfo -h -o '%P'",
                timeout=10
            )
            if exit_code == 0:
                partitions = [p.strip().rstrip("*") for p in stdout.strip().split("\n") if p.strip()]
                return partitions
            return []
        except:
            return []

    def get_runs(self, limit: int = 50) -> List[PipelineRun]:
        """Get recent pipeline runs."""
        if not self.runs_file.exists():
            return []

        with open(self.runs_file, "r") as f:
            data = json.load(f)

        runs = []
        for r in data.get("runs", [])[-limit:]:
            run = PipelineRun(
                run_id=r["run_id"],
                pipeline_name=r["pipeline_name"],
                server_name=r["server_name"],
                status=r["status"],
                started_at=datetime.fromisoformat(r["started_at"]),
                completed_at=datetime.fromisoformat(r["completed_at"]) if r.get("completed_at") else None,
                work_dir=r.get("work_dir", ""),
                log_file=r.get("log_file", ""),
                parameters=r.get("parameters", {}),
                processes=r.get("processes", []),
                error_message=r.get("error_message", ""),
                slurm_job_id=r.get("slurm_job_id"),
            )
            runs.append(run)

        return runs

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        """Get a specific run by ID."""
        runs = self.get_runs(limit=1000)
        return next((r for r in runs if r.run_id == run_id), None)

    def update_run(self, run: PipelineRun) -> None:
        """Update a pipeline run."""
        self._save_run(run)

    def _save_run(self, run: PipelineRun) -> None:
        """Save a pipeline run to the runs file."""
        runs = self.get_runs(limit=1000)

        # Update existing or add new
        existing_idx = next((i for i, r in enumerate(runs) if r.run_id == run.run_id), None)
        if existing_idx is not None:
            runs[existing_idx] = run
        else:
            runs.append(run)

        with open(self.runs_file, "w") as f:
            json.dump({"runs": [r.to_dict() for r in runs]}, f, indent=2)

    def get_log_tail(self, server_name: str, log_file: str, lines: int = 100) -> str:
        """Get the tail of a log file from a remote server."""
        try:
            exit_code, stdout, stderr = self.exec_command(
                server_name,
                f"tail -n {lines} {log_file}",
                timeout=10
            )
            if exit_code == 0:
                return stdout
            return f"Error reading log: {stderr}"
        except Exception as e:
            return f"Error: {str(e)}"

    def check_nextflow_installed(self, server_name: str) -> tuple[bool, str]:
        """Check if Nextflow is installed on a server."""
        try:
            exit_code, stdout, stderr = self.exec_command(
                server_name,
                "nextflow -version",
                timeout=30
            )
            if exit_code == 0:
                version = stdout.strip().split("\n")[0] if stdout else "unknown"
                return True, version
            return False, "Nextflow not found"
        except Exception as e:
            return False, str(e)
