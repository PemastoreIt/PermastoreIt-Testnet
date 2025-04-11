#!/usr/bin/env python
import click
import os
import json
import sys
import time
import glob # For bulk upload
from typing import Optional, List, Dict, Any # Added more types

# --- Import Rich ---
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.pretty import pretty_repr # For better dict printing

# --- Import SDK ---
# Assume SDK is in the same directory or installable
try:
    from permastoreit_sdk import (
        PermastoreItClient,
        PermastoreItError,
        APIError,
        NetworkError,
        FileNotFoundErrorOnServer,
        ZKPDisabledError
    )
except ImportError:
    # Use print here as Rich console might not be ready
    print("Error: Failed to import PermastoreIt SDK. Make sure permastoreit_sdk.py is accessible.")
    sys.exit(1)

# --- Initialize Rich Console ---
console = Console(stderr=True) # Use stderr for messages, stdout for data if needed

# --- Helper Functions ---

def print_output(data: Any, output_format: str, pretty: bool = True):
    """Helper to print data in specified format using Rich."""
    if output_format == 'json':
        # Compact JSON for machine readability
        # Use stdout for JSON data output
        print(json.dumps(data, separators=(',', ':')))
    else:
        # Pretty print using Rich for text format (to stderr)
        if isinstance(data, (dict, list)):
             # Use rich's pretty representation or Syntax highlighting
             # console.print(data) # Rich's default pretty print
             try:
                # Try syntax highlighting if it's likely JSON structure
                syntax = Syntax(json.dumps(data, indent=2, sort_keys=True), "json", theme="default", line_numbers=False)
                console.print(syntax)
             except Exception:
                 console.print(data) # Fallback to default rich print
        else:
            # Print simple strings directly
            console.print(str(data))


def handle_sdk_error(e, exit_on_error=True):
    """Helper to print SDK errors using Rich Panel."""
    error_title = "[bold red]Error[/]"
    message = "An unexpected error occurred."

    if isinstance(e, FileNotFoundErrorOnServer):
        message = f"Resource '[bold cyan]{e.resource_id}[/]' not found on the server (404)."
    elif isinstance(e, ZKPDisabledError):
         message = f"{e}"
         error_title = "[bold yellow]Warning[/]" # Treat as warning
    elif isinstance(e, APIError):
        message = f"API Error ([bold]{e.status_code}[/]): {e.detail}"
    elif isinstance(e, NetworkError):
        message = f"Network Error: {e}"
    elif isinstance(e, FileNotFoundError): # Local file not found
         message = f"Local File Error: {e}"
    elif isinstance(e, PermastoreItError): # General SDK error
        message = f"SDK Error: {e}"
    else: # Unexpected errors
        message = f"An unexpected error occurred: {e}"

    console.print(Panel(message, title=error_title, border_style="red", expand=False))

    if exit_on_error:
        sys.exit(1)
    else:
        return message # Return message if not exiting

def common_options(func):
    """Decorator for common options like output format."""
    # Note: Default is now 'text'. JSON output goes to stdout, text/messages to stderr.
    func = click.option('--output-format', type=click.Choice(['text', 'json'], case_sensitive=False), default='text', help='Output format (text to stderr, json lines to stdout).', show_default=True)(func)
    return func

# --- CLI Command Group ---

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--url', default="http://localhost:5000", help="Base URL of the PermastoreIt node API.", envvar='PERMASTOREIT_URL', show_default=True)
@click.option('--timeout', type=int, default=60, help="Default request timeout in seconds.", show_default=True)
@click.version_option(version="0.2.0", prog_name="PermastoreIt CLI") # Add version
@click.pass_context
def cli(ctx, url, timeout):
    """
    Command Line Interface for interacting with and testing a PermastoreIt node.

    Example: python permastoreit_cli.py --url <NODE_URL> upload <FILE>
    """
    ctx.ensure_object(dict)
    try:
        ctx.obj['CLIENT'] = PermastoreItClient(base_url=url, timeout=timeout)
        ctx.obj['BASE_URL'] = url
        ctx.obj['OUTPUT_FORMAT'] = 'text' # Default, subcommands can override via param

    except Exception as e:
         console.print(Panel(f"Failed to initialize client for URL '{url}': {e}", title="[bold red]Initialization Error[/]", border_style="red"))
         sys.exit(1)

# --- CLI Subcommands ---

@cli.command()
@common_options
@click.pass_context
def status(ctx, output_format):
    """Get the operational status of the node."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    ctx.obj['OUTPUT_FORMAT'] = output_format # Store format
    console.print(f"Fetching status from [cyan]{client.base_url}[/]...")
    try:
        t_start = time.perf_counter()
        result = client.get_status()
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000
        result['query_time_ms'] = duration_ms # Add timing to result dict

        print_output(result, output_format) # Use helper

    except Exception as e:
        handle_sdk_error(e)

@cli.command()
@common_options
@click.pass_context
def health(ctx, output_format):
    """Check the health of the node and its components."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Fetching health from [cyan]{client.base_url}[/]...")
    exit_code = 0
    try:
        t_start = time.perf_counter()
        result = client.get_health()
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000
        result['query_time_ms'] = duration_ms

        if output_format == 'json':
            print_output(result, output_format)
        else:
            # Print text format using Rich
            status_color = "green" if result.get('status') == 'healthy' else "yellow"
            console.print(Panel(f"Overall Status: [bold {status_color}]{result.get('status', 'UNKNOWN').upper()}[/]", title="Health Check", expand=False, border_style=status_color))

            table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
            table.add_column("Component", style="dim cyan", width=15)
            table.add_column("Status", style="white")

            components = result.get('components', {})
            for comp, comp_status in components.items():
                status_text = "[green]OK[/]" if comp_status else "[bold red]FAIL[/]"
                table.add_row(comp.capitalize(), status_text)
            console.print(table)

            # Print other info
            console.print(f"  Node ID: {result.get('node_id', 'N/A')}")
            console.print(f"  Files Stored: {result.get('files_stored', 'N/A')}")
            console.print(f"  Blockchain Length: {result.get('blockchain_length', 'N/A')}")
            console.print(f"  DHT Peers (Known): {result.get('peers_connected', 'N/A')}")
            console.print(f"  Query Time: {duration_ms:.2f} ms")

        if result.get('status') != 'healthy':
             exit_code = 2 # Indicate unhealthy status via exit code
    except Exception as e:
        handle_sdk_error(e) # Exits with 1 on error
    sys.exit(exit_code)

@cli.command()
@click.argument('file_path', type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option('--repeat', '-r', type=int, default=1, help="Number of times to repeat the upload.", show_default=True)
@click.option('--delay', '-d', type=float, default=0, help="Delay in seconds between repetitions.", show_default=True)
@common_options
@click.pass_context
def upload(ctx, file_path, repeat, delay, output_format):
    """Upload a file to the PermastoreIt node, optionally repeating."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Uploading '[cyan]{os.path.basename(file_path)}[/]' to [cyan]{base_url}[/] ({repeat}x, delay {delay}s)...")

    results_data = []
    overall_success = True

    for i in range(repeat):
        if i > 0 and delay > 0:
            time.sleep(delay)
        if repeat > 1:
            console.print(f"-- Attempt {i+1}/{repeat} --")

        t_start = time.perf_counter()
        try:
            # TODO: Integrate rich progress bar if SDK supports callbacks or for large files
            result = client.upload(file_path)
            t_end = time.perf_counter()
            duration_ms = (t_end - t_start) * 1000
            result['upload_time_ms'] = duration_ms
            results_data.append({"success": True, "result": result})

            if output_format == 'text':
                status_color = 'green' if result.get('status') == 'success' else 'yellow'
                console.print(Panel(
                    f"Status: [bold {status_color}]{result.get('status', 'N/A').upper()}[/]\n"
                    f"Hash: [cyan]{result.get('hash', 'N/A')}[/]\n"
                    f"Size: {result.get('size', 'N/A')} bytes\n"
                    f"ZKP: {'Available' if result.get('zkp_available') else 'N/A'}\n"
                    f"Time: {duration_ms:.2f} ms\n"
                    f"Message: {result.get('message', '')}",
                    title=f"[bold]Upload Result {i+1}[/]",
                    border_style=status_color,
                    expand=False
                ))

        except Exception as e:
            t_end = time.perf_counter() # Still record time even on error
            duration_ms = (t_end - t_start) * 1000
            overall_success = False
            error_message = handle_sdk_error(e, exit_on_error=(repeat == 1)) # Only exit if not repeating
            results_data.append({"success": False, "error": error_message, "time_ms": duration_ms})
            # Error panel already printed by handle_sdk_error if exiting

    if output_format == 'json':
        for res in results_data:
            print_output(res, output_format) # Print each result as a JSON line

    if not overall_success and repeat > 1:
         sys.exit(1) # Exit with error if any repetition failed


@cli.command(name="upload-bulk")
@click.argument('directory_path', type=click.Path(exists=True, file_okay=False, readable=True))
@click.option('--pattern', '-p', default="*", help="Glob pattern for files (e.g., '*.txt').", show_default=True)
@click.option('--delay', '-d', type=float, default=0.1, help="Delay seconds between uploads.", show_default=True)
@common_options
@click.pass_context
def upload_bulk(ctx, directory_path, pattern, delay, output_format):
    """Upload all files matching a pattern from a directory."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Uploading files matching '[cyan]{pattern}[/]' from '[cyan]{directory_path}[/]' to [cyan]{base_url}[/]...")

    try:
        files_to_upload = [f for f in glob.glob(os.path.join(directory_path, pattern)) if os.path.isfile(f)]
    except Exception as e:
        console.print(Panel(f"Error finding files: {e}", title="[bold red]Error[/]", border_style="red"))
        sys.exit(1)

    if not files_to_upload:
        console.print("[yellow]No files found matching pattern.[/]")
        return

    console.print(f"Found {len(files_to_upload)} file(s).")
    results_data = []
    success_count = 0
    fail_count = 0

    # Use Rich Progress bar
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=console, # Use stderr console for progress
        transient=False # Keep progress bar after completion for bulk summary
    ) as progress:
        task = progress.add_task("[cyan]Uploading...", total=len(files_to_upload))

        for file_path in files_to_upload:
            if delay > 0: time.sleep(delay)
            # Update progress description
            progress.update(task, description=f"[cyan]Uploading {os.path.basename(file_path)}...")

            t_start = time.perf_counter()
            try:
                result = client.upload(file_path)
                t_end = time.perf_counter()
                duration_ms = (t_end - t_start) * 1000
                result['upload_time_ms'] = duration_ms
                result['source_file'] = file_path
                results_data.append({"success": True, "result": result})
                success_count += 1
            except Exception as e:
                t_end = time.perf_counter()
                duration_ms = (t_end - t_start) * 1000
                error_message = handle_sdk_error(e, exit_on_error=False) # Log error but continue bulk op
                results_data.append({"success": False, "source_file": file_path, "error": error_message, "time_ms": duration_ms})
                fail_count += 1
            progress.update(task, advance=1)

    console.print(f"\nBulk upload complete. Success: [green]{success_count}[/], Failed: [red]{fail_count}[/]")
    if output_format == 'json':
        # Print summary and then individual results
        summary = {"total_files": len(files_to_upload), "success": success_count, "failed": fail_count}
        print_output({"summary": summary}, output_format)
        for res in results_data:
            print_output(res, output_format)


@cli.command()
@click.argument('file_hash', type=click.STRING)
@click.option('--out-dir', '-o', default=".", help="Directory to save downloaded file.", type=click.Path(file_okay=False, writable=True))
@click.option('--name', '-n', default=None, help="Filename to save as (defaults to hash).", type=click.STRING)
@click.option('--repeat', '-r', type=int, default=1, help="Number of download repetitions.", show_default=True)
@click.option('--delay', '-d', type=float, default=0, help="Delay seconds between repetitions.", show_default=True)
@common_options
@click.pass_context
def download(ctx, file_hash, out_dir, name, repeat, delay, output_format):
    """Download a file by its hash, optionally repeating."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    save_filename_base = name if name else file_hash
    console.print(f"Downloading hash '[cyan]{file_hash}[/]' from [cyan]{base_url}[/] to '[cyan]{out_dir}[/]' ({repeat}x, delay {delay}s)...")

    results_data = []
    overall_success = True

    for i in range(repeat):
        save_filename = f"{save_filename_base}.{i}" if repeat > 1 else save_filename_base
        target_path = os.path.join(out_dir, save_filename)

        if i > 0 and delay > 0: time.sleep(delay)
        if repeat > 1: console.print(f"-- Attempt {i+1}/{repeat} -> {target_path} --")

        t_start = time.perf_counter()
        try:
            # TODO: Add rich progress bar if SDK provides download progress or file size known
            os.makedirs(out_dir, exist_ok=True)
            downloaded_path = client.download(file_hash, save_dir=out_dir, save_filename=save_filename)
            t_end = time.perf_counter()
            duration_ms = (t_end - t_start) * 1000
            result_data = {"downloaded_path": downloaded_path, "download_time_ms": duration_ms}
            results_data.append({"success": True, "result": result_data})
            if output_format == 'text':
                 console.print(Panel(
                     f"File downloaded to: [green]{downloaded_path}[/]\n"
                     f"Time: {duration_ms:.2f} ms",
                     title=f"[bold]Download Result {i+1}[/]",
                     border_style="green",
                     expand=False
                 ))

        except Exception as e:
            t_end = time.perf_counter()
            duration_ms = (t_end - t_start) * 1000
            overall_success = False
            error_message = handle_sdk_error(e, exit_on_error=(repeat == 1))
            results_data.append({"success": False, "error": error_message, "time_ms": duration_ms})
            # Error panel already printed if exiting

    if output_format == 'json':
        for res in results_data:
            print_output(res, output_format)

    if not overall_success and repeat > 1:
         sys.exit(1)


@cli.command(name="list")
@click.option('--limit', '-l', type=click.INT, default=None, help="Limit number of results.")
@common_options
@click.pass_context
def list_files(ctx, limit, output_format):
    """List metadata of stored files (most recent first)."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Listing files from [cyan]{base_url}[/] (limit: {limit or 'All'})...")
    try:
        t_start = time.perf_counter()
        results = client.list_files(limit=limit)
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000

        if output_format == 'json':
             output_data = {"files": results, "query_time_ms": duration_ms}
             print_output(output_data, output_format) # Single JSON line for list
        else:
            console.print(f"Query Time: {duration_ms:.2f} ms")
            if not results:
                console.print("[yellow]No files found.[/]")
                return

            table = Table(title=f"Stored Files (Limit: {limit or 'All'})", box='ROUNDED', show_header=True, header_style="bold magenta")
            table.add_column("Hash", style="dim cyan", width=18, overflow='fold')
            table.add_column("Timestamp", style="white", width=20)
            table.add_column("Size (Bytes)", style="white", justify="right", width=12)
            table.add_column("Content Type", style="yellow", overflow='fold')
            table.add_column("Filename", style="green", overflow='fold')

            for item in results:
                 ts_raw = item.get('timestamp', 0)
                 try: ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts_raw)) if ts_raw else 'N/A'
                 except ValueError: ts = 'Invalid Timestamp'
                 table.add_row(
                     item.get('hash', 'N/A')[:18], # Truncate hash
                     ts,
                     str(item.get('size', 0)),
                     item.get('content_type', '?'),
                     item.get('filename', 'N/A')
                 )
            console.print(table)

    except Exception as e:
        handle_sdk_error(e)

@cli.command()
@click.argument('file_hash', type=click.STRING)
@common_options
@click.pass_context
def info(ctx, file_hash, output_format):
    """Get metadata information for a specific file hash."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Getting info for hash '[cyan]{file_hash}[/]' from [cyan]{base_url}[/]...")
    try:
        t_start = time.perf_counter()
        result = client.get_file_info(file_hash)
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000
        result['query_time_ms'] = duration_ms # Add timing info

        print_output(result, output_format) # Use helper

    except Exception as e:
        handle_sdk_error(e)

@cli.command()
@click.argument('query', type=click.STRING)
@click.option('--limit', '-l', type=click.INT, default=10, help="Limit number of results.")
@common_options
@click.pass_context
def search(ctx, query, limit, output_format):
    """Search for files by filename or tags."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Searching for '[cyan]{query}[/]' on [cyan]{base_url}[/] (limit: {limit})...")
    try:
        t_start = time.perf_counter()
        results = client.search(query=query, limit=limit)
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000

        if output_format == 'json':
             output_data = {"results": results, "query_time_ms": duration_ms}
             print_output(output_data, output_format) # Single JSON line for results
        else:
            console.print(f"Query Time: {duration_ms:.2f} ms")
            if not results:
                console.print("[yellow]No results found.[/]")
                return

            table = Table(title=f"Search Results for '{query}' (Limit: {limit})", box='ROUNDED', show_header=True, header_style="bold magenta")
            table.add_column("Hash", style="dim cyan", width=18, overflow='fold')
            table.add_column("Relevance", style="white", justify="right", width=10)
            table.add_column("Size (Bytes)", style="white", justify="right", width=12)
            table.add_column("Content Type", style="yellow", overflow='fold')
            table.add_column("Filename", style="green", overflow='fold')

            for item in results:
                 table.add_row(
                     item.get('hash', 'N/A')[:18],
                     f"{item.get('similarity', 0.0):.2f}",
                     str(item.get('size', 0)),
                     item.get('content_type', '?'),
                     item.get('filename', 'N/A')
                 )
            console.print(table)

    except Exception as e:
        handle_sdk_error(e)

@cli.command()
@click.argument('file_hash', type=click.STRING)
@common_options
@click.pass_context
def zkp(ctx, file_hash, output_format):
    """Generate Zero-Knowledge Proof for a file hash."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Generating ZKP for hash '[cyan]{file_hash}[/]' from [cyan]{base_url}[/]...")
    try:
        t_start = time.perf_counter()
        result = client.get_zk_proof(file_hash)
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000
        result['query_time_ms'] = duration_ms

        print_output(result, output_format) # Use helper

    except Exception as e:
        handle_sdk_error(e)

# --- New Command for Metrics ---
@cli.command(name="get-metrics")
@common_options
@click.pass_context
def get_metrics(ctx, output_format):
    """Fetch detailed performance metrics from the node (REQUIRES backend /metrics endpoint)."""
    client: PermastoreItClient = ctx.obj['CLIENT']
    base_url = ctx.obj['BASE_URL']
    ctx.obj['OUTPUT_FORMAT'] = output_format
    console.print(f"Fetching metrics from [cyan]{base_url}[/]...")
    try:
        # Assumes a get_metrics() method exists in the SDK, calling a '/metrics' endpoint
        if not hasattr(client, 'get_metrics'):
             console.print(Panel(
                "SDK method 'get_metrics()' not found.\n"
                "This command requires a '/metrics' endpoint on the backend node and corresponding SDK support.",
                title="[bold yellow]Not Implemented[/]", border_style="yellow", expand=False
             ))
             sys.exit(1)

        t_start = time.perf_counter()
        # result = client.get_metrics() # Replace with actual call when implemented
        # Placeholder: Simulate fetching data until backend is ready
        result = {"placeholder": "Backend /metrics endpoint not implemented", "status": "not_implemented"}
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000
        result['query_time_ms'] = duration_ms

        print_output(result, output_format) # Use helper

    except Exception as e:
        handle_sdk_error(e)


if __name__ == "__main__":
    cli()
