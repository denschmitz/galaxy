from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable

from astroquery.mast import Observations

from galaxy.cache import download_file
from galaxy.config import SearchConfig


PRODUCT_TYPE_PRIORITY = {
    "SCIENCE": 0,
    "DRZ": 1,
    "DRC": 2,
    "I2D": 3,
    "CAL": 4,
}


@dataclass(slots=True)
class SearchResult:
    observations: list[dict[str, Any]]
    products: list[dict[str, Any]]


def query_archive(shape_kind: str, shape_kwargs: dict[str, Any], search: SearchConfig) -> SearchResult:
    if shape_kind == "circle":
        observations = Observations.query_region(
            f"{shape_kwargs['ra']} {shape_kwargs['dec']}",
            radius=f"{shape_kwargs['radius']} deg",
        )
    elif shape_kind == "box":
        observations = Observations.query_region(
            f"{shape_kwargs['ra']} {shape_kwargs['dec']}",
            width=f"{shape_kwargs['width']} deg",
            height=f"{shape_kwargs['height']} deg",
        )
    else:
        observations = Observations.query_criteria(s_region=shape_kwargs["coordinates"])

    obs_rows = [dict(row) for row in observations]
    obs_rows = filter_observations(obs_rows, search)

    if not obs_rows:
        return SearchResult(observations=[], products=[])

    products = Observations.get_product_list(obs_rows)
    product_rows = [dict(row) for row in products]
    product_rows = filter_products(product_rows, search)
    return SearchResult(observations=obs_rows, products=product_rows)


def filter_observations(observations: list[dict[str, Any]], search: SearchConfig) -> list[dict[str, Any]]:
    rows = observations
    if search.missions:
        rows = [row for row in rows if str(row.get("obs_collection", "")).upper() in {m.upper() for m in search.missions}]
    if search.instruments:
        rows = [row for row in rows if str(row.get("instrument_name", "")).upper() in {i.upper() for i in search.instruments}]
    return rows


def filter_products(products: list[dict[str, Any]], search: SearchConfig) -> list[dict[str, Any]]:
    rows = products
    if search.detectors:
        allowed = {item.upper() for item in search.detectors}
        rows = [row for row in rows if str(row.get("detector", "")).upper() in allowed]
    if search.filters:
        allowed = {item.upper() for item in search.filters}
        rows = [row for row in rows if str(row.get("filters", "")).upper() in allowed]
    if search.product_types:
        allowed = {item.upper() for item in search.product_types}
        rows = [row for row in rows if str(row.get("productType", "")).upper() in allowed]
    if search.observation_date_start:
        rows = [row for row in rows if str(row.get("t_min", "")) >= search.observation_date_start]
    if search.observation_date_end:
        rows = [row for row in rows if str(row.get("t_max", "")) <= search.observation_date_end]
    return rows


def rank_product(product: dict[str, Any]) -> tuple[int, int, tuple[int, ...], str]:
    product_type = str(product.get("productType", "")).upper()
    filename = str(product.get("productFilename", ""))
    fits_penalty = 0 if filename.lower().endswith((".fits", ".fits.gz")) else 1
    version_rank = _version_rank(product)
    identifier = stable_product_identifier(product)
    return (PRODUCT_TYPE_PRIORITY.get(product_type, 99), fits_penalty, version_rank, identifier)


def stable_product_identifier(product: dict[str, Any]) -> str:
    return str(
        product.get("productFilename")
        or product.get("dataURI")
        or product.get("obsID")
        or product.get("obs_id")
        or ""
    ).lower()


def _version_rank(product: dict[str, Any]) -> tuple[int, ...]:
    version_source = " ".join(
        str(product.get(field, "") or "")
        for field in ("productVersion", "productSubGroupDescription", "dataURI", "productFilename")
    )
    version_parts = [int(part) for part in re.findall(r"\d+", version_source)]
    if version_parts:
        return tuple(-part for part in version_parts)
    return (0,)


def select_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for product in products:
        key = (str(product.get("obs_id", "")), str(product.get("filters", "")))
        grouped.setdefault(key, []).append(product)
    selected: list[dict[str, Any]] = []
    for key in sorted(grouped):
        selected.append(sorted(grouped[key], key=rank_product)[0])
    return selected


def download_products(
    products: list[dict[str, Any]],
    cache_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for product in products:
        filename = str(product.get("productFilename") or product.get("dataURI", "unknown.fits")).split("/")[-1]
        url = str(product.get("dataURL") or product.get("dataURI") or "")
        destination = cache_dir / filename
        if progress:
            progress(f"Downloading {filename}")
        try:
            details = download_file(url, destination)
            manifest.append(
                {
                    "product_identifier": product.get("obs_id", filename),
                    "stable_product_identifier": stable_product_identifier(product),
                    "product_filename": product.get("productFilename"),
                    "filter": product.get("filters"),
                    "product_type": product.get("productType"),
                    "product_version": product.get("productVersion") or product.get("productSubGroupDescription"),
                    "selection_rank": [
                        rank_product(product)[0],
                        rank_product(product)[1],
                        list(rank_product(product)[2]),
                        rank_product(product)[3],
                    ],
                    "url": url,
                    "local_path": details["local_path"],
                    "file_size": details["file_size"],
                    "checksum": details["checksum"],
                    "download_timestamp": details["download_timestamp"],
                    "status": details["status"],
                }
            )
        except Exception as exc:  # pragma: no cover
            skipped.append(
                {
                    "product_identifier": product.get("obs_id", filename),
                    "stable_product_identifier": stable_product_identifier(product),
                    "url": url,
                    "reason": str(exc),
                }
            )
    return manifest, skipped
