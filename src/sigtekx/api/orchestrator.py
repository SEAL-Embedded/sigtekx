"""EC2 lifecycle drivers: launch -> benchmark -> download -> terminate.

Replaces the manual console procedure documented in
docs/aws/cloud-deployment.md (steps 4-6) with a single API call, while
reusing the existing shell scripts verbatim for the parts they already do
well. The scripts are the source of truth for *how* a benchmark runs; this
module only owns the instance lifecycle around them.

Two drivers behind one Protocol:

- ``RealDriver`` provisions a real spot GPU instance via boto3.
- ``MockDriver`` fakes the same state transitions with no AWS calls, so the
  service is demoable (and testable) at zero cost.

Cost safety is the design centre of this module. Every launched instance is
terminated in a ``finally`` block, tagged for out-of-band discovery, and
recorded in SQLite the moment it exists. See ``TERMINATION`` below for the
honest limits of that guarantee.

TERMINATION
-----------
The ``finally`` block covers exceptions, benchmark failure and SSH timeouts.
It does NOT cover SIGKILL of the API process or the host dying, because no
in-process handler runs in those cases. Mitigations, in order of strength:

1. Every instance is tagged ``ManagedBy=sigtekx-api`` at launch, so orphans
   are findable with one CLI call (see ``ORPHAN_QUERY``).
2. Instance IDs are written to SQLite *before* the benchmark starts, so a
   restarted API reports them via ``RunStore.unterminated_instances()``.
3. Spot instances cap the blast radius but do not expire on their own.

A production system would add an EC2 auto-terminate alarm or a Lambda
reaper on the tag. That is deliberately out of scope here and noted in
docs/_personal/api-upgrade-path.md.
"""

import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Protocol

from sigtekx.api.models import BenchmarkRequest, RunMode, RunStatus

logger = logging.getLogger("sigtekx.api.orchestrator")

MANAGED_TAG = "sigtekx-api"
ORPHAN_QUERY = (
    "aws ec2 describe-instances "
    f"--filters Name=tag:ManagedBy,Values={MANAGED_TAG} "
    "Name=instance-state-name,Values=running,pending "
    "--query 'Reservations[].Instances[].InstanceId' --output text"
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts" / "aws"

# Wall-clock ceilings. run_mode=full is a ~30min Snakemake suite, so its ceiling
# is generous; the others are tight enough that a hung run is caught, not billed.
BENCH_TIMEOUT_S = {
    RunMode.SMOKE: 15 * 60,
    RunMode.SINGLE: 45 * 60,
    RunMode.FULL: 90 * 60,
}
SSH_WAIT_TIMEOUT_S = 300
SSH_POLL_INTERVAL_S = 10

# Dead-man switch. The instance shuts itself down after this many minutes no
# matter what happens to the API process, which is the only mitigation that
# survives SIGKILL of this process or the host dying. Sized above the longest
# benchmark (full ~= 30min) plus boot and upload slack.
MAX_INSTANCE_LIFETIME_MIN = int(os.environ.get("SIGX_MAX_LIFETIME_MIN", "120"))


class StepFailed(RuntimeError):
    """A lifecycle step failed; the caller must still terminate the instance."""


class LifecycleDriver(Protocol):
    """Contract shared by the real and mock drivers."""

    def launch(self, instance_type: str) -> tuple[str, str]:
        """Provision an instance. Returns (instance_id, public_ip)."""
        ...

    def wait_for_ssh(self, public_ip: str) -> None:
        """Block until the instance accepts SSH, or raise StepFailed."""
        ...

    def run_benchmark(self, public_ip: str, instance_id: str, req: BenchmarkRequest) -> None:
        """Run the benchmark on the instance via the existing shell script."""
        ...

    def download_results(self) -> str:
        """Pull results locally. Returns the result location."""
        ...

    def terminate(self, instance_id: str) -> None:
        """Terminate the instance. Must be safe to call more than once."""
        ...


# ---------------------------------------------------------------------------
# Shell-out helper
# ---------------------------------------------------------------------------


def _run_script(script: Path, args: list[str], timeout_s: int, env_extra: dict | None = None) -> str:
    """Run one of the repo's AWS shell scripts and capture its output.

    Uses a list argv (never ``shell=True``) so request-supplied values such as
    hydra args cannot be interpreted as shell syntax.
    """
    if not script.exists():
        raise StepFailed(f"script not found: {script}")

    env = {**os.environ, **(env_extra or {})}
    cmd = ["bash", str(script), *args]
    # NB: not "args" -- that is a reserved LogRecord attribute and passing it
    # via extra= raises "Attempt to overwrite 'args' in LogRecord".
    logger.info("exec", extra={"script": script.name, "argv": args})

    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise StepFailed(f"{script.name} timed out after {timeout_s}s") from exc

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-15:]
        raise StepFailed(f"{script.name} exited {proc.returncode}: {' | '.join(tail)}")

    return proc.stdout


# ---------------------------------------------------------------------------
# Mock driver
# ---------------------------------------------------------------------------


class MockDriver:
    """Simulates the lifecycle with no AWS calls and no cost.

    Exists so the service can be demoed and integration-tested without an AWS
    account. Sleeps are short but non-zero so status transitions are actually
    observable through the API during a demo.

    Unused arguments below are intentional: the signatures must match
    LifecycleDriver so the two drivers stay substitutable.
    """

    def __init__(self, step_delay_s: float = 1.0) -> None:
        self.step_delay_s = step_delay_s
        self.terminated: list[str] = []

    def launch(self, instance_type: str) -> tuple[str, str]:  # noqa: ARG002
        time.sleep(self.step_delay_s)
        instance_id = f"i-mock{int(time.time()) % 100000:05d}"
        logger.info("[mock] instance launched", extra={"instance_id": instance_id})
        return instance_id, "203.0.113.10"  # TEST-NET-3, never routable

    def wait_for_ssh(self, public_ip: str) -> None:  # noqa: ARG002
        time.sleep(self.step_delay_s)

    def run_benchmark(self, public_ip: str, instance_id: str, req: BenchmarkRequest) -> None:  # noqa: ARG002
        time.sleep(self.step_delay_s * 2)
        logger.info("[mock] benchmark complete", extra={"run_mode": req.run_mode.value})

    def download_results(self) -> str:
        time.sleep(self.step_delay_s)
        return "datasets/aws-mock-run/"

    def terminate(self, instance_id: str) -> None:
        self.terminated.append(instance_id)
        logger.info("[mock] instance terminated", extra={"instance_id": instance_id})


# ---------------------------------------------------------------------------
# Real driver
# ---------------------------------------------------------------------------


class RealDriver:
    """Provisions real EC2 spot GPU instances. Costs money.

    Launch parameters come from the environment because they are
    account-specific (AMI IDs are region-scoped, security-group and subnet IDs
    are VPC-scoped, the key-pair name must already exist in the account).
    Baking them into source would make the repo non-portable and would leak
    infrastructure identifiers into version control.
    """

    def __init__(self) -> None:
        self.region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
        self.ami_id = os.environ.get("SIGX_AMI_ID")
        self.key_name = os.environ.get("SIGX_KEY_NAME", "sigtekx")
        self.security_group = os.environ.get("SIGX_SECURITY_GROUP")
        self.subnet_id = os.environ.get("SIGX_SUBNET_ID")
        self.iam_profile = os.environ.get(
            "SIGX_INSTANCE_PROFILE", "SigTekXEC2BenchmarkRole"
        )
        self.use_spot = os.environ.get("SIGX_USE_SPOT", "true").lower() != "false"
        self.ondemand_fallback = (
            os.environ.get("SIGX_ONDEMAND_FALLBACK", "true").lower() != "false"
        )

        if not self.ami_id:
            raise RuntimeError(
                "SIGX_AMI_ID is required in real mode (region-scoped Deep Learning AMI). "
                "Set SIGX_API_MODE=mock to run without AWS."
            )

        import boto3  # imported lazily: only real mode needs it

        self._ec2 = boto3.client("ec2", region_name=self.region)
        self.preflight()

    def preflight(self) -> None:
        """Validate AWS config before anything billable happens.

        Every check here is a read-only API call. Catching a bad AMI or a
        missing key pair now costs a second; catching it after run_instances
        costs a boot cycle and the minutes of instance time that go with it.
        Fail loudly at startup rather than mid-run.
        """
        import botocore.exceptions

        try:
            import boto3

            ident = boto3.client("sts", region_name=self.region).get_caller_identity()
        except botocore.exceptions.BotoCoreError as exc:
            raise RuntimeError(f"AWS credentials not usable: {exc}") from exc
        except botocore.exceptions.ClientError as exc:
            raise RuntimeError(f"AWS credentials rejected: {exc}") from exc

        problems: list[str] = []

        try:
            self._ec2.describe_images(ImageIds=[self.ami_id])
        except botocore.exceptions.ClientError as exc:
            problems.append(f"SIGX_AMI_ID={self.ami_id} not found in {self.region} ({exc.response['Error']['Code']})")

        try:
            self._ec2.describe_key_pairs(KeyNames=[self.key_name])
        except botocore.exceptions.ClientError:
            problems.append(f"SIGX_KEY_NAME={self.key_name} does not exist in {self.region}")

        try:
            boto3.client("iam").get_instance_profile(InstanceProfileName=self.iam_profile)
        except botocore.exceptions.ClientError:
            problems.append(
                f"instance profile {self.iam_profile} not found "
                "(run scripts/aws/setup_iam.sh)"
            )

        if problems:
            raise RuntimeError("real-mode preflight failed: " + "; ".join(problems))

        logger.info(
            "preflight ok",
            extra={
                "account": ident["Account"],
                "region": self.region,
                "ami": self.ami_id,
                "spot": self.use_spot,
            },
        )

    def launch(self, instance_type: str) -> tuple[str, str]:
        spec: dict = {
            "ImageId": self.ami_id,
            "InstanceType": instance_type,
            "KeyName": self.key_name,
            "MinCount": 1,
            "MaxCount": 1,
            "IamInstanceProfile": {"Name": self.iam_profile},
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "ManagedBy", "Value": MANAGED_TAG},
                        {"Key": "Name", "Value": "sigtekx-benchmark"},
                    ],
                }
            ],
        }
        # Dead-man switch: the instance terminates itself even if this process
        # is SIGKILLed. Spot instances always terminate on shutdown and reject
        # an explicit InstanceInitiatedShutdownBehavior, so only set it for
        # on-demand; the user-data timer applies to both.
        spec["UserData"] = (
            "#!/bin/bash\n"
            f"shutdown -h +{MAX_INSTANCE_LIFETIME_MIN}\n"
        )
        if not self.use_spot:
            spec["InstanceInitiatedShutdownBehavior"] = "terminate"

        if self.security_group:
            spec["SecurityGroupIds"] = [self.security_group]
        if self.subnet_id:
            spec["SubnetId"] = self.subnet_id
        if self.use_spot:
            # one-time spot: the instance is terminated (not stopped) on
            # interruption, which matches this workload's disposable nature.
            spec["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {"SpotInstanceType": "one-time"},
            }

        resp = self._launch_with_capacity_retry(spec)
        instance_id = resp["Instances"][0]["InstanceId"]
        logger.info("instance launched", extra={"instance_id": instance_id})

        # Block until AWS assigns a public IP.
        self._ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
        desc = self._ec2.describe_instances(InstanceIds=[instance_id])
        public_ip = desc["Reservations"][0]["Instances"][0].get("PublicIpAddress")
        if not public_ip:
            raise StepFailed(
                f"{instance_id} has no public IP — check the subnet has an internet gateway"
            )
        return instance_id, public_ip

    def _launch_with_capacity_retry(self, spec: dict) -> dict:
        """Launch, falling back to another AZ when one is out of capacity.

        Spot GPU capacity is per-availability-zone and fluctuates, so pinning a
        single subnet turns a routine shortage into a failed run. When no subnet
        is configured we let EC2 choose, then retry the remaining default
        subnets one at a time on InsufficientInstanceCapacity.

        Only capacity errors are retried; a bad AMI or missing permission is a
        real failure and must surface immediately rather than be retried four
        times against every AZ.
        """
        import botocore.exceptions

        # Both mean "this AZ cannot serve the request, try another": one is a
        # transient shortage, the other means the type is not offered there.
        RETRYABLE = {"InsufficientInstanceCapacity", "Unsupported"}

        candidates: list[str | None] = [spec.get("SubnetId")]
        if not spec.get("SubnetId"):
            candidates += self._default_subnets()

        # Spot is cheaper but is the first thing to run out. If every AZ is out
        # of spot capacity, fall back to on-demand rather than failing the run:
        # a few cents more is better than a blocked benchmark. Opt out with
        # SIGX_ONDEMAND_FALLBACK=false.
        plans: list[tuple[str, dict]] = [("spot", spec)]
        if spec.get("InstanceMarketOptions") and self.ondemand_fallback:
            on_demand = {k: v for k, v in spec.items() if k != "InstanceMarketOptions"}
            on_demand["InstanceInitiatedShutdownBehavior"] = "terminate"
            plans.append(("on-demand", on_demand))

        last_exc: Exception | None = None
        for market, base in plans:
            for subnet in candidates:
                attempt = dict(base)
                if subnet:
                    attempt["SubnetId"] = subnet
                else:
                    attempt.pop("SubnetId", None)
                try:
                    resp = self._ec2.run_instances(**attempt)
                    if market == "on-demand":
                        logger.warning(
                            "no spot capacity anywhere; launched on-demand instead",
                            extra={"subnet": subnet or "<ec2-chosen>"},
                        )
                    return resp
                except botocore.exceptions.ClientError as exc:
                    code = exc.response["Error"]["Code"]
                    if code not in RETRYABLE:
                        raise
                    logger.warning(
                        "AZ cannot serve this request, trying another",
                        extra={
                            "subnet": subnet or "<ec2-chosen>",
                            "market": market,
                            "code": code,
                        },
                    )
                    last_exc = exc

        raise StepFailed(
            f"no {spec['InstanceType']} capacity in any availability zone "
            f"of {self.region} (spot and on-demand): {last_exc}"
        )

    def _default_subnets(self) -> list[str]:
        """Default subnets in this region, one per AZ."""
        try:
            resp = self._ec2.describe_subnets(
                Filters=[{"Name": "default-for-az", "Values": ["true"]}]
            )
            return [s["SubnetId"] for s in resp["Subnets"]]
        except Exception:  # noqa: BLE001 -- fallback path only
            logger.warning("could not enumerate subnets for AZ fallback")
            return []

    def wait_for_ssh(self, public_ip: str) -> None:
        """``instance_running`` only means the hypervisor started it; sshd may
        need another minute. Poll the port rather than guessing with sleep."""
        deadline = time.monotonic() + SSH_WAIT_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((public_ip, 22), timeout=5):
                    logger.info("ssh ready", extra={"ip": public_ip})
                    return
            except OSError:
                time.sleep(SSH_POLL_INTERVAL_S)
        raise StepFailed(f"SSH not ready on {public_ip} after {SSH_WAIT_TIMEOUT_S}s")

    def run_benchmark(self, public_ip: str, instance_id: str, req: BenchmarkRequest) -> None:
        args = [public_ip, instance_id]
        if req.run_mode is RunMode.SMOKE:
            args.append("--smoke")
        elif req.run_mode is RunMode.FULL:
            args.append("--full")
        else:
            args.append("--")
            args.extend(req.hydra_args or ["experiment=ionosphere_test", "+benchmark=latency"])

        _run_script(
            SCRIPTS / "run_ec2_benchmark.sh",
            args,
            timeout_s=BENCH_TIMEOUT_S[req.run_mode],
            env_extra=_engine_env(req),
        )

    def download_results(self) -> str:
        out = _run_script(SCRIPTS / "download_results.sh", [], timeout_s=15 * 60)
        for line in out.splitlines():
            if "Location:" in line:
                return line.split("Location:", 1)[1].strip()
        return "datasets/ (see download_results.sh output)"

    def terminate(self, instance_id: str) -> None:
        self._ec2.terminate_instances(InstanceIds=[instance_id])
        logger.info("instance terminated", extra={"instance_id": instance_id})


def _engine_env(req: BenchmarkRequest) -> dict:
    """Pass engine knobs the shell script already understands.

    Only maps what run_ec2_benchmark.sh actually reads; the rest of
    EngineConfig reaches the container through hydra args.
    """
    env = {}
    if req.run_mode is RunMode.SINGLE and any(
        a.startswith("+benchmark=throughput") for a in req.hydra_args
    ):
        env["SIGX_BENCH_SCRIPT"] = "run_throughput.py"
    return env


def build_driver() -> LifecycleDriver:
    """Select a driver from SIGX_API_MODE. Defaults to mock.

    Defaulting to mock is deliberate: the failure mode of guessing wrong is
    asymmetric. Guessing mock costs nothing; guessing real spends money on an
    unconfigured machine.
    """
    mode = os.environ.get("SIGX_API_MODE", "mock").lower()
    if mode == "real":
        logger.warning("orchestrator in REAL mode — runs will launch billable EC2 instances")
        return RealDriver()
    return MockDriver(step_delay_s=float(os.environ.get("SIGX_MOCK_DELAY", "1.0")))


# ---------------------------------------------------------------------------
# The orchestration itself
# ---------------------------------------------------------------------------


def execute_run(run_id: str, req: BenchmarkRequest, driver: LifecycleDriver, store) -> None:
    """Drive one benchmark end to end, then always clean up.

    Runs in a background thread. It must never raise: an escaping exception
    would be swallowed by the threadpool and the run would appear stuck.
    Every failure path is recorded on the run instead.
    """
    instance_id: str | None = None
    instance_type = req.instance_type or os.environ.get("SIGX_INSTANCE_TYPE", "g4dn.xlarge")

    try:
        store.update(run_id, status=RunStatus.PROVISIONING)
        instance_id, public_ip = driver.launch(instance_type)
        # Persist the ID immediately: from here on the instance is billable and
        # must be recoverable even if this process dies.
        store.update(run_id, instance_id=instance_id)

        driver.wait_for_ssh(public_ip)

        store.update(run_id, status=RunStatus.RUNNING)
        driver.run_benchmark(public_ip, instance_id, req)

        store.update(run_id, status=RunStatus.DOWNLOADING)
        location = driver.download_results()

        store.update(run_id, status=RunStatus.SUCCEEDED, result_location=location)
        logger.info("run succeeded", extra={"run_id": run_id, "location": location})

    except Exception as exc:  # noqa: BLE001 — background thread must not raise
        logger.exception("run failed", extra={"run_id": run_id})
        store.update(run_id, status=RunStatus.FAILED, error=str(exc)[:500])

    finally:
        # The cost guarantee. Runs on success, failure and timeout alike.
        if instance_id is not None:
            try:
                driver.terminate(instance_id)
                store.update(run_id, terminated=True)
            except Exception:  # noqa: BLE001
                # Terminate failed: leave terminated=0 so the instance shows up
                # in the startup orphan audit rather than being forgotten.
                logger.exception(
                    "TERMINATE FAILED — instance may still be billing",
                    extra={"run_id": run_id, "instance_id": instance_id},
                )
