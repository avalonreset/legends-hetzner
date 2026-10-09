# Security

Do not put API tokens, private SSH keys, private inventories, cloud-init secrets,
or unredacted command output in issues, commits, or knowledge packs.

For a suspected vulnerability, use the repository's private security advisory
reporting when available. If unavailable, open a minimal issue requesting a
private reporting channel without exploit details or sensitive data.

Use narrowly scoped Hetzner project credentials and read-only tokens for
inventory where possible. Review the selected project before any mutation.
The module's plan approval protects its own workflow; it cannot prevent an
agent or user from running other software directly.

Only the latest release receives fixes. There is no guaranteed response time.
