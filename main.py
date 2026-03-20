# main.py
import os
import click

from src.identifier.url_parser import parse_phishtank_csv, save_cid_list
from src.identifier.dnslink_resolver import dnslink_query
from src.collector.node_tracker import track_cids
from src.collector.local_collector import collect_ipfs_repo
from src.analyzer.reassembler import reassemble_chunks
from src.analyzer.ip_mapper import create_map
from src.analyzer.credential_extractor import summarize_credentials, clone_credentials
from src.preventer.prevention_manager import stop_ipfs_daemon, generate_block_request_list
from src.reporter.html_reporter import generate_report


def get_output_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(d, exist_ok=True)
    return d


@click.group()
def cli():
    """IPFS-Forensics-System

    Based on IF-DSS framework (Son et al., DFRWS 2023)
    """
    pass


# ===== Stage 1: Identification =====

@cli.command()
@click.argument('csv_path')
@click.option('-o', '--output', default=get_output_dir)
def identify(csv_path, output):
    """Extract CIDs from PhishTank CSV"""
    results = parse_phishtank_csv(csv_path)
    cid_file = save_cid_list(results, output)
    click.echo(f"Found {len(results)} IPFS URLs -> {cid_file}")


@cli.command()
@click.argument('url_file')
@click.option('-o', '--output', default=get_output_dir)
def dnslink(url_file, output):
    """Query DNSLink records for URLs"""
    result = dnslink_query(url_file, output)
    click.echo(f"Found {len(result)} DNSLink records")


# ===== Stage 2: Collection =====

@cli.command()
@click.argument('cid_file')
@click.option('--ipfs', default='ipfs', help='Path to ipfs binary')
@click.option('-o', '--output', default=get_output_dir)
def collect(cid_file, ipfs, output):
    """Track CID providers and collect IPs"""
    yn = input("Is your IPFS daemon running? (y/n): ")
    if yn.lower() != 'y':
        click.echo("Please start IPFS daemon first")
        return
    result = track_cids(cid_file, ipfs, output)
    s = result["stats"]
    click.echo(f"Tracked {s['total']} CIDs: {s['found']} found, {s['not_found']} not found")


@cli.command()
@click.argument('repo_path')
@click.option('-o', '--output', default=get_output_dir)
def collect_local(repo_path, output):
    """Collect local IPFS repository artifacts"""
    evidence = collect_ipfs_repo(repo_path, output)
    click.echo(f"PeerID: {evidence.get('peer_id', 'N/A')}")
    click.echo(f"Blocks: {evidence.get('blocks_count', 0)}")


# ===== Stage 3: Analysis =====

@cli.command()
@click.argument('blocks_dir')
@click.option('-o', '--output', default=get_output_dir)
def reassemble(blocks_dir, output):
    """Reassemble IPFS blocks with fault tolerance"""
    stats = reassemble_chunks(blocks_dir, output)
    click.echo(f"Trees: {stats.trees}, Lists: {stats.lists}, Blobs: {stats.blobs}")
    click.echo(f"Missing: {stats.missing_blocks}, Errors: {len(stats.errors)}")


@cli.command()
@click.argument('track_json')
@click.option('-o', '--output', default=get_output_dir)
def mapips(track_json, output):
    """Generate IP geolocation map"""
    create_map(track_json, output)


@cli.command()
@click.argument('repo_path')
def credentials(repo_path):
    """Extract credentials from IPFS repo"""
    summary = summarize_credentials(repo_path)
    click.echo(f"PeerID: {summary['peer_id']}")
    click.echo(f"Has PrivKey: {summary['has_private_key']}")
    click.echo(f"Has SwarmKey: {summary['has_swarm_key']}")
    click.echo(f"API: {summary['api_address']}")


# ===== Stage 4: Prevention =====

@cli.command()
@click.option('-o', '--output', default=get_output_dir)
def prevent(output):
    """Generate block request list and optionally stop daemon"""
    track_path = os.path.join(output, "track.json")
    generate_block_request_list(track_path, output)

    yn = input("Stop local IPFS daemon? (y/n): ")
    if yn.lower() == 'y':
        result = stop_ipfs_daemon()
        click.echo(f"Daemon stop: {result['status']}")


# ===== Stage 5: Report =====

@cli.command()
@click.option('--name', required=True, help='Case name')
@click.option('-o', '--output', default=get_output_dir)
def report(name, output):
    """Generate HTML forensic report"""
    import json

    track_path = os.path.join(output, "track.json")
    reassembly_path = os.path.join(output, "reassemble", "reassembly_report.json")

    track_results = {}
    if os.path.exists(track_path):
        track_results = json.load(open(track_path))

    reassembly_stats = None
    if os.path.exists(reassembly_path):
        reassembly_stats = json.load(open(reassembly_path))

    path = generate_report(
        case_name=name,
        output_dir=output,
        id_stats={"total": 0, "cids_found": len(track_results)},
        track_stats={
            "total": len(track_results),
            "found": sum(1 for v in track_results.values() if v.get("IP")),
            "not_found": sum(1 for v in track_results.values() if not v.get("IP"))
        },
        track_results=track_results,
        reassembly_stats=reassembly_stats,
    )
    click.echo(f"Report: {path}")


if __name__ == '__main__':
    cli()