"""Logging filters for production logging configuration."""
import logging


class SkipDisallowedHost(logging.Filter):
    """Drop DisallowedHost records so internet scanners don't trigger alerts.

    Requests to hostnames outside ALLOWED_HOSTS (notably the mail/webmail
    subdomains, which resolve to the same vhost) are routine background noise
    from crawlers and port scanners. They are still written to the rotating
    log file by the 'file' handler; this filter is attached only to the
    'mail_admins' handler so a scan cannot flood the admin mailbox.
    """

    def filter(self, record):
        if record.name.startswith("django.security.DisallowedHost"):
            return False
        msg = record.getMessage() if record.args else record.msg
        return not (isinstance(msg, str) and msg.startswith("Invalid HTTP_HOST header"))
