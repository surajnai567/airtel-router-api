"""
CLI entry point for Nokia GPON Router API.

Usage:
    python -m cli.main list              List all connected devices
    python -m cli.main blocked           List all blocked devices
    python -m cli.main block <MAC>       Block a device by MAC address
    python -m cli.main unblock <MAC>     Unblock a device by MAC address
"""
import argparse
import sys
import os

from dotenv import load_dotenv

load_dotenv()

from core import RouterAPI


def create_router():
    """Create a RouterAPI instance from environment variables."""
    return RouterAPI(
        ip_address=os.getenv("ROUTER_IP", "192.168.1.1"),
        username=os.getenv("ROUTER_USERNAME", "admin"),
        password=os.getenv("ROUTER_PASSWORD", "admin"),
    )


def cmd_list(router):
    """List all connected/known devices."""
    devices = router.list_devices()
    if devices:
        print(f"\n{'Hostname':<30} {'IP':<16} {'MAC':<20} {'Active':<8} {'Interface'}")
        print("-" * 100)
        for d in devices:
            status = "Yes" if d["active"] else "No"
            print(f"{d['hostname']:<30} {d['ip']:<16} {d['mac']:<20} {status:<8} {d['interface']}")
    else:
        print("No devices found.")


def cmd_blocked(router):
    """List all blocked devices."""
    blocked = router.list_blocked_devices()
    if blocked:
        print(f"\n{'MAC':<20} {'Policy Name':<30} {'Enabled':<10} {'Schedule'}")
        print("-" * 80)
        for b in blocked:
            print(
                f"{b['mac']:<20} {b['policy_name']:<30} "
                f"{str(b['policy_enabled']):<10} {b['start_time']}-{b['end_time']}"
            )
    else:
        print("\nNo blocked devices.")


def cmd_block(router, mac, policy_name=None):
    """Block a device by MAC address."""
    success = router.block_device(mac, policy_name)
    if success:
        print(f"Successfully blocked {mac}.")
    else:
        print(f"Failed to block {mac}.")


def cmd_unblock(router, mac):
    """Unblock a device by MAC address."""
    success = router.unblock_device(mac)
    if success:
        print(f"Successfully unblocked {mac}.")
    else:
        print(f"Failed to unblock {mac}.")


def main():
    parser = argparse.ArgumentParser(
        description="Nokia GPON Router API — CLI Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m cli.main list\n"
            "  python -m cli.main blocked\n"
            "  python -m cli.main block AA:BB:CC:DD:EE:FF\n"
            '  python -m cli.main block AA:BB:CC:DD:EE:FF --name "My Policy"\n'
            "  python -m cli.main unblock AA:BB:CC:DD:EE:FF\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    subparsers.add_parser("list", help="List all connected devices")

    # blocked
    subparsers.add_parser("blocked", help="List all blocked devices")

    # block
    block_parser = subparsers.add_parser("block", help="Block a device by MAC address")
    block_parser.add_argument("mac", help="MAC address to block (e.g., AA:BB:CC:DD:EE:FF)")
    block_parser.add_argument("--name", dest="policy_name", help="Custom policy name")

    # unblock
    unblock_parser = subparsers.add_parser("unblock", help="Unblock a device by MAC address")
    unblock_parser.add_argument("mac", help="MAC address to unblock (e.g., AA:BB:CC:DD:EE:FF)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    router = create_router()

    if not router.login():
        print("Login failed!", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "list":
            cmd_list(router)
        elif args.command == "blocked":
            cmd_blocked(router)
        elif args.command == "block":
            cmd_block(router, args.mac, args.policy_name)
        elif args.command == "unblock":
            cmd_unblock(router, args.mac)
    finally:
        router.logout()


if __name__ == "__main__":
    main()
