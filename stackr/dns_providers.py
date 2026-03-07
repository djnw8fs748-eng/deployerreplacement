"""DNS provider registry.

Maps provider names to their required environment variables and Traefik
challenge configuration. Used by the validator to check that all required
credentials are present before deploying.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DnsProvider:
    """Metadata for a supported ACME DNS challenge provider."""

    name: str
    # Environment variables that must be present for this provider
    required_env: list[str] = field(default_factory=list)
    # The Traefik dnschallenge.provider value (usually same as name)
    traefik_provider: str = ""
    # Human-readable display name
    display_name: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "traefik_provider", self.traefik_provider or self.name)
        object.__setattr__(self, "display_name", self.display_name or self.name.title())


# Registry of all supported DNS providers
DNS_PROVIDERS: dict[str, DnsProvider] = {
    "cloudflare": DnsProvider(
        name="cloudflare",
        display_name="Cloudflare",
        required_env=["CF_DNS_API_TOKEN"],
        traefik_provider="cloudflare",
    ),
    "route53": DnsProvider(
        name="route53",
        display_name="AWS Route 53",
        required_env=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"],
        traefik_provider="route53",
    ),
    "porkbun": DnsProvider(
        name="porkbun",
        display_name="Porkbun",
        required_env=["PORKBUN_API_KEY", "PORKBUN_SECRET_API_KEY"],
        traefik_provider="porkbun",
    ),
    "namecheap": DnsProvider(
        name="namecheap",
        display_name="Namecheap",
        required_env=["NAMECHEAP_API_USER", "NAMECHEAP_API_KEY"],
        traefik_provider="namecheap",
    ),
    "digitalocean": DnsProvider(
        name="digitalocean",
        display_name="DigitalOcean",
        required_env=["DO_AUTH_TOKEN"],
        traefik_provider="digitalocean",
    ),
    "duckdns": DnsProvider(
        name="duckdns",
        display_name="DuckDNS",
        required_env=["DUCKDNS_TOKEN"],
        traefik_provider="duckdns",
    ),
    "godaddy": DnsProvider(
        name="godaddy",
        display_name="GoDaddy",
        required_env=["GODADDY_API_KEY", "GODADDY_API_SECRET"],
        traefik_provider="godaddy",
    ),
    "desec": DnsProvider(
        name="desec",
        display_name="deSEC",
        required_env=["DESEC_TOKEN"],
        traefik_provider="desec",
    ),
    "hetzner": DnsProvider(
        name="hetzner",
        display_name="Hetzner DNS",
        required_env=["HETZNER_API_KEY"],
        traefik_provider="hetzner",
    ),
    "ovh": DnsProvider(
        name="ovh",
        display_name="OVH",
        required_env=[
            "OVH_ENDPOINT",
            "OVH_APPLICATION_KEY",
            "OVH_APPLICATION_SECRET",
            "OVH_CONSUMER_KEY",
        ],
        traefik_provider="ovh",
    ),
}


def get_provider(name: str) -> DnsProvider | None:
    """Return the DnsProvider for *name*, or None if not registered."""
    return DNS_PROVIDERS.get(name)


def list_providers() -> list[str]:
    """Return sorted list of supported provider names."""
    return sorted(DNS_PROVIDERS)


def required_env_vars(name: str) -> list[str]:
    """Return the required env vars for *name*, or empty list if unknown."""
    provider = get_provider(name)
    return provider.required_env if provider else []
