# pdg.nvidia_gpu

Host-level NVIDIA GPU enablement for Rocky/RHEL 9 HTCondor workers. It does two things:

1. Installs the NVIDIA driver from the CUDA repo (VSC recipe, el9) via the `@nvidia-driver:latest-dkms` module stream plus `kernel-devel`, then reboots so the kernel module loads.
2. Installs `nvidia-container-toolkit` and wires the NVIDIA runtime into Docker (for GPU tools that run under Docker). Apptainer/Singularity needs nothing here; it uses `--nv`.

HTCondor GPU advertising (`use feature : GPUs` and the `GPUGeneration` ClassAd) is **not** in this role. It is deployed alongside the other condor `config.d` snippets by the worker playbook (`04-vib-compute-workers.yml`), matching how `10-vib.conf` is managed.

## Requirements

- An NVIDIA GPU attached to the host.
- Docker already installed (this role restarts it; run it after the docker role).

## Key variables

See `defaults/main.yml`. Common toggles:

- `nvidia_gpu_enable_docker_runtime` (default `true`): install the toolkit and configure Docker. Set `false` for apptainer-only nodes.
- `nvidia_gpu_reboot` (default `true`): reboot after a driver (re)install.

## Tags

`gpu_driver`, `gpu_docker` (both also tagged `gpu`).

## Usage

```yaml
- role: pdg.nvidia_gpu
  when: gpu_enabled | default(false)
```
