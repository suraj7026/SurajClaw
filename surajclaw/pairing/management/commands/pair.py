"""``python manage.py pair`` -- approve / deny / list pairing codes.

Subcommands:

    pair list            -- show pending pairing codes
    pair approve <CODE>  -- approve a code (creates an ApprovedSender)
    pair deny <CODE>     -- deny a code
    pair senders         -- list active approved senders
    pair revoke <ch> <id> -- revoke a sender's access
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Manage device pairing codes and the approved-sender allowlist."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("list", help="Show pending pairing codes.")
        sub.add_parser("senders", help="List active approved senders.")

        ap = sub.add_parser("approve", help="Approve a pending pairing code.")
        ap.add_argument("code")
        ap.add_argument("--label", default="", help="Optional nickname for this sender.")

        dn = sub.add_parser("deny", help="Deny a pending pairing code.")
        dn.add_argument("code")

        rv = sub.add_parser("revoke", help="Revoke an approved sender.")
        rv.add_argument("channel")
        rv.add_argument("sender_id")
        rv.add_argument("--reason", default="")

    def handle(self, *args, **opts):
        from pairing import services

        action = opts["action"]

        if action == "list":
            rows = services.list_pending()
            if not rows:
                self.stdout.write("no pending codes")
                return
            self.stdout.write(
                "{:<10} {:<10} {:<24} {:<10} {}".format(
                    "code", "channel", "sender_id", "expires", "display_name"
                )
            )
            for pc in rows:
                self.stdout.write(
                    "{:<10} {:<10} {:<24} {:<10} {}".format(
                        pc.code,
                        pc.channel,
                        pc.sender_id[:24],
                        pc.expires_at.strftime("%H:%M:%S"),
                        pc.display_name,
                    )
                )
            return

        if action == "senders":
            rows = services.list_approved()
            if not rows:
                self.stdout.write("no approved senders")
                return
            self.stdout.write("{:<10} {:<32} {}".format("channel", "sender_id", "label"))
            for s in rows:
                self.stdout.write(
                    "{:<10} {:<32} {}".format(s.channel, s.sender_id[:32], s.label)
                )
            return

        if action == "approve":
            try:
                sender, _ = services.approve_code(opts["code"], label=opts["label"])
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write(
                self.style.SUCCESS(
                    f"approved {sender.channel}:{sender.sender_id}"
                    + (f" ({sender.label})" if sender.label else "")
                )
            )
            return

        if action == "deny":
            try:
                pc = services.deny_code(opts["code"])
            except Exception as exc:
                raise CommandError(str(exc))
            self.stdout.write(f"denied {pc.code} ({pc.channel}:{pc.sender_id})")
            return

        if action == "revoke":
            sender = services.revoke_sender(
                opts["channel"], opts["sender_id"], reason=opts["reason"]
            )
            if sender is None:
                raise CommandError("no matching active sender")
            self.stdout.write(self.style.SUCCESS(f"revoked {sender.channel}:{sender.sender_id}"))
            return
