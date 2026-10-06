#!/usr/bin/env python3
"""List, start and stop EC2 instances safely with boto3.

Examples:
    python ec2_control.py list
    python ec2_control.py list --state running --region eu-north-1
    python ec2_control.py start i-0123456789abcdef0 --dry-run
    python ec2_control.py stop i-0123456789abcdef0 --yes

Credentials come from the standard AWS chain (environment, ~/.aws, SSO, or an
instance role). Nothing is hardcoded.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Iterable, Iterator

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

log = logging.getLogger("ec2_control")

INSTANCE_ID_RE = re.compile(r"^i-[0-9a-f]{8}([0-9a-f]{9})?$")

# Exit codes
OK, USAGE_ERROR, AWS_ERROR, ABORTED = 0, 2, 3, 4


def instance_id(value: str) -> str:
    """argparse type: validate the EC2 instance ID format before calling AWS."""
    if not INSTANCE_ID_RE.match(value):
        raise argparse.ArgumentTypeError(f"invalid instance ID: {value!r}")
    return value


def name_tag(instance: dict) -> str:
    for tag in instance.get("Tags", []):
        if tag.get("Key") == "Name":
            return tag.get("Value", "")
    return ""


def iter_instances(ec2, states: Iterable[str] | None = None) -> Iterator[dict]:
    """Yield every instance, following pagination (describe_instances returns
    at most one page per call, so large accounts would otherwise be cut off)."""
    filters = [{"Name": "instance-state-name", "Values": list(states)}] if states else []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=filters):
        for reservation in page.get("Reservations", []):
            yield from reservation.get("Instances", [])


def cmd_list(ec2, args) -> int:
    count = 0
    for inst in iter_instances(ec2, args.state):
        count += 1
        print(f"{inst['InstanceId']:<20} {inst['State']['Name']:<12} "
              f"{inst.get('InstanceType', ''):<12} {name_tag(inst)}")
    log.info("%d instance(s) found", count)
    return OK


def current_states(ec2, ids: list[str]) -> dict[str, str]:
    resp = ec2.describe_instances(InstanceIds=ids)
    return {
        inst["InstanceId"]: inst["State"]["Name"]
        for res in resp.get("Reservations", [])
        for inst in res.get("Instances", [])
    }


def confirm(action: str, ids: list[str]) -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input(f"{action} {len(ids)} instance(s): {', '.join(ids)}? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def change_state(ec2, args, action: str) -> int:
    ids = sorted(set(args.instance_ids))
    skip_state = "running" if action == "start" else "stopped"

    if args.dry_run:
        # EC2 DryRun checks permissions without changing anything.
        # AWS answers with a "DryRunOperation" error when the call WOULD succeed.
        try:
            getattr(ec2, f"{action}_instances")(InstanceIds=ids, DryRun=True)
        except ClientError as err:
            code = err.response["Error"]["Code"]
            if code == "DryRunOperation":
                print(f"Dry run OK: you are allowed to {action} {', '.join(ids)}")
                return OK
            raise
        return OK  # not expected, but nothing was changed either

    states = current_states(ec2, ids)
    missing = [i for i in ids if i not in states]
    if missing:
        log.error("Instance(s) not found: %s", ", ".join(missing))
        return AWS_ERROR
    todo = [i for i in ids if states[i] != skip_state]
    for i in ids:
        if i not in todo:
            print(f"{i} is already {skip_state}, skipping")
    if not todo:
        return OK

    if action == "stop" and not args.yes and not confirm("Stop", todo):
        log.warning("Aborted: stopping requires confirmation (or --yes)")
        return ABORTED

    resp = getattr(ec2, f"{action}_instances")(InstanceIds=todo)
    key = "StartingInstances" if action == "start" else "StoppingInstances"
    for change in resp.get(key, []):
        print(f"{change['InstanceId']}: {change['PreviousState']['Name']} -> "
              f"{change['CurrentState']['Name']}")
    return OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely list, start and stop EC2 instances.")
    parser.add_argument("--region", help="AWS region (default: from your AWS config)")
    parser.add_argument("--profile", help="AWS CLI profile name")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list instances")
    p_list.add_argument("--state", action="append",
                        choices=["pending", "running", "stopping", "stopped",
                                 "shutting-down", "terminated"],
                        help="filter by state (repeatable)")

    for name in ("start", "stop"):
        p = sub.add_parser(name, help=f"{name} instances")
        p.add_argument("instance_ids", nargs="+", type=instance_id, metavar="INSTANCE_ID")
        p.add_argument("--dry-run", action="store_true",
                       help="only check permissions (EC2 DryRun), change nothing")
        if name == "stop":
            p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        ec2 = session.client("ec2")
        if args.command == "list":
            return cmd_list(ec2, args)
        return change_state(ec2, args, args.command)
    except NoCredentialsError:
        log.error("No AWS credentials found. Run 'aws configure' or 'aws sso login'.")
        return AWS_ERROR
    except ClientError as err:
        error = err.response.get("Error", {})
        code = error.get("Code", "Unknown")
        if code in {"UnauthorizedOperation", "AccessDenied", "AccessDeniedException"}:
            log.error("Permission denied (%s). Check the IAM policy (see iam-policy.json).", code)
        else:
            log.error("AWS error %s: %s", code, error.get("Message", err))
        return AWS_ERROR
    except BotoCoreError as err:
        log.error("AWS SDK error: %s", err)
        return AWS_ERROR


if __name__ == "__main__":
    sys.exit(main())
