from typing import Optional

from mat3ra.ide.compute import Compute, QueueName


def get_compute(client, cluster_name: Optional[str] = None, queue=QueueName.D, ppn: int = 1) -> Compute:
    """
    Compute configuration on an available cluster, or a clear error saying none is available.

    Args:
        client: An authenticated APIClient.
        cluster_name: Substring of the desired cluster's hostname; the first available is used
            when omitted.
        queue: Queue to submit to.
        ppn: Processors per node.
    """
    clusters = client.clusters.list()
    if not clusters:
        raise RuntimeError(
            "No compute cluster is available on this account. A cluster node has to be running "
            "and registered before jobs can be submitted."
        )
    if cluster_name is None:
        return Compute(cluster=clusters[0], queue=queue, ppn=ppn)
    matches = [c for c in clusters if cluster_name in c["hostname"]]
    if not matches:
        available = ", ".join(c["hostname"] for c in clusters)
        raise RuntimeError(f"No cluster matching {cluster_name!r}. Available: {available}")
    return Compute(cluster=matches[0], queue=queue, ppn=ppn)
