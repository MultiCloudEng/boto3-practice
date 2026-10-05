"""Offline tests: botocore's Stubber replaces real AWS calls with canned responses."""
import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

import ec2_control as ec

ID1 = "i-0123456789abcdef0"
ID2 = "i-0fedcba9876543210"


def instance(iid, state, name=None):
    inst = {"InstanceId": iid, "State": {"Name": state}, "InstanceType": "t3.micro"}
    if name:
        inst["Tags"] = [{"Key": "Name", "Value": name}]
    return inst


@pytest.fixture
def ec2():
    client = boto3.client("ec2", region_name="eu-north-1",
                          aws_access_key_id="test", aws_secret_access_key="test")
    with Stubber(client) as stub:
        client.stub = stub
        yield client
        stub.assert_no_pending_responses()


def args_for(argv):
    return ec.build_parser().parse_args(argv)


def test_list_follows_pagination(ec2, capsys):
    ec2.stub.add_response("describe_instances",
                          {"Reservations": [{"Instances": [instance(ID1, "running", "web")]}],
                           "NextToken": "page2"}, {"Filters": []})
    ec2.stub.add_response("describe_instances",
                          {"Reservations": [{"Instances": [instance(ID2, "stopped")]}]},
                          {"Filters": [], "NextToken": "page2"})
    assert ec.cmd_list(ec2, args_for(["list"])) == ec.OK
    out = capsys.readouterr().out
    assert ID1 in out and "web" in out and ID2 in out


def test_list_state_filter(ec2):
    ec2.stub.add_response("describe_instances", {"Reservations": []},
                          {"Filters": [{"Name": "instance-state-name", "Values": ["running"]}]})
    assert ec.cmd_list(ec2, args_for(["list", "--state", "running"])) == ec.OK


def test_invalid_instance_id_rejected():
    with pytest.raises(SystemExit):
        args_for(["stop", "i-123"])


def test_dry_run_reports_permission_ok(ec2, capsys):
    ec2.stub.add_client_error("stop_instances", service_error_code="DryRunOperation",
                              expected_params={"InstanceIds": [ID1], "DryRun": True})
    assert ec.change_state(ec2, args_for(["stop", ID1, "--dry-run"]), "stop") == ec.OK
    assert "Dry run OK" in capsys.readouterr().out


def test_dry_run_unauthorized_is_raised(ec2):
    ec2.stub.add_client_error("start_instances", service_error_code="UnauthorizedOperation",
                              expected_params={"InstanceIds": [ID1], "DryRun": True})
    with pytest.raises(ClientError):
        ec.change_state(ec2, args_for(["start", ID1, "--dry-run"]), "start")


def test_start_skips_already_running(ec2, capsys):
    ec2.stub.add_response("describe_instances",
                          {"Reservations": [{"Instances": [instance(ID1, "running")]}]},
                          {"InstanceIds": [ID1]})
    assert ec.change_state(ec2, args_for(["start", ID1]), "start") == ec.OK
    assert "already running" in capsys.readouterr().out


def test_stop_requires_confirmation_when_not_interactive(ec2, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    ec2.stub.add_response("describe_instances",
                          {"Reservations": [{"Instances": [instance(ID1, "running")]}]},
                          {"InstanceIds": [ID1]})
    assert ec.change_state(ec2, args_for(["stop", ID1]), "stop") == ec.ABORTED


def test_stop_with_yes(ec2, capsys):
    ec2.stub.add_response("describe_instances",
                          {"Reservations": [{"Instances": [instance(ID1, "running")]}]},
                          {"InstanceIds": [ID1]})
    ec2.stub.add_response("stop_instances",
                          {"StoppingInstances": [{"InstanceId": ID1,
                                                  "PreviousState": {"Name": "running", "Code": 16},
                                                  "CurrentState": {"Name": "stopping", "Code": 64}}]},
                          {"InstanceIds": [ID1]})
    assert ec.change_state(ec2, args_for(["stop", ID1, "--yes"]), "stop") == ec.OK
    assert "running -> stopping" in capsys.readouterr().out


def test_unknown_instance_returns_error(ec2):
    ec2.stub.add_response("describe_instances", {"Reservations": []}, {"InstanceIds": [ID1]})
    assert ec.change_state(ec2, args_for(["start", ID1]), "start") == ec.AWS_ERROR


def test_main_handles_access_denied(monkeypatch):
    def boom(*a, **k):
        raise ClientError({"Error": {"Code": "UnauthorizedOperation", "Message": "no"}},
                          "DescribeInstances")
    monkeypatch.setattr(ec, "cmd_list", boom)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    assert ec.main(["--region", "eu-north-1", "list"]) == ec.AWS_ERROR
