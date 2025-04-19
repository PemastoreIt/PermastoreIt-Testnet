# --- PermastoreIt Python SDK ---

import requests
import os
from typing import Dict, List, Optional, Any
import mimetypes

# --- Custom Exceptions ---

class PermastoreItError(Exception):
    """Base exception for SDK errors."""
    pass

class APIError(PermastoreItError):
    """Raised for non-2xx API responses."""
    def __init__(self, status_code: int, detail: Optional[str] = None, response_text: Optional[str] = None):
        self.status_code = status_code
        # Provide a more informative default message
        self.detail = detail or f"Server returned status {status_code}"
        self.response_text = response_text or "" # Store raw response text if needed
        super().__init__(f"API Error {status_code}: {self.detail}")

class NetworkError(PermastoreItError):
    """Raised for connection, timeout, or other request errors."""
    pass

class FileNotFoundErrorOnServer(APIError):
     """Raised specifically for 404 errors when expecting a file/resource."""
     def __init__(self, resource_id: str): # Changed to generic resource_id
        self.resource_id = resource_id
        super().__init__(404, f"Resource '{resource_id}' not found on server.")

class ZKPDisabledError(APIError):
    """Raised when ZKP functionality is requested but disabled on the server."""
    def __init__(self):
        super().__init__(501, "ZKP is not enabled on the target node.")

# --- Client Class ---

class PermastoreItClient:
    """
    A client library for interacting with the PermaStore 1.2.0 API.

    Example Usage:
        client = PermastoreItClient(base_url="http://127.0.0.1:5000")
        status = client.get_status()
        upload_result = client.upload("my_local_file.txt")
        client.download(upload_result['hash'], save_dir="downloaded_files")
    """
    def __init__(self, base_url: str = "http://localhost:5000", timeout: int = 60):
        """
        Initializes the client to connect to a PermastoreIt node.

        Args:
            base_url: The base URL of the PermastoreIt node API
                      (e.g., "http://127.0.0.1:5000"). Should not end with '/'.
            timeout: Default timeout in seconds for API requests.
        """
        self.base_url = base_url.rstrip('/') # Remove trailing slash if present
        self.timeout = timeout
        self.session = requests.Session() # Use a session for connection reuse & header persistence
        # Example: Set default headers if needed
        # self.session.headers.update({'Accept': 'application/json'})

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Internal helper method for making API requests.

        Handles URL construction, default timeout, and basic error checking,
        raising custom SDK exceptions.

        Args:
            method: HTTP method (e.g., "GET", "POST").
            endpoint: API endpoint path (e.g., "/status", "/upload").
            **kwargs: Additional arguments passed to requests.request
                      (e.g., params, data, json, files, stream, headers).

        Returns:
            requests.Response object on success.

        Raises:
            NetworkError: For connection, timeout, or other request issues.
            APIError: For non-2xx HTTP status codes from the server.
            FileNotFoundErrorOnServer: For 404 errors on specific resource paths.
            ZKPDisabledError: For 501 errors related to ZKP.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        kwargs.setdefault('timeout', self.timeout) # Apply default timeout

        try:
            response = self.session.request(method, url, **kwargs)

            # Check for non-successful status codes (client/server errors)
            if not response.ok:
                 detail = None
                 raw_text = response.text # Store raw text for debugging
                 try:
                     data = response.json()
                     detail = data.get("detail")
                 except requests.exceptions.JSONDecodeError:
                     detail = raw_text[:200] if raw_text else f"No detail provided (Status: {response.status_code})"

                 # Raise specific errors based on status code and context
                 if response.status_code == 404:
                      path_parts = endpoint.lstrip('/').split('/')
                      if len(path_parts) == 2 and path_parts[0] in ["download", "file-info", "zk-proof"]:
                          resource_id = path_parts[1]
                          raise FileNotFoundErrorOnServer(resource_id)
                      else:
                           raise APIError(response.status_code, detail or "Resource not found", raw_text)
                 elif response.status_code == 501 and "zkp" in endpoint.lower():
                      raise ZKPDisabledError()
                 else:
                      # General API error for other 4xx/5xx codes
                     raise APIError(response.status_code, detail, raw_text)

            return response # Return successful response object

        except requests.exceptions.Timeout as e:
             raise NetworkError(f"Request timed out connecting to {url}: {e}") from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(f"Connection error connecting to {url}: {e}") from e
        except requests.exceptions.RequestException as e: # Catch other request errors
            raise NetworkError(f"Network request error for {url}: {e}") from e

    # --- Public SDK Methods ---

    def get_root_message(self) -> Dict[str, str]:
        """Gets the welcome message from the root endpoint ('/')."""
        response = self._make_request("GET", "/")
        return response.json()

    def get_status(self) -> Dict[str, Any]:
        """Gets the operational status of the node."""
        response = self._make_request("GET", "/status")
        return response.json()

    def get_health(self) -> Dict[str, Any]:
        """Gets the health check report of the node."""
        response = self._make_request("GET", "/health")
        # Health check might return non-200 on degraded, but .ok checks for 2xx
        # If you need the degraded info, you might need to handle 503 specifically
        # or adjust _make_request to allow certain non-2xx codes for health.
        # For simplicity now, assume 200 is healthy.
        return response.json()

    def upload(self, file_path: str) -> Dict[str, Any]:
        """
        Uploads a file from the given local path to the node.

        Args:
            file_path: The local path to the file to upload.

        Returns:
            A dictionary containing the upload result (status, hash, size, etc.).

        Raises:
            FileNotFoundError: If the local file_path does not exist.
            PermastoreItError: If reading the local file fails.
            APIError: If the server returns an error (e.g., invalid type, too large).
            NetworkError: If there's a connection issue.
        """
        if not os.path.isfile(file_path): # More specific check
            raise FileNotFoundError(f"Local file not found or is not a regular file: {file_path}")

        file_name = os.path.basename(file_path)

         # --- Start Modification ---
         # Explicitly guess the MIME type
        content_type, encoding = mimetypes.guess_type(file_path)
        if content_type is None:
              # Fallback if guess fails - or you could raise an error
              content_type = 'application/octet-stream'
              print(f"Warning: Could not guess MIME type for {file_name}. Sending as {content_type}", file=sys.stderr) # Use stderr for warnings
         # --- End Modification ---

        try:
            with open(file_path, 'rb') as f:
                  # --- Modified files dictionary ---
                  # Pass tuple: (filename, file_object, content_type)
                files = {'file': (file_name, f, content_type)}
                  # --- End Modification ---
                # Consider a longer timeout for uploads
                upload_timeout = max(self.timeout * 2, 120) # e.g., double default or 2 mins
                response = self._make_request("POST", "/upload", files=files, timeout=upload_timeout)
                # Note: Server returns 201 for new, 200 for dedupe. _make_request checks .ok (2xx)
                return response.json()
        except IOError as e:
             raise PermastoreItError(f"Failed to read local file {file_path}: {e}") from e
        # APIError and NetworkError are handled by _make_request


    def download(self, file_hash: str, save_dir: str, save_filename: Optional[str] = None) -> str:
        """
        Downloads a file by its hash and saves it to a specified directory.

        Args:
            file_hash: The SHA-256 hash of the file to download.
            save_dir: The directory where the file should be saved.
                      It will be created if it doesn't exist.
            save_filename: Optional. The name to save the file as.
                           If None, uses the file hash as the filename.

        Returns:
            The full path to the successfully downloaded file.

        Raises:
            FileNotFoundErrorOnServer: If the file hash is not found on the server (404).
            APIError: For other server errors during download request.
            NetworkError: If there's a connection issue.
            PermastoreItError: If creating the directory or writing the file fails.
        """
        if not save_filename:
            save_filename = file_hash # Default to using hash

        # Ensure save directory exists
        try:
            os.makedirs(save_dir, exist_ok=True)
        except OSError as e:
             raise PermastoreItError(f"Failed to create save directory '{save_dir}': {e}") from e

        full_save_path = os.path.join(save_dir, save_filename)

        try:
            # Use stream=True for potentially large files
            response = self._make_request("GET", f"/download/{file_hash}", stream=True)

            # Write the content chunk by chunk
            with open(full_save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024): # 1MB chunks
                    f.write(chunk)

            return full_save_path
        # Let APIError (including FileNotFoundErrorOnServer), NetworkError propagate from _make_request
        except IOError as e: # Catch errors writing the file
             # Clean up potentially partially written file
             try: os.remove(full_save_path)
             except OSError: pass
             raise PermastoreItError(f"Failed to write downloaded file to '{full_save_path}': {e}") from e
        except Exception as e: # Catch other unexpected errors during download/save
             # Clean up potentially partially written file
             try: os.remove(full_save_path)
             except OSError: pass
             raise PermastoreItError(f"Unexpected error during download/save: {e}") from e


    def list_files(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
         """
         Retrieves metadata for stored files, optionally limited.

         Args:
             limit: Optional maximum number of recent files to return.

         Returns:
             A list of file metadata dictionaries.

         Raises:
            APIError: For server errors during listing.
            NetworkError: If there's a connection issue.
         """
         params = {}
         if limit is not None:
             if not isinstance(limit, int) or limit < 1:
                 raise ValueError("Limit must be a positive integer.")
             params['limit'] = limit
         response = self._make_request("GET", "/files", params=params)
         return response.json()


    def get_file_info(self, file_hash: str) -> Dict[str, Any]:
        """
        Gets metadata for a specific file hash from the blockchain record.

        Args:
            file_hash: The SHA-256 hash of the file.

        Returns:
            A dictionary containing the file's metadata.

        Raises:
            FileNotFoundErrorOnServer: If the file hash is not found (404).
            APIError: For other server errors.
            NetworkError: If there's a connection issue.
        """
        # FileNotFoundErrorOnServer raised by _make_request if 404 occurs
        response = self._make_request("GET", f"/file-info/{file_hash}")
        return response.json()

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Searches for files by query (matches filenames and tags).

        Args:
            query: The search term.
            limit: The maximum number of results to return (default 10).

        Returns:
            A list of search result dictionaries, sorted by relevance.

        Raises:
            APIError: For server errors during search.
            NetworkError: If there's a connection issue.
        """
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("Limit must be a positive integer.")
        params = {'query': query, 'limit': limit}
        response = self._make_request("GET", "/search", params=params)
        return response.json()

    def get_zk_proof(self, file_hash: str) -> Dict[str, Any]:
        """
        Gets the Zero-Knowledge Proof for a file hash.

        Args:
            file_hash: The SHA-256 hash of the file.

        Returns:
            A dictionary containing the ZKP details (proof, challenge, algorithm).

        Raises:
            FileNotFoundErrorOnServer: If the file hash is not found (404).
            ZKPDisabledError: If ZKP is disabled on the server (501).
            APIError: For other server errors.
            NetworkError: If there's a connection issue.
        """
        # Specific errors (404, 501) handled by _make_request
        response = self._make_request("GET", f"/zk-proof/{file_hash}")
        return response.json()

# --- Example Usage (if script is run directly) ---
if __name__ == '__main__':
    print("PermastoreIt SDK Example Usage")
    # Replace with the actual URL of your running PermastoreIt node
    NODE_URL = "http://127.0.0.1:5000"
    client = PermastoreItClient(base_url=NODE_URL)

    try:
        print(f"\n--- Checking Node Status ({NODE_URL}) ---")
        status = client.get_status()
        print(f"Status: {status}")

        print(f"\n--- Checking Node Health ---")
        health = client.get_health()
        print(f"Health: {health}")

        # --- Upload Example ---
        print("\n--- Uploading File ---")
        test_filename = "sdk_test_upload.txt"
        try:
            with open(test_filename, "w") as f:
                f.write(f"Test content from SDK at {time.time()}")
            print(f"Created test file: {test_filename}")

            upload_result = client.upload(test_filename)
            print(f"Upload Result: {upload_result}")
            uploaded_hash = upload_result.get('hash')

            if uploaded_hash:
                 # --- Get Info Example ---
                 print(f"\n--- Getting File Info ({uploaded_hash}) ---")
                 info = client.get_file_info(uploaded_hash)
                 print(f"File Info: {info}")

                 # --- Search Example ---
                 print(f"\n--- Searching for 'sdk_test' ---")
                 search_results = client.search("sdk_test")
                 print(f"Search Results: {search_results}")

                  # --- ZKP Example ---
                 print(f"\n--- Getting ZKP ({uploaded_hash}) ---")
                 try:
                     zkp = client.get_zk_proof(uploaded_hash)
                     print(f"ZKP Result: {zkp}")
                 except ZKPDisabledError as e:
                      print(f"ZKP Test Skipped: {e}")


                 # --- Download Example ---
                 print(f"\n--- Downloading File ({uploaded_hash}) ---")
                 download_dir = "sdk_downloads"
                 downloaded_path = client.download(uploaded_hash, save_dir=download_dir)
                 print(f"File downloaded to: {downloaded_path}")
                 # You can optionally verify the content here
                 # with open(downloaded_path, "r") as f: print(f"Downloaded content: {f.read()}")

                 # --- List Files Example ---
                 print(f"\n--- Listing Recent Files (limit 5) ---")
                 recent_files = client.list_files(limit=5)
                 print("Recent Files:")
                 for f_info in recent_files:
                     print(f"  - Hash: {f_info.get('hash', 'N/A')}, Name: {f_info.get('filename', 'N/A')}, Time: {f_info.get('timestamp', 'N/A')}")


            else:
                 print("Upload did not return a hash.")

        except FileNotFoundError:
             print(f"Error: Test file '{test_filename}' not found or could not be created.")
        finally:
            # Clean up test file
            if os.path.exists(test_filename):
                try: os.remove(test_filename)
                except OSError: pass
            # Clean up download dir if desired
            # if os.path.exists(download_dir):
            #    try: shutil.rmtree(download_dir)
            #    except OSError: pass


        # --- Test Error Handling ---
        print("\n--- Testing Error Handling ---")
        non_existent_hash = "a"*64 # 64 'a's - unlikely to exist
        try:
            print(f"Attempting to get info for non-existent hash: {non_existent_hash}")
            client.get_file_info(non_existent_hash)
        except FileNotFoundErrorOnServer as e:
            print(f"Successfully caught expected error: {e}")
        except Exception as e:
             print(f"Caught unexpected error: {e}")


    except PermastoreItError as e:
        print(f"\nSDK Error: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred during SDK example run: {e}")