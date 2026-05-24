#!/bin/bash
# Keeps your DuckDNS record pointed at the current EC2 public IP.
# Run via cron every 5 minutes:
#   */5 * * * * /home/ubuntu/lotto/deploy/duckdns-renew.sh >> /var/log/duckdns.log 2>&1

DOMAIN="YOUR_DOMAIN"          # just the subdomain part, e.g. md-lotto
TOKEN="YOUR_DUCKDNS_TOKEN"    # from duckdns.org/account

curl -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" -o /tmp/duckdns.txt
echo " [$(date -u '+%Y-%m-%d %H:%M UTC')]"
