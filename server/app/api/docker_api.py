"""Docker Engine API wrapper via Unix socket (no external dependencies)."""

import json
import select
import socket
import time
import logging

_SOCKET_PATH = "/var/run/docker.sock"
_CRLF = "\r\n"

logger = logging.getLogger("reelmind.docker_api")


class DockerAPI:
    """Minimal Docker Engine API client using Unix socket."""

    def __init__(self, socket_path=None):
        self.socket_path = socket_path or _SOCKET_PATH

    def _request(self, method, path, body=None, raw=False):
        """Send HTTP request via Unix socket to Docker Engine API."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(30)
        s.connect(self.socket_path)

        json_body = json.dumps(body).encode() if body else None

        req = f"{method} {path} HTTP/1.1{_CRLF}Host: localhost{_CRLF}"
        if json_body:
            req += f"Content-Type: application/json{_CRLF}Content-Length: {len(json_body)}{_CRLF}"
        req += _CRLF

        s.sendall(req.encode())
        if json_body:
            s.sendall(json_body)

        # Read all response data with select-based timeout
        resp = b""
        first_read = True
        while True:
            # Longer initial wait for first response, shorter for subsequent
            timeout = 3.0 if first_read else 0.5
            ready, _, _ = select.select([s], [], [], timeout)
            if not ready:
                break
            chunk = s.recv(65536)
            if not chunk:
                break
            resp += chunk
            first_read = False
            # If we have the full HTTP response (headers + body), check
            # for end of chunked transfer (terminal "0\r\n\r\n")
            if b"\r\n\r\n" in resp:
                idx = resp.find(b"\r\n\r\n")
                body_seen = resp[idx + 4:]
                if body_seen.rstrip().endswith(b"0"):
                    break
        s.close()

        if not resp:
            return 0, ""

        # Split headers and body
        separator = b"\r\n\r\n"
        header_end = resp.find(separator)
        if header_end < 0:
            return 0, resp.decode("utf-8", errors="replace")[:200]

        headers = resp[:header_end].decode()
        body_data = resp[header_end + 4:]
        status_line = headers.split(_CRLF)[0]
        status_code = int(status_line.split(" ")[1])

        # If chunked, parse it
        is_chunked = any(
            line.lower().startswith("transfer-encoding:")
            and "chunked" in line.lower()
            for line in headers.split(_CRLF)[1:]
        )

        if is_chunked:
            parsed = b""
            remaining = body_data
            while remaining:
                line_end = remaining.find(b"\r\n")
                if line_end < 0:
                    break
                try:
                    chunk_size = int(remaining[:line_end].strip(), 16)
                except ValueError:
                    break
                if chunk_size == 0:
                    break
                parsed += remaining[line_end + 2: line_end + 2 + chunk_size]
                remaining = remaining[line_end + 2 + chunk_size + 2:]
            body_data = parsed

        if raw:
            return status_code, body_data
        return status_code, body_data.decode("utf-8", errors="replace")

    def inspect_container(self, container_name):
        """Get container details."""
        status, body = self._request("GET", f"/containers/{container_name}/json")
        if status == 200:
            return json.loads(body)
        return None

    def force_remove_container(self, container_name):
        """Force-remove a running container."""
        status, _ = self._request("DELETE", f"/containers/{container_name}?force=true&v=1")
        return status == 204

    def rename_container(self, old_name, new_name):
        """Rename a container."""
        status, _ = self._request("POST", f"/containers/{old_name}/rename?name={new_name}")
        return status == 204 or status == 200

    def container_exists(self, container_name):
        """Check if a container with the given name exists."""
        c = self.inspect_container(container_name)
        return c is not None
    def ping(self) -> bool:
        """Check if Docker Engine is reachable."""
        try:
            status, _ = self._request("GET", "/_ping")
            return status == 200
        except Exception:
            return False

    def list_containers(self, all_containers: bool = True) -> list[dict]:
        """List all containers."""
        path = f"/containers/json?all={'true' if all_containers else 'false'}"
        status, body = self._request("GET", path)
        if status == 200:
            return json.loads(body)
        return []

    @staticmethod
    def _strip_docker_frames(data: bytes) -> str:
        """Strip Docker 8-byte frame headers from multiplexed log stream."""
        result = bytearray()
        i = 0
        while i < len(data):
            if i + 8 > len(data):
                break
            frame_size = (data[i+4] << 24) | (data[i+5] << 16) | (data[i+6] << 8) | data[i+7]
            i += 8
            if frame_size == 0:
                break
            end = min(i + frame_size, len(data))
            result.extend(data[i:end])
            i = end
        return result.decode("utf-8", errors="replace")

    def container_logs(self, name: str, tail: int = 200) -> str:
        """Fetch container logs via Docker Engine API."""
        path = f"/containers/{name}/logs?stdout=true&stderr=true&tail={tail}"
        try:
            status, body_bytes = self._request("GET", path, raw=True)
            if status == 200:
                return self._strip_docker_frames(body_bytes)
        except Exception as e:
            logger.warning("container_logs(%s) failed: %s", name, e)
        return ""

    def _build_create_config(self, container, new_port, name):
        """Build create config from an existing container config with new port."""
        config = container["Config"]
        host_config = container["HostConfig"]
        port_str = str(new_port)

        exposed_ports = {f"{port_str}/tcp": {}}
        port_bindings = {f"{port_str}/tcp": [{"HostIp": "0.0.0.0", "HostPort": port_str}]}

        env_list = list(config.get("Env", []))
        updated_env = []
        port_found = False
        for e in env_list:
            if e.startswith("PORT="):
                updated_env.append(f"PORT={new_port}")
                port_found = True
            else:
                updated_env.append(e)
        if not port_found:
            updated_env.append(f"PORT={new_port}")
        if "HOST=0.0.0.0" not in updated_env:
            updated_env.append("HOST=0.0.0.0")

        create_config = {
            "Hostname": config.get("Hostname", name),
            "AttachStdin": False, "AttachStdout": False, "AttachStderr": False,
            "Tty": config.get("Tty", False),
            "OpenStdin": config.get("OpenStdin", False), "StdinOnce": False,
            "Env": updated_env,
            "Cmd": config.get("Cmd"),
            "Entrypoint": config.get("Entrypoint"),
            "Image": config.get("Image"),
            "Labels": config.get("Labels", {}),
            "WorkingDir": config.get("WorkingDir", "/"),
            "ExposedPorts": exposed_ports,
            "HostConfig": {
                "Binds": host_config.get("Binds", []),
                "PortBindings": port_bindings,
                "RestartPolicy": {"Name": "always"},
                "NetworkMode": host_config.get("NetworkMode", "reelmind-network"),
                "Init": host_config.get("Init", False),
                "Memory": host_config.get("Memory", 0),
                "MemoryReservation": host_config.get("MemoryReservation", 0),
                "NanoCpus": host_config.get("NanoCpus", 0),
                "ShmSize": host_config.get("ShmSize", 0),
            },
        }

        mounts = container.get("Mounts", [])
        if mounts:
            binds = []
            for m in mounts:
                src = m.get("Source", "")
                dst = m.get("Destination", "")
                mode = m.get("Mode", "rw")
                if src and dst:
                    binds.append(f"{src}:{dst}:{mode}")
            if binds:
                create_config["HostConfig"]["Binds"] = binds

        networks = container.get("NetworkSettings", {}).get("Networks", {})
        nc = {}
        for net_name, net_cfg in networks.items():
            aliases = list(net_cfg.get("Aliases", []))
            if name and name not in aliases:
                aliases.append(name)
            nc[net_name] = {"Aliases": aliases}
        create_config["NetworkingConfig"] = {"EndpointsConfig": nc}

        return create_config

    def create_container(self, create_config):
        """Create a container by name."""
        status, body = self._request("POST", "/containers/create", create_config)
        result = json.loads(body) if body else {}
        if status in (201,):
            return result.get("Id"), result.get("Warnings", [])
        err = result.get("message", str(result))
        logger.error("Create failed (status=%s): %s", status, err)
        return None, err

    def create_named_container(self, name, create_config):
        """Create a container with a specific name."""
        status, body = self._request("POST", f"/containers/create?name={name}", create_config)
        result = json.loads(body) if body else {}
        if status in (201,) and "Id" in result:
            return result["Id"], result.get("Warnings", [])
        err = result.get("message", str(result))
        logger.error("Create '%s' failed (status=%s): %s", name, status, err)
        return None, err

    def start_container(self, container_id):
        """Start a container."""
        status, body = self._request("POST", f"/containers/{container_id}/start")
        if status not in (204, 304):
            logger.warning("start_container returned %s: %s", status, body[:200])
            return False
        return True

    def recreate_server_container(self, new_port):
        """Recreate reelmind-server container with new port mapping.

        Strategy:
        1. Rename old 'reelmind-server' -> 'reelmind-server-old'
        2. Create new container as 'reelmind-server' with new port
        3. Start the new container
        4. Force-remove 'reelmind-server-old'
        """
        old_name = "reelmind-server"
        backup_name = "reelmind-server-old"

        # Step 0: Clean up leftover from previous failed restart
        if self.container_exists(backup_name):
            logger.info("Cleaning up leftover backup container '%s'", backup_name)
            self.force_remove_container(backup_name)

        # Step 1: Rename old -> backup
        logger.info("Renaming '%s' -> '%s'", old_name, backup_name)
        if not self.rename_container(old_name, backup_name):
            raise Exception(f"Failed to rename '{old_name}' to '{backup_name}'")

        # Step 2: Inspect backup to get config
        container = self.inspect_container(backup_name)
        if not container:
            self.rename_container(backup_name, old_name)
            raise Exception(f"Container '{backup_name}' not found after rename")

        # Step 3: Create new container with original name
        create_config = self._build_create_config(container, new_port, old_name)
        logger.info("Creating new container '%s' on port %s...", old_name, new_port)

        cid, warnings = self.create_named_container(old_name, create_config)
        if not cid:
            self.rename_container(backup_name, old_name)
            raise Exception(f"Failed to create new container: {warnings}")

        logger.info("Starting new container '%s' (%s)...", old_name, cid[:12])
        if not self.start_container(cid):
            self.force_remove_container(cid)
            self.rename_container(backup_name, old_name)
            raise Exception("Failed to start new container")

        logger.info("New container '%s' started on port %s", old_name, new_port)

        # Step 4: Remove old backup container
        logger.info("Removing old container '%s'...", backup_name)
        try:
            self.force_remove_container(backup_name)
        except Exception as e:
            logger.warning("Could not remove old container '%s': %s", backup_name, e)

        return True


def restart_with_new_port(new_port):
    """Restart reelmind-server with a new port mapping."""
    return DockerAPI().recreate_server_container(new_port)
