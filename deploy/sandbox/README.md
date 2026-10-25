# REDLINE Secure Sandbox Runner Specification

## Overview

The `redline-sandbox-runner:latest` container image provides the execution environment for untrusted candidate code and adversarial verification in REDLINE.

In accordance with Stage P2-3 and `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`, candidate execution occurs inside an ephemeral container configured with:
- Non-root user execution (`UID 1000:GID 1000`)
- Dropped Linux capabilities (`--cap-drop=ALL`)
- Prevention of privilege escalation (`--security-opt=no-new-privileges`)
- Disabled network access by default (`--network none`)
- Read-only root filesystem (`--read-only`)
- Ephemeral in-memory scratch space (`--tmpfs /tmp:rw,noexec,nosuid,size=64m`)
- Isolated canonical workspace mount (`-v <workspace>:/workspace:rw`)
- Strict CPU, PID, memory, and timeout limits enforced by server-side policy

---

## 1. Verified Upstream Base Image

The image definition uses an official Python base image pinned by its immutable multi-architecture OCI image index SHA-256 digest:

- **Base Image:** `python:3.11-slim-bookworm`
- **OCI Index Digest:** `sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf`
- **Linux/amd64 Platform Digest:** `sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199`
- **Upstream Source:** `docker-library/repo-info` (`remote/3.11-slim-bookworm.md`)

*Note on Reproducibility:* The image must not be claimed as fully reproducible until a local build has completed, all build inputs have been pinned and hashed, and the resulting image digest is verified and recorded in the audit trail.

---

## 2. Pinned Dependencies

Only the minimal packages required for executing candidate tests and capturing structured results are included:

| Package | Version | Purpose |
| :--- | :--- | :--- |
| `iniconfig` | `2.0.0` | Ini file parser dependency for pytest |
| `packaging` | `24.1` | Core Python package utilities |
| `pluggy` | `1.5.0` | Plugin manager dependency for pytest |
| `pytest` | `8.3.3` | Test execution runner |
| `pytest-json-report` | `1.5.0` | Structured JSON report emission |
| `coverage` | `7.6.1` | Deterministic coverage tracking |

No compiler toolchains, package manager build dependencies, or external networking utilities are retained in the final image layers.

---

## 3. Build & Digest Recording Instructions

### Build Command
Once Docker Desktop is active, build the image using:

```bash
docker build \
  --file deploy/sandbox/Dockerfile \
  --tag redline-sandbox-runner:latest \
  deploy/sandbox/
```

### Inspecting and Recording the Image Digest
After building, extract the immutable image digest and inspect its configuration:

```bash
# Obtain image ID and RepoDigests
docker inspect --format='{{index .RepoDigests 0}}' redline-sandbox-runner:latest

# Record image ID
docker inspect --format='{{.Id}}' redline-sandbox-runner:latest
```

---

## 4. Execution Hardening Flags

The container runner must always be invoked using the flags constructed by `SecureSandboxBackend.build_container_args()`:

```bash
docker run \
  --name <container_name> \
  --rm \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user 1000:1000 \
  -v <canonical_workspace>:/workspace:rw \
  -w /workspace \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --network none \
  --cpus <cpu_limit> \
  --pids-limit <pids_limit> \
  --memory <max_memory_bytes>b \
  redline-sandbox-runner:latest \
  <command...>
```

---

## 5. Disk Quota: Reactive Measurement vs. Proactive Quotas

### Current Status: Reactive Post-Execution Measurement
- The existing implementation (`SecureSandboxBackend.measure_workspace_disk_usage`) traverses the workspace **reactively after execution finishes**.
- It uses non-following traversal (`os.lstat`), prunes directory junctions/symlinks, deduplicates hard links via `(st_dev, st_ino)`, and fails closed on inaccessible paths or quota violations.
- **Limitation:** Standard host bind mounts (`-v`) write directly to the underlying host filesystem. Therefore, the reactive measurement cannot prevent host disk exhaustion *during* execution if a rogue candidate attempts rapid unbounded writes.
- The backend truthfully reports:
  - `hard_quota_enforced: False`
  - `is_reactive_measurement: True`

### Future Work: Proactive Kernel-Enforced Quotas
To enforce proactive hard write limits during runtime, future enhancements may implement:
1. **Loopback Volume Backing:** A dedicated pre-sized ext4 loopback image formatted with XFS/ext4 project quotas (`xfs_quota` / `repquota`).
2. **Container Tmpfs Workspaces:** Ephemeral candidate workspaces mounted directly on a size-bounded `tmpfs` volume (`--tmpfs /workspace:rw,size=256m,uid=1000,gid=1000`), where writes are blocked at the VFS block-allocation layer upon exceeding capacity.
