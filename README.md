# PermastoreIt Testnet Information (Alpha Phase)

## Welcome!

Thank you for participating in the alpha testnet for PermastoreIt! This is an early version of a decentralized storage system featuring AI-driven deduplication and Zero-Knowledge Proof capabilities, now using a Kademlia DHT for peer discovery.

Your testing and feedback are crucial for identifying bugs, evaluating performance, and guiding future development.

**PLEASE READ CAREFULLY: This is an ALPHA testnet. Expect bugs, potential network instability, and possible data resets. Do NOT store any critical or sensitive data on this network.**

## Testnet Goals

The primary goals for this phase of the testnet are:

1.  **Validate Kademlia DHT:** Test the reliability of peer discovery, bootstrapping, and basic DHT operations (`set`/`get`) in a multi-node environment.
2.  **Test Core P2P Operations:** Verify file upload, AI deduplication, metadata recording (using per-node SQLite backend), P2P download (via DHT lookup), file info retrieval, search, and ZKP generation across multiple nodes.
3.  **Gather Initial Metrics:** Collect preliminary data on API performance, upload/download times, and DHT operation timings (via logs and potentially future metrics endpoints).
4.  **Identify Bugs & Bottlenecks:** Uncover issues related to concurrency, error handling, network communication, component interaction, and the Kademlia implementation itself.
5.  **Evaluate Usability:** Gather feedback on the setup process and the CLI tool usage.

## Features Under Test

* P2P Peer Discovery via Kademlia DHT (replacing static `peers.txt`)
* File Upload with AI Semantic Deduplication (Text & Images)
* Metadata Recording using per-node SQLite database (replaces `blockchain.json`)
* File Download (checking local first, then finding providers via DHT)
* File Info Retrieval (`/file-info`) & Listing (`/files`)
* File Search (`/search` based on filename/tags)
* ZKP Generation (`/zk-proof`)
* Basic Node Status/Health (`/status`, `/health`)
* Command Line Interface (`permastoreit_cli.py`) for interaction

## Known Limitations & Warnings

* **ALPHA SOFTWARE:** Expect bugs, instability, and potential breaking changes or network resets without notice.
* **NO DATA PERSISTENCE GUARANTEE:** Data stored on the testnet may be lost. Do not use it for important files.

## Prerequisites

* **Docker & Docker Compose:** You need Docker and Docker Compose installed and running on your system (Linux, macOS, or Windows with WSL2 recommended).
* **Git:** To clone this testnet repository.
* **Network Access:** Your node needs stable internet access.
* **Firewall Configuration:** You MUST open the following ports on your machine/firewall for incoming traffic:
    * **TCP Port (API):** The port specified in your `config.json` (`port`, default 5000).
    * **UDP Port (Kademlia):** The port specified in your `config.json` (`network.kademlia_port`, default 8468).

## How to Participate (Setup Steps)

1.  **Clone this Repository:**
    ```bash
    git clone <URL_of_this_Testnet_Repository>
    cd <testnet-repository-directory>
    ```
2.  **Create Configuration:** Copy the example configuration file:
    ```bash
    cp config.json.example config.json
    ```
3.  **Edit `config.json`:** Open `config.json` in a text editor and **carefully** set the following:
    * `network.bootstrap_nodes`: Replace the placeholder(s) with the actual IP addresses and Kademlia ports of the official testnet bootstrap nodes (see section below). **Do NOT leave this empty unless you are running a bootstrap node yourself.**
    * `network.node_api_url`: **Crucially**, set this to the publicly reachable URL of *your* node's API server (e.g., `http://YOUR_PUBLIC_IP:5000`). Other nodes need this URL (obtained via the DHT) to download files from you. If you are behind NAT and don't have a public IP/port forwarding, direct downloads from peers might fail.
    * (Optional) Adjust `network.kademlia_port` or `port` if needed (ensure firewall rules match and update `docker-compose.yaml` port mappings accordingly).
4.  **Ensure Firewall Ports are Open:** Verify that incoming TCP traffic is allowed on your API port and incoming UDP traffic is allowed on your Kademlia port.
5.  **Build and Run:** Start the PermastoreIt node using Docker Compose:
    ```bash
    docker compose up --build -d
    ```
    *(The first time might take a while to download the base image and build)*
6.  **Check Logs:** Monitor the startup logs to ensure everything initializes correctly and Kademlia bootstrapping completes:
    ```bash
    docker compose logs -f server
    ```
    Look for "DHT Server listening...", "Bootstrapping complete...", and "Uvicorn running...".

## Using the CLI Tool

A command-line tool (`permastoreit_cli.py`) is included in this repository for interacting with your node and the network.

* **Prerequisites:** Python 3.9+ and `pip`. Install dependencies:
    ```bash
    pip install -r requirements.txt
    # (Assuming requirements.txt in the testnet repo includes 'click' and 'requests')
    # OR: pip install click requests
    ```
* **Basic Usage:**
    ```bash
    # Target your local node (default URL: http://localhost:5000)
    python permastoreit_cli.py status
    python permastoreit_cli.py upload /path/to/your/file.txt
    python permastoreit_cli.py list --limit 10
    python permastoreit_cli.py download <FILE_HASH> -o ./output_dir

    # Target a different node
    python permastoreit_cli.py --url http://<OTHER_NODE_IP>:PORT status
    ```
* **See Help:** For all commands and options:
    ```bash
    python permastoreit_cli.py --help
    python permastoreit_cli.py upload --help
    ```

## What to Test & How to Provide Feedback

We appreciate testing related to:

* **Basic Operations:** Uploading various file types/sizes (within limits), downloading files (from your node and attempting from others via hash), searching, getting file info, checking status/health.
* **Kademlia/P2P:**
    * Can your node successfully bootstrap?
    * Can you retrieve files uploaded by *other* testnet participants (allow time for DHT propagation)?
    * Observe node status (`peers_connected` count - note: this counts DHT router entries, not active connections).
* **AI Deduplication:** Try uploading identical files, slightly modified text files, or similar images. Does the `status` in the upload response correctly show "deduplicated"?
* **CLI Tool:** Is the CLI easy to use? Is the output clear? Any bugs?
* **Stability:** Does the node run reliably? Does it crash unexpectedly?

**Providing Feedback:**

* Please report bugs, issues, or suggestions via **(https://github.com/PemastoreIt/PermastoreIt-Testnet/issues)**
* For general discussion or questions, join our Discord! **https://discord.gg/MSnmxC3cwG**

Please include relevant logs, steps to reproduce, your `config.json` (excluding secrets if any were added), and details about your environment when reporting issues.

## Bootstrap Node Information

Connect your node to the PermastoreIt testnet using the following bootstrap node(s):

* `["<Bootstrap_Node_1_IP>", 8468]`
* `["<Bootstrap_Node_2_IP>", 8468]` *(Optional)*

*(**Maintainer Note:** Replace `<Bootstrap_Node_X_IP>` with the actual, stable public IP addresses or domain names of your designated bootstrap nodes before sharing this document.)*

## Disclaimer

This PermastoreIt testnet software is experimental alpha software provided "AS IS", without warranty of any kind. Use it at your own risk. Data stored on the testnet is not guaranteed to be persistent, secure, or private, and may be deleted at any time. Do not use the testnet for storing sensitive or critical information.

---

Thank you for helping test PermastoreIt!
