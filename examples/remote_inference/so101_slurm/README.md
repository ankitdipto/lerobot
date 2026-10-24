# SO-101 laptop and Slurm pi0.5 deployment

This recipe replaces the retired `lerobot.async_inference` gRPC commands with
upstream's `lerobot.remote_inference` server and remote rollout client. It retains
the six-component degree/percent action order, `front` RGB camera at 640x480,
30 Hz, calibration ID, and blue-cube task used in the local experiments.

The checkpoint must use those exact conventions and include its saved processors.
The configuration is checked without hardware; task success and cluster transport
timing still need validation with the actual checkpoint. Use the same LeRobot
revision on the laptop and the compute node.

## Environment

For existing conda environments, install the current checkout and the required extras:

```bash
conda activate lerobot
# Laptop: preserves hardware support and updates the CLI entry points.
uv pip install --python "$CONDA_PREFIX/bin/python" -e '.[remote,core_scripts,feetech]'

# Compute node: run in its own environment from the same checkout revision.
uv pip install --python "$CONDA_PREFIX/bin/python" -e '.[remote,core_scripts,pi]'
```

For a separate lockfile-managed environment, use
`uv sync --locked --extra remote --extra core_scripts --extra feetech` on the
laptop; use `--extra pi` instead of `--extra feetech` on the compute node.
The commands below use Python module entry points, so an existing editable install
does not need its console scripts regenerated to launch them.

## Compute node

Inside your GPU allocation, set the path on the compute node:

```bash
PI05_CHECKPOINT=/absolute/path/to/pi05/checkpoints/last/pretrained_model
python -m lerobot.scripts.lerobot_policy_server \
  --config_path=examples/remote_inference/so101_slurm/server.yaml \
  --model.repo_or_path="$PI05_CHECKPOINT"
```

Wait for `Policy server ready` before starting the laptop client. Loading and
warmup happen once per server process. Keep the process and Slurm allocation alive
between trials; sequential clients reuse the same loaded deployment after session
cleanup. Changing the model, its inference settings, or server configuration
requires restarting the server. Neither the client nor this recipe submits a Slurm
job or chooses a partition/account for you.

## Laptop tunnel

The new server uses Zenoh TCP on port 7447 rather than gRPC on port 8080.
Open a separate laptop terminal and replace the SSH placeholders:

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -J YOUR_USER@LOGIN_NODE \
  -L 17447:127.0.0.1:7447 \
  YOUR_USER@COMPUTE_NODE
```

The server binds to compute-node loopback and the client explicitly connects to
the laptop's forwarded port. This assumes the cluster permits SSH through the
login node to an allocated compute node. Port forwarding itself does not validate
policy timing; measure the first run over the actual route.

## Laptop client and trials

Check device paths before launching:

```bash
python scripts/find_external_webcam.py
ls -l /dev/serial/by-id
```

Update `robot.cameras.front.index_or_path` in `client.yaml` to the printed camera
path. Its default `/dev/video4` is a previous mapping, not a permanent identifier.
The configured USB serial ID belongs to the previously identified follower arm.

The following command connects hardware; run it only when ready to operate:

```bash
python -m lerobot.scripts.lerobot_rollout \
  --config_path=examples/remote_inference/so101_slurm/client.yaml
```

- `/start` starts a trial. Each trial runs for at most 60 seconds with this config,
  then enters a position hold while keeping the session open.
- `/reset` invalidates the previous plan and **moves the arm back to its startup
  pose**, restores the initial task, then waits for another `/start`. Clear the
  return path before using it. This is not a torque-off pause command.
- `/stop` or Ctrl+C ends the client. This recipe sets
  `return_to_initial_position=false` so shutdown does not automatically return the
  arm to its startup pose. `disable_torque_on_disconnect=true` releases torque on
  disconnect, so support the arm if needed.

The server can remain running after `/stop`; start another client to begin a new
session with the same loaded model. The interactive terminal suppresses routine
logs but prints cadence reports at segment boundaries. For detailed continuous
diagnostics, run a bounded non-interactive trial yourself by adding
`--interactive=false --duration=20 --inference.log_level=DEBUG`; it starts policy
execution automatically and exits after the trial.

## Mapping the previous local changes

| Previous local change | Upstream replacement |
| --- | --- |
| Observation-upload worker | Remote engine worker handles encoding/exchanges; local capture and motor dispatch do not wait for network round trips. |
| Robot I/O serialization | Rollout's thread-safe robot wrapper owns hardware access. |
| Atomic action queue replacement | Inference chunk runtime owns request, queue, and commitment transitions. |
| Five-second upload timeout | `inference.action_timeout_s=5` bounds an entire remote action exchange; this is broader than the old upload-only timeout. |
| Control cadence logs | Rollout cadence reports and remote engine diagnostics. |
| Client reconnection reloaded weights | Server owns one warmed deployment and admits sequential client sessions. |

The old `actions_per_chunk=50` becomes server `execution.n_action_steps=50`.
The old `chunk_size_threshold=0.5` corresponded nominally to 25/30 seconds of
remaining playback; `refill_seconds=0.83` is a starting comparison value, not an
exact behavioral equivalence. Upstream can raise its effective refill threshold
based on measured turnaround.

The former `weighted_average` aggregation has no identical new flag. This recipe
starts with aligned chunks and no blending. Compare task progress before adding
explicit arm-only `blend_components` and a small `blend_steps` window; do not
silently apply joint-angle averaging to gripper closure. See
[the upstream remote inference guide](../../../docs/source/remote_inference.mdx)
for alignment, blending and RTC configuration.

The legacy gRPC implementation and its tests are not restored. Its final local
version is preserved in the Git stash named
`Backup local webcam and async client changes before upstream remote-inference migration`.
