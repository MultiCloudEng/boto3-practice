# EC2 Control with boto3

A small, safe command-line tool to list, start and stop EC2 instances with Python and boto3. I started with three separate scripts to explore least-privilege IAM: they triggered and handled real `UnauthorizedOperation` errors. I then turned them into one tool with safer behavior.

## Features

- **No hardcoded IDs or credentials.** Instance IDs are arguments; credentials come from the standard AWS chain (`aws configure`, SSO, environment variables, instance role).
- **Pagination.** `list` follows `NextToken`, so it works in accounts with many instances.
- **`--dry-run`.** Uses EC2's built-in `DryRun` to check permissions without changing anything.
- **Safe stop.** Asks for confirmation (or `--yes`), and refuses in non-interactive runs without `--yes`.
- **Idempotent.** Skips instances that are already in the target state and reports unknown IDs.
- **Clear errors.** Distinct messages and exit codes for missing credentials, permission denied and other AWS errors.

## Usage

```bash
pip install -r requirements.txt

python ec2_control.py list
python ec2_control.py list --state running --region eu-north-1
python ec2_control.py start i-0123456789abcdef0 --dry-run   # permission check only
python ec2_control.py start i-0123456789abcdef0
python ec2_control.py stop  i-0123456789abcdef0             # asks for confirmation
python ec2_control.py --profile dev stop i-0123456789abcdef0 --yes
```

Exit codes: `0` OK, `2` usage error, `3` AWS or credentials error, `4` aborted (no confirmation).

## Least-privilege IAM

[`iam-policy.json`](iam-policy.json) allows listing all instances, but starting and stopping **only instances tagged `Environment=dev`**. Attach it to the IAM user or role that runs the tool, and adjust the tag to your setup. `--dry-run` is a quick way to check whether a policy allows an action.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

10 offline tests use botocore's `Stubber`, so they make no AWS calls and need no credentials. They cover pagination, the state filter, invalid IDs, dry-run success and denial, skipping instances already in the target state, stop confirmation, unknown instances and access-denied handling. They also run in GitHub Actions together with `ruff`.

**What was tested against real AWS:** the original scripts (start, stop, list and the `UnauthorizedOperation` handling) were run against my AWS account. The new CLI has been tested offline (stubbed AWS) only so far.

## Skills

Python, boto3, AWS EC2 API, IAM least privilege, error handling, pagination, testing with mocks.
