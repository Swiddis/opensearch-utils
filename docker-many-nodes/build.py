import sys
import json

node_template = """  {NODE}: # This is also the hostname of the container within the Docker network (i.e. https://opensearch-node1/)
    image: opensearchstaging/opensearch:2.14.0 # Specifying the latest available image - modify if you want a specific version
    container_name: {NODE}
    environment:
      - cluster.name=opensearch-cluster # Name the cluster
      - node.name={NODE} # Name the node that will run in this container
      - discovery.seed_hosts={NODES} # Nodes to look for when discovering the cluster
      - cluster.initial_cluster_manager_nodes={NODES} # Nodes eligible to serve as cluster manager
      - bootstrap.memory_lock=true # Disable JVM heap memory swapping
      - "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m" # Set min and max JVM heap sizes to at least 50% of system RAM
      - OPENSEARCH_INITIAL_ADMIN_PASSWORD=myStrongPassword123!    # Sets the demo admin user password when using demo configuration, required for OpenSearch 2.12 and later
    ulimits:
      memlock:
        soft: -1 # Set memlock to unlimited (no soft or hard limit)
        hard: -1
      nofile:
        soft: 65536 # Maximum number of open files for the opensearch user - set to at least 65536
        hard: 65536
    volumes:
      - {NODE}:/usr/share/opensearch/data # Creates volume called opensearch-data1 and mounts it to the container
    ports:
      - {PORT1}:9200 # REST API
      - {PORT2}:9600 # Performance Analyzer
    networks:
      - opensearch-net # All of the containers will join the same Docker bridge network
"""

dashboard_template = """
  opensearch-dashboards:
    image: opensearchstaging/opensearch-dashboards:2.14.0 # Make sure the version of opensearch-dashboards matches the version of opensearch installed on other nodes
    container_name: opensearch-dashboards
    ports:
      - 5601:5601 # Map host port 5601 to container port 5601
    expose:
      - "5601" # Expose port 5601 for web access to OpenSearch Dashboards
    environment:
      OPENSEARCH_HOSTS: '{NODE_LINKS}' # Define the OpenSearch nodes that OpenSearch Dashboards will query
    networks:
      - opensearch-net
"""


def port(n, base=9200):
    return str(base + n - 1)


def node(n):
    return f"opensearch-node{n}"


def nodes(n):
    return ",".join(node(i) for i in range(1, n + 1))


def links(n):
    return json.dumps([f"https://{node(i)}:{port(i)}" for i in range(1, n + 1)], separators=(',', ':'))


if __name__ == "__main__":
    node_count = int(sys.argv[1])

    result = "version: '3'\n\nservices:\n"
    for i in range(1, node_count + 1):
        result += (
            node_template.replace("{NODE}", node(i))
            .replace("{PORT1}", port(i))
            .replace("{PORT2}", port(i, 9600))
            .replace("{NODES}", nodes(node_count))
        )
    result += dashboard_template.replace("{NODE_LINKS}", links(node_count))

    result += "\n\nvolumes:\n"
    for i in range(1, node_count + 1):
        result += f"  {node(i)}:\n"
    result += "networks:\n  opensearch-net:\n"

    with open("docker-compose.yml", "w") as output:
        output.write(result)
