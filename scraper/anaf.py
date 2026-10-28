"""Company identity lookup — ANAF (demoanaf.ro) + CUIScan + CUIFirma.

Mirrors the JS template's ``scraper/anaf.js`` exactly:

    company lookup:  1 try demoanaf.ro  -> 1 try cuiscan.ro  -> (caller's cache)
    brand search:    1 try demoanaf.ro  -> 1 try cuifirma.ro

No retries here on purpose (each source gets exactly one attempt before the
cascade moves on) — this module bypasses ``scraper.fetch``'s retry/backoff
wrapper deliberately, unlike the rest of the codebase.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .config import USER_AGENT

log = logging.getLogger("scraper.anaf")

ANAF_API_URL = "https://demoanaf.ro/api/company/"
ANAF_SEARCH_URL = "https://demoanaf.ro/api/search"
CUISCAN_API_URL = "https://cuiscan.ro/api.php"
CUIFIRMA_SEARCH_URL = "https://cuifirma.ro/api/search"
TIMEOUT_SEC = 10.0


def _map_cuiscan_to_anaf_format(data: dict) -> dict:
    """Reshape a CUIScan company record into the ANAF response shape."""
    tva_periods = [
        {
            "start": p.get("dataStart"),
            "end": p.get("dataEnd") or None,
            "yearStart": "",
            "message": p.get("mesaj") or "",
        }
        for p in (data.get("perioadeTVA") or [])
    ]
    hq = data.get("adresaSediu")
    headquarters_address = (
        {
            "street": hq.get("strada", ""),
            "number": hq.get("numar", ""),
            "locality": hq.get("localitate", ""),
            "county": hq.get("judet", ""),
            "country": "",
            "postalCode": hq.get("codPostal", ""),
        }
        if hq
        else {"street": "", "number": "", "locality": "", "county": "", "country": "", "postalCode": ""}
    )
    administrators = [
        {"name": a.get("nume") or a.get("name") or "", "role": a.get("rol") or a.get("role") or "administrator"}
        for a in (data.get("administratori") or [])
    ]

    return {
        "cui": data.get("cui"),
        "name": data.get("denumire"),
        "address": data.get("adresa"),
        "registrationNumber": data.get("nrRegCom"),
        "phone": data.get("telefon") or "",
        "fax": data.get("fax") or "",
        "postalCode": data.get("codPostal"),
        "caenCode": data.get("codCaen"),
        "iban": data.get("iban") or "",
        "registrationState": data.get("stareInregistrare"),
        "registrationDate": data.get("dataInregistrare"),
        "fiscalAuthority": data.get("organFiscal"),
        "ownershipForm": data.get("formaProprietate"),
        "organizationForm": data.get("formaOrganizare"),
        "legalForm": data.get("formaJuridica"),
        "vatRegistered": data.get("platitorTVA"),
        "vatPeriods": tva_periods,
        "cashBasisVat": data.get("tvaIncasare") or False,
        "cashBasisVatStart": data.get("dataInceputTvaInc") or None,
        "cashBasisVatEnd": data.get("dataSfarsitTvaInc") or None,
        "inactive": not data.get("activ"),
        "inactiveSince": data.get("dataInactivare") or None,
        "reactivatedSince": data.get("dataReactivare") or None,
        "splitVat": data.get("splitTVA") or False,
        "eFacturaRegistered": data.get("eFactura") or False,
        "headquartersAddress": headquarters_address,
        "fiscalAddress": {"street": "", "number": "", "locality": "", "county": "", "country": "", "postalCode": ""},
        "administrators": administrators,
        "authorizedCaenCodes": data.get("caenAutorizate") or [],
        "onrcStatus": 0,
        "onrcStatusLabel": "Funcțiune" if data.get("activ") else "Inactiv",
    }


def _headers() -> dict:
    return {"User-Agent": USER_AGENT}


def _fetch_from_cuiscan(cif: str | int) -> dict:
    res = requests.get(
        CUISCAN_API_URL, params={"action": "company", "cui": cif}, headers=_headers(), timeout=TIMEOUT_SEC
    )
    if not res.ok:
        raise RuntimeError(f"CUIScan API error: {res.status_code}")
    data = res.json()
    if not data or not data.get("denumire"):
        raise RuntimeError("CUIScan returned no data")
    return _map_cuiscan_to_anaf_format(data)


def _fetch_from_anaf(cif: str | int) -> dict | None:
    res = requests.get(f"{ANAF_API_URL}{cif}", headers=_headers(), timeout=TIMEOUT_SEC)
    if not res.ok:
        raise RuntimeError(f"ANAF API error: {res.status_code}")
    data = res.json()
    if data.get("success") is False:
        raise RuntimeError((data.get("error") or {}).get("message") or "ANAF returned error")
    return data.get("data")


def _search_from_anaf(brand_name: str) -> list[dict]:
    res = requests.get(ANAF_SEARCH_URL, params={"q": brand_name}, headers=_headers(), timeout=TIMEOUT_SEC)
    if not res.ok:
        raise RuntimeError(f"ANAF search error: {res.status_code}")
    return res.json().get("data") or []


def _search_from_cuifirma(brand_name: str) -> list[dict]:
    res = requests.get(CUIFIRMA_SEARCH_URL, params={"q": brand_name}, headers=_headers(), timeout=TIMEOUT_SEC)
    if not res.ok:
        raise RuntimeError(f"CUIFirma search error: {res.status_code}")
    results = res.json().get("results") or []
    return [
        {
            "cui": str(r.get("cui")),
            "name": r.get("name"),
            "statusLabel": "Funcțiune" if r.get("is_active") else (r.get("status_label") or "Inactiv"),
        }
        for r in results
    ]


def get_company_from_anaf(cif: str | int) -> dict | None:
    """Company by CIF — ANAF (demoanaf.ro) first, CUIScan fallback."""
    try:
        log.info("fetching company data for CIF %s (demoanaf.ro)...", cif)
        return _fetch_from_anaf(cif)
    except Exception as exc:  # noqa: BLE001 - any failure falls through to the next source
        log.info("demoANAF failed (%s) — trying cuiscan.ro...", exc)
        return _fetch_from_cuiscan(cif)


def get_company_from_anaf_with_fallback(cif: str | int, cached_data: Any = None) -> Any:
    """Same as :func:`get_company_from_anaf`, plus a last-resort cache fallback."""
    try:
        return get_company_from_anaf(cif)
    except Exception as exc:  # noqa: BLE001 - both live sources failed
        log.warning("all company data sources unavailable: %s", exc)
        if cached_data is not None:
            log.info("using cached company data as fallback")
            return cached_data
        raise


def search_company(brand_name: str) -> list[dict]:
    """Search companies by brand — ANAF (demoanaf.ro) first, CUIFirma fallback."""
    try:
        return _search_from_anaf(brand_name)
    except Exception as exc:  # noqa: BLE001
        log.info("demoANAF search failed (%s) — trying cuifirma.ro...", exc)
        return _search_from_cuifirma(brand_name)
