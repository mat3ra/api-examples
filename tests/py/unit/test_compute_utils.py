import pytest
from mat3ra.ide.compute import QueueName
from mat3ra.notebooks_utils import compute as compute_module
from mat3ra.notebooks_utils.compute import get_compute

CLUSTERS = [{"hostname": "cluster-001.mat3ra.com"}, {"hostname": "cluster-007.mat3ra.com"}]


class FakeClusters:
    def __init__(self, clusters):
        self._clusters = clusters

    def list(self):
        return self._clusters


class FakeClient:
    def __init__(self, clusters):
        self.clusters = FakeClusters(clusters)


@pytest.fixture
def compute_as_kwargs(monkeypatch):
    monkeypatch.setattr(compute_module, "Compute", lambda **kwargs: kwargs)


def test_get_compute_defaults_to_the_first_cluster(compute_as_kwargs):
    compute = get_compute(FakeClient(CLUSTERS), queue=QueueName.D, ppn=2)
    assert compute == {"cluster": CLUSTERS[0], "queue": QueueName.D, "ppn": 2}


def test_get_compute_matches_a_hostname_substring(compute_as_kwargs):
    assert get_compute(FakeClient(CLUSTERS), "007")["cluster"] == CLUSTERS[1]


def test_get_compute_says_when_no_cluster_is_available(compute_as_kwargs):
    with pytest.raises(RuntimeError, match="No compute cluster is available"):
        get_compute(FakeClient([]))


def test_get_compute_lists_the_clusters_on_a_name_miss(compute_as_kwargs):
    with pytest.raises(RuntimeError, match="cluster-001.mat3ra.com, cluster-007.mat3ra.com"):
        get_compute(FakeClient(CLUSTERS), "cluster-042")
