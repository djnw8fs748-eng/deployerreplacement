"""Tests for DNS provider registry."""

from __future__ import annotations

from stackr.dns_providers import (
    DNS_PROVIDERS,
    DnsProvider,
    get_provider,
    list_providers,
    required_env_vars,
)


def test_all_known_providers_registered():
    expected = {
        "cloudflare", "route53", "porkbun", "namecheap",
        "digitalocean", "duckdns", "godaddy", "desec", "hetzner", "ovh",
    }
    assert expected.issubset(set(DNS_PROVIDERS))


def test_get_provider_returns_dataclass():
    p = get_provider("cloudflare")
    assert isinstance(p, DnsProvider)
    assert p.name == "cloudflare"
    assert p.display_name == "Cloudflare"


def test_get_provider_unknown_returns_none():
    assert get_provider("unknownprovider") is None


def test_cloudflare_required_env():
    assert required_env_vars("cloudflare") == ["CF_DNS_API_TOKEN"]


def test_route53_required_env():
    vars_ = required_env_vars("route53")
    assert "AWS_ACCESS_KEY_ID" in vars_
    assert "AWS_SECRET_ACCESS_KEY" in vars_
    assert "AWS_REGION" in vars_


def test_porkbun_required_env():
    vars_ = required_env_vars("porkbun")
    assert "PORKBUN_API_KEY" in vars_
    assert "PORKBUN_SECRET_API_KEY" in vars_


def test_namecheap_required_env():
    vars_ = required_env_vars("namecheap")
    assert "NAMECHEAP_API_USER" in vars_
    assert "NAMECHEAP_API_KEY" in vars_


def test_digitalocean_required_env():
    assert required_env_vars("digitalocean") == ["DO_AUTH_TOKEN"]


def test_duckdns_required_env():
    assert required_env_vars("duckdns") == ["DUCKDNS_TOKEN"]


def test_godaddy_required_env():
    vars_ = required_env_vars("godaddy")
    assert "GODADDY_API_KEY" in vars_
    assert "GODADDY_API_SECRET" in vars_


def test_unknown_provider_returns_empty_env():
    assert required_env_vars("nonexistent") == []


def test_list_providers_sorted():
    providers = list_providers()
    assert providers == sorted(providers)
    assert "cloudflare" in providers
    assert "route53" in providers


def test_traefik_provider_defaults_to_name():
    p = get_provider("cloudflare")
    assert p is not None
    assert p.traefik_provider == "cloudflare"


def test_all_providers_have_required_env():
    """Every registered provider must declare at least one required env var."""
    for name, provider in DNS_PROVIDERS.items():
        assert provider.required_env, f"Provider '{name}' has no required_env"


def test_all_providers_have_display_name():
    for name, provider in DNS_PROVIDERS.items():
        assert provider.display_name, f"Provider '{name}' has no display_name"
