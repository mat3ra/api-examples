import asyncio
import contextlib
import threading
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from mat3ra.api_client import AuthContext, JobEndpoints
from mat3ra.notebooks_utils.core.entity.job.api import (
    _list_jobs_with_fetch,
    create_job,
    find_job_for_material,
    find_job_for_material_with_property,
    get_jobs_statuses_by_ids_async,
    get_kgrid_of_job,
    get_kgrid_query,
)

OWNER_ID = "account-1"
PROJECT_ID = "project-1"
JOB_PREFIX = "NEB H2+H"
MATERIAL_SET_ID = "set-1"
MATERIAL_SET_NAME = "H2+H"

MATERIAL_INITIAL: Dict[str, Any] = {"_id": "m-initial", "name": "initial"}
MATERIAL_FINAL: Dict[str, Any] = {"_id": "m-final", "name": "final"}
MATERIALS: List[Dict[str, Any]] = [MATERIAL_INITIAL, MATERIAL_FINAL]

MULTI_MATERIAL_WORKFLOW: Dict[str, Any] = {
    "_id": "workflow-1",
    "name": "NEB",
    "isMultiMaterial": True,
}
SINGLE_MATERIAL_WORKFLOW: Dict[str, Any] = {
    "_id": "workflow-2",
    "name": "Total Energy",
    "isMultiMaterial": False,
}
MATERIALS_SET: Dict[str, Any] = {
    "_id": MATERIAL_SET_ID,
    "name": MATERIAL_SET_NAME,
    "slug": MATERIAL_SET_NAME,
    "isEntitySet": True,
}
CREATED_JOB: Dict[str, Any] = {"_id": "job-1", "name": JOB_PREFIX}
EXISTING_JOB: Dict[str, Any] = {"_id": "job-0", "name": "Fixed-cell Relaxation V_B pbe-us", "status": "finished"}
RELAX_WORKFLOW_NAME = "Fixed-cell Relaxation V_B pbe-us"
CHARGE_TAGS = ["charge:-1"]


@pytest.mark.parametrize(
    ("workflow", "materials_set", "expected_materials_set"),
    [
        (MULTI_MATERIAL_WORKFLOW, MATERIALS_SET, True),
        (MULTI_MATERIAL_WORKFLOW, None, False),
        (SINGLE_MATERIAL_WORKFLOW, MATERIALS_SET, True),
    ],
)
def test_create_job_sets_materials_set_when_provided(workflow, materials_set, expected_materials_set):
    client = MagicMock()
    client.jobs.create.return_value = CREATED_JOB
    workflow_payload = dict(workflow)

    job = create_job(
        api_client=client,
        materials=MATERIALS,
        workflow=workflow_payload,
        project_id=PROJECT_ID,
        owner_id=OWNER_ID,
        prefix=JOB_PREFIX,
        materials_set=materials_set,
    )

    assert job["_id"] == "job-1"
    config = client.jobs.create.call_args.args[0]
    assert "_id" not in workflow_payload
    assert ("_materialsSet" in config) is expected_materials_set
    if expected_materials_set:
        assert config["_materialsSet"] == {
            "_id": MATERIAL_SET_ID,
            "cls": "Material",
            "slug": MATERIAL_SET_NAME,
        }
    if workflow.get("isMultiMaterial"):
        assert config["_materials"] == [{"_id": "m-initial"}, {"_id": "m-final"}]
    else:
        assert "_materials" not in config


@pytest.mark.parametrize(
    ("tags", "expected_tags"),
    [(None, None), (CHARGE_TAGS, CHARGE_TAGS)],
)
def test_create_job_sets_tags_when_provided(tags, expected_tags):
    client = MagicMock()
    client.jobs.create.return_value = CREATED_JOB

    create_job(
        api_client=client,
        materials=MATERIALS,
        workflow=dict(SINGLE_MATERIAL_WORKFLOW),
        project_id=PROJECT_ID,
        owner_id=OWNER_ID,
        prefix=JOB_PREFIX,
        tags=tags,
    )

    assert client.jobs.create.call_args.args[0].get("tags") == expected_tags


@pytest.mark.parametrize(
    "statuses",
    [("finished",), ("submitted", "queued", "active")],
)
def test_find_job_for_material_returns_the_job_when_found(statuses):
    client = MagicMock()
    client.jobs.list.return_value = [EXISTING_JOB]

    job = find_job_for_material(client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID, statuses=statuses)

    assert job == EXISTING_JOB
    client.jobs.list.assert_called_once_with(
        {
            "_material._id": MATERIAL_INITIAL["_id"],
            "owner._id": OWNER_ID,
            "workflow.name": RELAX_WORKFLOW_NAME,
            "status": {"$in": list(statuses)},
        },
        {"limit": 1},
    )


def test_find_job_for_material_returns_none_when_not_found():
    client = MagicMock()
    client.jobs.list.return_value = []

    job = find_job_for_material(client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID)

    assert job is None


def test_find_job_for_material_defaults_to_finished_only():
    client = MagicMock()
    client.jobs.list.return_value = []

    find_job_for_material(client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID)

    assert client.jobs.list.call_args.args[0]["status"] == {"$in": ["finished"]}


PROPERTY_NAME = "total_energy"
JOB_WITHOUT_PROPERTY: Dict[str, Any] = {"_id": "job-2", "name": "Band Gap", "status": "finished"}


def test_find_job_for_material_with_property_returns_the_first_job_that_reported_it():
    client = MagicMock()
    client.jobs.list.return_value = [JOB_WITHOUT_PROPERTY, EXISTING_JOB]
    client.properties.get_for_job.side_effect = lambda job_id, property_name: (
        [{"name": property_name}] if job_id == EXISTING_JOB["_id"] else []
    )

    job = find_job_for_material_with_property(
        client, MATERIAL_INITIAL["_id"], PROPERTY_NAME, OWNER_ID, tags=CHARGE_TAGS
    )

    assert job == EXISTING_JOB
    client.jobs.list.assert_called_once_with(
        {
            "_material._id": MATERIAL_INITIAL["_id"],
            "owner._id": OWNER_ID,
            "status": "finished",
            "tags": {"$all": CHARGE_TAGS},
        }
    )


def test_find_job_for_material_with_property_returns_none_when_no_job_reported_it():
    client = MagicMock()
    client.jobs.list.return_value = [JOB_WITHOUT_PROPERTY]
    client.properties.get_for_job.return_value = []

    job = find_job_for_material_with_property(client, MATERIAL_INITIAL["_id"], PROPERTY_NAME, OWNER_ID)

    assert job is None
    assert "tags" not in client.jobs.list.call_args.args[0]


SCF_KGRID_QUERY: Dict[str, Any] = {
    "workflow.subworkflows.units": {
        "$elemMatch": {"name": "pw_scf", "context": {"$elemMatch": {"name": "kgrid", "data.dimensions": [4, 4, 4]}}}
    }
}
RELAX_KGRID_QUERY: Dict[str, Any] = {
    "workflow.subworkflows.units": {
        "$elemMatch": {"name": "pw_relax", "context": {"$elemMatch": {"name": "kgrid", "data.dimensions": [4, 4, 4]}}}
    }
}


@pytest.mark.parametrize(
    ("kgrid", "unit_name", "expected_query"),
    [(None, "pw_relax", {}), ([4, 4, 4], "pw_scf", SCF_KGRID_QUERY), ([4, 4, 4], "pw_relax", RELAX_KGRID_QUERY)],
)
def test_get_kgrid_query(kgrid, unit_name, expected_query):
    assert get_kgrid_query(kgrid, unit_name) == expected_query


def test_find_job_for_material_with_property_matches_the_pw_scf_kgrid():
    client = MagicMock()
    client.jobs.list.return_value = [EXISTING_JOB]
    client.properties.get_for_job.return_value = [{"name": PROPERTY_NAME}]

    job = find_job_for_material_with_property(client, MATERIAL_INITIAL["_id"], PROPERTY_NAME, OWNER_ID, kgrid=[4, 4, 4])

    assert job == EXISTING_JOB
    assert SCF_KGRID_QUERY.items() <= client.jobs.list.call_args.args[0].items()


def test_find_job_for_material_matches_the_kgrid_of_the_unit():
    client = MagicMock()
    client.jobs.list.return_value = [EXISTING_JOB]

    job = find_job_for_material(
        client, MATERIAL_INITIAL["_id"], RELAX_WORKFLOW_NAME, OWNER_ID, kgrid=[4, 4, 4], unit_name="pw_relax"
    )

    assert job == EXISTING_JOB
    assert RELAX_KGRID_QUERY.items() <= client.jobs.list.call_args.args[0].items()


# The pw_scf unit with a kgrid context, input not rendered yet, and as production job BLmZo5WZfFXKKTb2H stores a job
# created without a grid: no context, the platform's grid rendered into the input.
KGRID_CONTEXT: Dict[str, Any] = {
    "name": "kgrid",
    "isEdited": True,
    "data": {"dimensions": [4, 4, 4], "shifts": [0, 0, 0], "gridMetricType": "KPPRA", "gridMetricValue": 768},
    "extraData": {"materialHash": "041d30e32f91e2eeb14c74298dffd08b"},
}
RENDERED_INPUT = (
    "CELL_PARAMETERS angstrom\n   0.000000000    0.000000000    5.326038000\nK_POINTS automatic\n1 1 1 0 0 0 \n"
)
UNIT_WITH_KGRID_CONTEXT: Dict[str, Any] = {
    "name": "pw_scf",
    "context": [KGRID_CONTEXT],
    "input": [{"template": {"name": "pw_scf.in"}, "rendered": "", "isManuallyChanged": False}],
}
UNIT_WITH_RENDERED_INPUT: Dict[str, Any] = {
    "name": "pw_scf",
    "context": [],
    "input": [{"template": {"name": "pw_scf.in"}, "rendered": RENDERED_INPUT, "isManuallyChanged": False}],
}


@pytest.mark.parametrize(
    ("unit", "expected_kgrid"),
    [(UNIT_WITH_KGRID_CONTEXT, [4, 4, 4]), (UNIT_WITH_RENDERED_INPUT, [1, 1, 1])],
)
def test_get_kgrid_of_job(unit, expected_kgrid):
    assert get_kgrid_of_job({"workflow": {"subworkflows": [{"units": [unit]}]}}) == expected_kgrid


REQUEST_TIMEOUT_SECONDS = 0.05
BLOCKED_REQUEST_SECONDS = 1.0


@pytest.mark.asyncio
async def test_get_jobs_statuses_by_ids_async_raises_when_the_request_times_out():
    release_request = threading.Event()
    endpoint = MagicMock()
    endpoint.list.side_effect = lambda query, projection: release_request.wait(BLOCKED_REQUEST_SECONDS)

    with pytest.raises(asyncio.TimeoutError):
        await get_jobs_statuses_by_ids_async(endpoint, [CREATED_JOB["_id"]], timeout=REQUEST_TIMEOUT_SECONDS)
    release_request.set()


HTTP_ERROR_401 = requests.HTTPError("Error 401.", response=MagicMock(status_code=401))
HTTP_ERROR_500 = requests.HTTPError("Error 500.", response=MagicMock(status_code=500))
JOBS_WITH_STATUSES: List[Dict[str, Any]] = [{"status": "active"}, {"status": "finished"}]
ACCESS_TOKEN = "access-token-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("access_token", "list_results", "expectation", "expected_reauthentications"),
    [
        (ACCESS_TOKEN, [HTTP_ERROR_401, JOBS_WITH_STATUSES], contextlib.nullcontext(), 1),
        (ACCESS_TOKEN, [HTTP_ERROR_401, HTTP_ERROR_401], pytest.raises(requests.HTTPError), 1),
        (ACCESS_TOKEN, [HTTP_ERROR_500], pytest.raises(requests.HTTPError), 0),
        (None, [HTTP_ERROR_401], pytest.raises(requests.HTTPError), 0),
    ],
    ids=["401 once", "401 twice", "500", "401 with X-Auth headers"],
)
async def test_get_jobs_statuses_by_ids_async_reauthenticates_once_on_401(
    monkeypatch, access_token, list_results, expectation, expected_reauthentications
):
    reauthenticate = AsyncMock()
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.job.api.reauthenticate", reauthenticate)
    endpoint = MagicMock(spec=JobEndpoints)
    endpoint.auth.access_token = access_token
    endpoint.list.side_effect = list_results

    with expectation:
        assert await get_jobs_statuses_by_ids_async(endpoint, [CREATED_JOB["_id"]]) == ["active", "finished"]
    assert reauthenticate.await_args_list == [((endpoint.auth,),)] * expected_reauthentications
    assert endpoint.list.call_count == len(list_results)


AUTH_TOKEN = "auth-token-1"
JOB_ENDPOINT_ARGUMENTS = ("platform.mat3ra.com", 443, OWNER_ID, AUTH_TOKEN, "2018-10-01", True)
JOBS_QUERY: Dict[str, Any] = {"_id": {"$in": [CREATED_JOB["_id"]]}}
STATUS_PROJECTION: Dict[str, Any] = {"fields": {"status": 1}}
JOBS_FETCH_URL = (
    "https://platform.mat3ra.com:443/api/2018-10-01/jobs"
    "?query=%7B%22_id%22%3A+%7B%22%24in%22%3A+%5B%22job-1%22%5D%7D%7D"
    "&projection=%7B%22fields%22%3A+%7B%22status%22%3A+1%7D%7D"
)
BEARER_HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
X_AUTH_HEADERS = {"X-Account-Id": OWNER_ID, "X-Auth-Token": AUTH_TOKEN, "Content-Type": "application/json"}
ABORT_SIGNAL = "abort-signal"
FETCH_RESPONSE_OK = SimpleNamespace(ok=True, status=200, json=AsyncMock(return_value={"data": JOBS_WITH_STATUSES}))
FETCH_RESPONSE_401 = SimpleNamespace(ok=False, status=401)


class FakeJsException(Exception):
    message = "TypeError: network error"


FETCH_RESPONSE_BODY_FAILED = SimpleNamespace(ok=True, status=200, json=AsyncMock(side_effect=FakeJsException()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("access_token", "response", "expectation", "expected_headers"),
    [
        (ACCESS_TOKEN, FETCH_RESPONSE_OK, contextlib.nullcontext(), BEARER_HEADERS),
        (None, FETCH_RESPONSE_OK, contextlib.nullcontext(), X_AUTH_HEADERS),
        (
            ACCESS_TOKEN,
            FETCH_RESPONSE_401,
            pytest.raises(requests.HTTPError, check=lambda error: error.response.status_code == 401),
            BEARER_HEADERS,
        ),
        (ACCESS_TOKEN, FETCH_RESPONSE_BODY_FAILED, pytest.raises(OSError, match="network error"), BEARER_HEADERS),
    ],
    ids=["bearer token", "X-Auth headers", "401", "network error while reading the body"],
)
async def test_list_jobs_with_fetch(monkeypatch, access_token, response, expectation, expected_headers):
    pyfetch = AsyncMock(return_value=response)
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.job.api.pyfetch", pyfetch)
    monkeypatch.setattr("mat3ra.notebooks_utils.core.entity.job.api.JsException", FakeJsException)
    stale_access_token = "stale-access-token" if access_token else None
    auth_context = AuthContext(access_token=stale_access_token, account_id=OWNER_ID, auth_token=AUTH_TOKEN)
    endpoint = JobEndpoints(*JOB_ENDPOINT_ARGUMENTS, auth=auth_context)
    auth_context.access_token = access_token

    with expectation:
        assert await _list_jobs_with_fetch(endpoint, JOBS_QUERY, STATUS_PROJECTION, ABORT_SIGNAL) == JOBS_WITH_STATUSES
    pyfetch.assert_awaited_once_with(JOBS_FETCH_URL, headers=expected_headers, signal=ABORT_SIGNAL)
