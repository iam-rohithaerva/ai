from mcp.server.mcpserver import MCPServer
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

server = MCPServer("Kubernetes MCP")


def get_kubernetes_client():
    # Reads the cluster address and credentials from ~/.kube/config
    config.load_kube_config()
    return client.CoreV1Api()


@server.tool()
def list_pods(namespace: str = "all") -> str:
    """List Kubernetes pods and their status."""
    try:
        v1 = get_kubernetes_client()

        if namespace == "all":
            pods = v1.list_pod_for_all_namespaces()
        else:
            pods = v1.list_namespaced_pod(namespace=namespace)

        if not pods.items:
            return "No pods found."

        results = []
        for pod in pods.items:
            results.append(
                f"{pod.metadata.namespace}/{pod.metadata.name}: {pod.status.phase}"
            )
        return "\n".join(results)

    except ApiException as e:
        return f"Kubernetes API error: {e.reason}"


if __name__ == "__main__":
    server.run(transport="streamable-http")   # default port 8000, path /mcp
