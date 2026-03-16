from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable

from astroquery.mast import Observations

from galaxy.cache import sha256_file
from galaxy.config import SearchConfig


PRODUCT_TYPE_PRIORITY = {
    "SCIENCE": 0,
    "DRZ": 1,
    "DRC": 2,
    "I2D": 3,
    "CAL": 4,
}
PRODUCT_LIST_BATCH_SIZE = 64


@dataclass(slots=True)
class SearchResult:
    observations: list[dict[str, Any]]
    products: list[dict[str, Any]]


def query_archive(
    shape_kind: str,
    shape_kwargs: dict[str, Any],
    search: SearchConfig,
    progress: Callable[[str], None] | None = None,
) -> SearchResult:
    if progress:
        progress(f"Submitting MAST observation query for {shape_kind} region")

    observations = Observations.query_region(
        f"{shape_kwargs['ra']} {shape_kwargs['dec']}",
        radius=f"{shape_kwargs['radius']} deg",
    )

    obs_rows = [dict(row) for row in observations]
    if progress:
        progress(f"MAST returned {len(obs_rows)} raw observations")
    obs_rows = filter_observations(obs_rows, search)
    if progress:
        progress(f"{len(obs_rows)} observations remain after mission/instrument filtering")

    if not obs_rows:
        return SearchResult(observations=[], products=[])

    observation_ids = list(
        dict.fromkeys(
            str(row.get("obsid") or "") for row in obs_rows if row.get("obsid") not in (None, "")
        )
    )
    if progress:
        progress(f"Fetching product lists for {len(observation_ids)} observations in batches of {PRODUCT_LIST_BATCH_SIZE}")

    product_rows: list[dict[str, Any]] = []
    batches = _batched(observation_ids, PRODUCT_LIST_BATCH_SIZE)
    for index, batch in enumerate(batches, start=1):
        if progress:
            progress(f"Fetching product batch {index}/{len(batches)} ({len(batch)} observations)")
        products = Observations.get_product_list(batch)
        product_rows.extend(dict(row) for row in products)

    if progress:
        progress(f"Retrieved {len(product_rows)} raw products before filtering")
    product_rows = filter_products(product_rows, search)
    if progress:
        progress(f"{len(product_rows)} products remain after detector/filter/type/date filtering")
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
        uri = str(product.get("dataURI") or "")
        destination = cache_dir / filename
        if progress:
            progress(f"Downloading {filename}")
        try:
            rank = rank_product(product)
            status, msg, url = Observations.download_file(uri, local_path=destination, cache=True, verbose=False)
            if status == "ERROR":
                raise RuntimeError(msg or "MAST download failed")
            manifest.append(
                {
                    "product_identifier": product.get("obs_id", filename),
                    "stable_product_identifier": stable_product_identifier(product),
                    "product_filename": product.get("productFilename"),
                    "filter": product.get("filters"),
                    "product_type": product.get("productType"),
                    "product_version": product.get("productVersion") or product.get("productSubGroupDescription"),
                    "selection_rank": [rank[0], rank[1], list(rank[2]), rank[3]],
                    "url": url,
                    "local_path": str(destination),
                    "file_size": destination.stat().st_size,
                    "checksum": sha256_file(destination),
                    "download_timestamp": None,
                    "status": status.lower(),
                }
            )
        except Exception as exc:  # pragma: no cover
            skipped.append(
                {
                    "product_identifier": product.get("obs_id", filename),
                    "stable_product_identifier": stable_product_identifier(product),
                    "url": uri,
                    "reason": str(exc),
                }
            )
            if progress:
                progress(f"Download failed for {filename}: {exc}")
    return manifest, skipped


def _batched(items: list[str], batch_size: int) -> list[list[str]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]
