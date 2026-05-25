"""Feeder lookup by geocoded address components.

Two steps:
1. resolve_adm2_pcode  — maps a human LGA name to its adm2_pcode by
   fuzzy-matching against the lgas table.
2. match_feeders       — calls the match_feeders_for_address Postgres
   function (see sql/match_feeders.sql) via Supabase RPC.
"""
from core import get_supabase_client


def _resolve_client(client):
    return client if client is not None else get_supabase_client()


def resolve_adm2_pcode(lga_name: str, client=None) -> str | None:
    if not lga_name:
        return None
    response = (
        _resolve_client(client)
        .table("lgas")
        .select("adm2_pcode")
        .ilike("adm2_name", f"%{lga_name}%")
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0]["adm2_pcode"] if rows else None


def match_feeders(address, route, neighborhood, sublocality, adm2_pcode, client=None):
    response = (
        _resolve_client(client)
        .rpc(
            "match_feeders_for_address",
            {
                "p_address": address,
                "p_route": route,
                "p_neighborhood": neighborhood,
                "p_sublocality": sublocality,
                "p_adm2_pcode": adm2_pcode,
            },
        )
        .execute()
    )
    return response.data or []
