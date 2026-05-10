from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
from typing import Any, Callable

from astroquery.mast import Observations

from galaxy.cache import sha256_file
from galaxy.config import SearchConfig
from galaxy.logging_utils import emit_log
from galaxy.selection import CandidateManifest, CandidateRecord, SelectionInputs


PRODUCT_TYPE_PRIORITY = {
    "SCIENCE": 0,
    "DRZ": 1,
    "DRC": 2,
    "I2D": 3,
    "CAL": 4,
}
PRODUCT_LIST_BATCH_SIZE = 64
NON_DISPLAY_FILTERS = {"BLANK", "DETECTION", "MIRVIS"}
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchResult:
    observations: list[dict[str, Any]]
    candidates: list[CandidateRecord]


def query_archive(
    shape_kind: str,
    shape_kwargs: dict[str, Any],
    search: SearchConfig,
    progress: Callable[[str], None] | None = None,
) -> SearchResult:
    observations, products = _query_archive_rows(shape_kind, shape_kwargs, search, progress=progress)
    return SearchResult(observations=observations, candidates=build_candidates(products))


def discover_candidates(
    shape_kind: str,
    shape_kwargs: dict[str, Any],
    search: SearchConfig,
    progress: Callable[[str], None] | None = None,
) -> list[CandidateRecord]:
    _, products = _query_archive_rows(shape_kind, shape_kwargs, search, progress=progress)
    return build_candidates(products)


def build_candidate_manifest(
    candidates: list[CandidateRecord],
    search: SearchConfig,
    config_path: str | None = None,
    selection_inputs: SelectionInputs | None = None,
) -> CandidateManifest:
    inputs = selection_inputs or SelectionInputs()
    updated = apply_selection_policy(candidates, search, inputs)
    return CandidateManifest(
        generated_at=_utc_now(),
        config_path=config_path,
        selection_policy=inputs.strategy or search.observation_selection,
        max_observations_per_filter=inputs.max_per_filter or search.max_observations_per_filter,
        selection_inputs=inputs,
        candidates=updated,
    )


def filter_observations(observations: list[dict[str, Any]], search: SearchConfig) -> list[dict[str, Any]]:
    rows = observations
    if search.missions:
        allowed = {m.upper() for m in search.missions}
        rows = [row for row in rows if str(row.get("obs_collection", "")).upper() in allowed]
    if search.instruments:
        allowed = {i.upper() for i in search.instruments}
        rows = [row for row in rows if str(row.get("instrument_name", "")).upper() in allowed]
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
        rows = [row for row in rows if str(row.get("_obs_t_min", row.get("t_min", ""))) >= search.observation_date_start]
    if search.observation_date_end:
        rows = [row for row in rows if str(row.get("_obs_t_max", row.get("t_max", ""))) <= search.observation_date_end]
    return [row for row in rows if _is_usable_display_product(row)]


def build_candidates(products: list[dict[str, Any]]) -> list[CandidateRecord]:
    candidates: list[CandidateRecord] = []
    for product in products:
        rank = rank_product(product)
        candidates.append(
            CandidateRecord(
                candidate_id=_candidate_id(product),
                obsid=_text_or_none(product.get("obsid")),
                obs_id=_text_or_none(product.get("obs_id") or product.get("obsID")),
                product_filename=_text_or_none(product.get("productFilename")),
                data_uri=_text_or_none(product.get("dataURI")),
                mission=_text_or_none(product.get("_obs_collection") or product.get("obs_collection")),
                instrument=_text_or_none(product.get("_obs_instrument") or product.get("instrument_name")),
                detector=_text_or_none(product.get("detector")),
                filter_name=_text_or_none(product.get("filters") or product.get("filter")),
                product_type=_text_or_none(product.get("productType")),
                product_version=_text_or_none(product.get("productVersion") or product.get("productSubGroupDescription")),
                observation_date_start=_text_or_none(product.get("_obs_t_min") or product.get("t_min")),
                observation_date_end=_text_or_none(product.get("_obs_t_max") or product.get("t_max")),
                exposure_time=_float_or_none(product.get("_obs_exptime") or product.get("exptime") or product.get("exposure_time")),
                file_size=_int_or_none(product.get("size") or product.get("productSize") or product.get("dataSize")),
                proposal_id=_text_or_none(product.get("proposal_id") or product.get("proposal_pi")),
                proposal_title=_text_or_none(product.get("proposal_title") or product.get("obs_title")),
                target_name=_text_or_none(product.get("target_name")),
                selection_rank=[rank[0], rank[1], list(rank[2]), rank[3]],
                extra_metadata={
                    "archive_ids": {
                        "obsid": product.get("obsid"),
                        "obs_id": product.get("obs_id") or product.get("obsID"),
                    },
                    "raw_product": dict(product),
                },
            )
        )
    return sorted(candidates, key=_candidate_sort_key)


def select_products(products: list[dict[str, Any]], search: SearchConfig | None = None) -> list[dict[str, Any]]:
    effective_search = search or SearchConfig()
    selected_candidates = [candidate for candidate in apply_selection_policy(build_candidates(products), effective_search) if candidate.selected]
    return [dict(candidate.extra_metadata.get("raw_product", {})) for candidate in selected_candidates]


def apply_selection_policy(
    candidates: list[CandidateRecord],
    search: SearchConfig,
    selection_inputs: SelectionInputs | None = None,
) -> list[CandidateRecord]:
    inputs = selection_inputs or SelectionInputs()
    updated = [_copy_candidate(candidate) for candidate in candidates]
    strategy = inputs.strategy or search.observation_selection
    max_per_filter = inputs.max_per_filter or search.max_observations_per_filter

    for candidate in updated:
        candidate.auto_selected = False
        candidate.auto_selection_reason = "dropped:not_auto_selected"
        candidate.selected = False
        candidate.selected_reason = "dropped:not_selected"

    best_per_observation = _best_candidates_per_observation_filter(updated)
    best_ids = {candidate.candidate_id for candidate in best_per_observation}
    for candidate in updated:
        if candidate.candidate_id not in best_ids:
            candidate.auto_selection_reason = "dropped:lower_ranked_product_in_observation_filter"

    auto_selected = _auto_select_candidates(best_per_observation, strategy, max_per_filter)
    auto_ids = {candidate.candidate_id for candidate in auto_selected}
    auto_reasons = {candidate.candidate_id: candidate.auto_selection_reason for candidate in auto_selected}

    for candidate in updated:
        if candidate.candidate_id in auto_ids:
            candidate.auto_selected = True
            candidate.auto_selection_reason = auto_reasons[candidate.candidate_id]
        elif candidate.candidate_id in best_ids and candidate.auto_selection_reason == "dropped:not_auto_selected":
            candidate.auto_selection_reason = _dropped_reason_for_strategy(strategy)

    narrowed = sorted(
        [candidate for candidate in updated if candidate.auto_selected and _matches_narrowing_filters(candidate, inputs)],
        key=lambda item: _selected_priority_key(item, strategy),
    )
    if inputs.max_total is not None:
        narrowed = narrowed[: inputs.max_total]
    narrowed_ids = {candidate.candidate_id for candidate in narrowed}

    for candidate in updated:
        if candidate.candidate_id in narrowed_ids:
            candidate.selected = True
            candidate.selected_reason = candidate.auto_selection_reason
        elif candidate.auto_selected and not _matches_narrowing_filters(candidate, inputs):
            candidate.selected_reason = "dropped:cli_filter"
        elif candidate.auto_selected and inputs.max_total is not None:
            candidate.selected_reason = "dropped:max_total"
        else:
            candidate.selected_reason = candidate.auto_selection_reason

    for candidate in updated:
        if candidate.user_selected is True:
            candidate.selected = True
            candidate.selected_reason = "selected:user_manifest"
        elif candidate.user_selected is False:
            candidate.selected = False
            candidate.selected_reason = "dropped:user_manifest"

    for candidate in updated:
        if _matches_explicit_include(candidate, inputs):
            candidate.selected = True
            candidate.selected_reason = "selected:explicit_include"

    for candidate in updated:
        if _matches_explicit_exclude(candidate, inputs):
            candidate.selected = False
            candidate.selected_reason = "dropped:explicit_exclude"

    return sorted(updated, key=_candidate_sort_key)


def download_selected(
    candidates: list[CandidateRecord],
    cache_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    selected_candidates = [item for item in candidates if item.selected]
    emit_log(logger, logging.INFO, f"Download queue contains {len(selected_candidates)} selected products", progress)
    for candidate in selected_candidates:
        filename = str(candidate.product_filename or candidate.data_uri or "unknown.fits").split("/")[-1]
        uri = str(candidate.data_uri or "")
        destination = cache_dir / filename
        emit_log(logger, logging.INFO, f"Download start: {filename}", progress)
        try:
            status, msg, url = Observations.download_file(uri, local_path=destination, cache=True, verbose=False)
            if status == "ERROR":
                raise RuntimeError(msg or "MAST download failed")
            emit_log(logger, logging.INFO, f"Download complete: {filename}", progress)
            manifest.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "product_identifier": candidate.obs_id or filename,
                    "stable_product_identifier": stable_product_identifier(candidate.extra_metadata.get("raw_product", {})),
                    "product_filename": candidate.product_filename,
                    "filter": candidate.filter_name,
                    "product_type": candidate.product_type,
                    "product_version": candidate.product_version,
                    "selection_rank": candidate.selection_rank,
                    "selected_reason": candidate.selected_reason,
                    "url": url,
                    "local_path": str(destination),
                    "file_size": destination.stat().st_size,
                    "checksum": sha256_file(destination),
                    "download_timestamp": None,
                    "status": status.lower(),
                }
            )
        except Exception as exc:  # pragma: no cover
            emit_log(logger, logging.ERROR, f"Download failed for {filename}: {exc}", progress)
            skipped.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "product_identifier": candidate.obs_id or filename,
                    "stable_product_identifier": stable_product_identifier(candidate.extra_metadata.get("raw_product", {})),
                    "url": uri,
                    "reason": str(exc),
                }
            )
    return manifest, skipped


def selection_summary(candidates: list[CandidateRecord]) -> dict[str, Any]:
    filters = sorted({candidate.filter_name for candidate in candidates if candidate.filter_name})
    instruments = sorted({candidate.instrument for candidate in candidates if candidate.instrument})
    missions = sorted({candidate.mission for candidate in candidates if candidate.mission})
    return {
        "candidate_count": len(candidates),
        "selected_count": sum(1 for candidate in candidates if candidate.selected),
        "auto_selected_count": sum(1 for candidate in candidates if candidate.auto_selected),
        "filters": filters,
        "instruments": instruments,
        "missions": missions,
    }


def _query_archive_rows(
    shape_kind: str,
    shape_kwargs: dict[str, Any],
    search: SearchConfig,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if shape_kind != "circle":
        raise ValueError(f"MAST discovery currently supports circle queries only; received {shape_kind}")

    emit_log(logger, logging.INFO, f"Archive query start: {shape_kind} region", progress)

    observations = Observations.query_region(
        f"{shape_kwargs['ra']} {shape_kwargs['dec']}",
        radius=f"{shape_kwargs['radius']} deg",
    )

    obs_rows = [dict(row) for row in observations]
    emit_log(logger, logging.INFO, f"Raw observation count: {len(obs_rows)}", progress)
    obs_rows = filter_observations(obs_rows, search)
    emit_log(logger, logging.INFO, f"Post-filter observation count: {len(obs_rows)}", progress)

    if not obs_rows:
        return [], []

    observation_metadata = _build_observation_metadata(obs_rows)
    observation_ids = list(dict.fromkeys(observation_metadata))
    emit_log(
        logger,
        logging.INFO,
        f"Product-batch fetch start: {len(observation_ids)} observations in batches of {PRODUCT_LIST_BATCH_SIZE}",
        progress,
    )

    product_rows: list[dict[str, Any]] = []
    batches = _batched(observation_ids, PRODUCT_LIST_BATCH_SIZE)
    for index, batch in enumerate(batches, start=1):
        emit_log(logger, logging.INFO, f"Product-batch fetch progress: {index}/{len(batches)} ({len(batch)} observations)", progress)
        products = Observations.get_product_list(batch)
        product_rows.extend(dict(row) for row in products)

    emit_log(logger, logging.INFO, f"Raw product count: {len(product_rows)}", progress)
    product_rows = _enrich_products(product_rows, observation_metadata)
    product_rows = filter_products(product_rows, search)
    emit_log(logger, logging.INFO, f"Post-filter product count: {len(product_rows)}", progress)
    return obs_rows, product_rows


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


def _candidate_id(product: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(product.get("obsid") or ""),
            str(product.get("obs_id") or product.get("obsID") or ""),
            str(product.get("filters") or product.get("filter") or ""),
            stable_product_identifier(product),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _version_rank(product: dict[str, Any]) -> tuple[int, ...]:
    version_source = " ".join(
        str(product.get(field, "") or "")
        for field in ("productVersion", "productSubGroupDescription", "dataURI", "productFilename")
    )
    version_parts = [int(part) for part in re.findall(r"\d+", version_source)]
    if version_parts:
        return tuple(-part for part in version_parts)
    return (0,)


def _build_observation_metadata(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for row in observations:
        obsid = str(row.get("obsid") or "")
        if not obsid:
            continue
        metadata[obsid] = {
            "_obs_t_min": row.get("t_min"),
            "_obs_t_max": row.get("t_max"),
            "_obs_exptime": row.get("t_exptime") or row.get("exptime") or row.get("exposure_time"),
            "_obs_collection": row.get("obs_collection"),
            "_obs_instrument": row.get("instrument_name"),
            "proposal_id": row.get("proposal_id") or row.get("proposal_pi"),
            "proposal_title": row.get("obs_title"),
            "target_name": row.get("target_name"),
        }
    return metadata


def _enrich_products(products: list[dict[str, Any]], observation_metadata: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for product in products:
        merged = dict(product)
        metadata = observation_metadata.get(str(product.get("obsid") or ""), {})
        merged.update(metadata)
        enriched.append(merged)
    return enriched


def _best_candidates_per_observation_filter(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    grouped: dict[tuple[str, str], list[CandidateRecord]] = {}
    for candidate in candidates:
        key = (
            str(candidate.obs_id or candidate.obsid or candidate.candidate_id),
            str(candidate.filter_name or "").upper(),
        )
        grouped.setdefault(key, []).append(candidate)
    return [sorted(grouped[key], key=_candidate_sort_key)[0] for key in sorted(grouped)]


def _auto_select_candidates(candidates: list[CandidateRecord], strategy: str, max_per_filter: int) -> list[CandidateRecord]:
    if strategy == "all":
        selected = [_copy_candidate(candidate) for candidate in candidates]
        for candidate in selected:
            candidate.auto_selection_reason = "selected:all"
        return sorted(selected, key=_candidate_sort_key)

    grouped: dict[str, list[CandidateRecord]] = {}
    for candidate in candidates:
        key = str(candidate.filter_name or candidate.candidate_id).upper()
        grouped.setdefault(key, []).append(candidate)

    selected: list[CandidateRecord] = []
    for key in sorted(grouped):
        ranked = sorted(grouped[key], key=lambda item: _observation_rank(item, strategy))
        kept = ranked[:max_per_filter]
        for candidate in kept:
            chosen = _copy_candidate(candidate)
            chosen.auto_selection_reason = f"selected:{strategy}"
            selected.append(chosen)
    return sorted(selected, key=_candidate_sort_key)


def _observation_rank(candidate: CandidateRecord, strategy: str) -> tuple[float, float, tuple[int, ...], tuple[Any, ...]]:
    end_date = _safe_float(candidate.observation_date_end, default=0.0)
    exposure = float(candidate.exposure_time or 0.0)
    rank = tuple(candidate.selection_rank[2]) if len(candidate.selection_rank) > 2 else (0,)
    selection_rank = _selection_rank_key(candidate)
    if strategy == "deepest_per_filter":
        return (-exposure, -end_date, rank, selection_rank)
    return (-end_date, -exposure, rank, selection_rank)


def _selected_priority_key(candidate: CandidateRecord, strategy: str) -> tuple[Any, ...]:
    if strategy in {"latest_per_filter", "deepest_per_filter"}:
        return _observation_rank(candidate, strategy)
    return _candidate_sort_key(candidate)


def _matches_narrowing_filters(candidate: CandidateRecord, inputs: SelectionInputs) -> bool:
    if inputs.include_filters and str(candidate.filter_name or "").upper() not in inputs.include_filters:
        return False
    if inputs.include_instruments and str(candidate.instrument or "").upper() not in inputs.include_instruments:
        return False
    if inputs.include_missions and str(candidate.mission or "").upper() not in inputs.include_missions:
        return False
    return True


def _matches_explicit_include(candidate: CandidateRecord, inputs: SelectionInputs) -> bool:
    obs_tokens = {str(candidate.obsid or ""), str(candidate.obs_id or "")}
    if any(token and token in inputs.include_obsids for token in obs_tokens):
        return True
    return bool(candidate.identity_tokens & inputs.include_products)


def _matches_explicit_exclude(candidate: CandidateRecord, inputs: SelectionInputs) -> bool:
    obs_tokens = {str(candidate.obsid or ""), str(candidate.obs_id or "")}
    if any(token and token in inputs.exclude_obsids for token in obs_tokens):
        return True
    return bool(candidate.identity_tokens & inputs.exclude_products)


def _dropped_reason_for_strategy(strategy: str) -> str:
    if strategy == "deepest_per_filter":
        return "dropped:shallower_than_peer"
    if strategy == "latest_per_filter":
        return "dropped:older_than_peer"
    return f"dropped:{strategy}"


def _candidate_sort_key(candidate: CandidateRecord) -> tuple[Any, ...]:
    return (
        str(candidate.filter_name or "").upper(),
        str(candidate.obs_id or candidate.obsid or ""),
        _selection_rank_key(candidate),
        candidate.candidate_id,
    )


def _selection_rank_key(candidate: CandidateRecord) -> tuple[Any, ...]:
    version_rank = tuple(candidate.selection_rank[2]) if len(candidate.selection_rank) > 2 else ()
    identifier = candidate.selection_rank[3] if len(candidate.selection_rank) > 3 else candidate.candidate_id
    return (candidate.selection_rank[0], candidate.selection_rank[1], version_rank, identifier)


def _copy_candidate(candidate: CandidateRecord) -> CandidateRecord:
    return CandidateRecord.from_dict(candidate.to_dict())


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _batched(items: list[str], batch_size: int) -> list[list[str]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _is_usable_display_product(product: dict[str, Any]) -> bool:
    filename = stable_product_identifier(product)
    filter_name = str(product.get("filters") or product.get("filter") or "").upper()
    mission = str(product.get("_obs_collection") or product.get("obs_collection") or "").upper()
    subgroup = str(product.get("productSubGroupDescription") or product.get("productVersion") or "").upper()

    if filename and not filename.endswith((".fits", ".fits.gz")):
        return False
    if filter_name in NON_DISPLAY_FILTERS:
        return False
    if ";" in filter_name:
        return False

    if mission == "JWST":
        return subgroup == "I2D" or filename.endswith("_i2d.fits") or filename.endswith("_i2d.fits.gz")
    if mission in {"HST", "HLA"}:
        return subgroup in {"DRC", "DRZ", "I2D"} or filename.endswith(("_drc.fits", "_drz.fits", "_drc.fits.gz", "_drz.fits.gz"))
    return True


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
