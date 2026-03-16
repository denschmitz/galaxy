from galaxy.config import SearchConfig
from galaxy.mast import filter_products, rank_product, select_products


def test_filter_products_respects_filters_and_type() -> None:
    rows = [
        {"detector": "WFC3", "filters": "F606W", "productType": "SCIENCE"},
        {"detector": "NIRCAM", "filters": "F200W", "productType": "SCIENCE"},
    ]
    filtered = filter_products(
        rows,
        SearchConfig(detectors=["NIRCAM"], filters=["F200W"], product_types=["SCIENCE"]),
    )
    assert filtered == [rows[1]]


def test_select_products_is_deterministic() -> None:
    products = [
        {"obs_id": "A", "filters": "F200W", "productType": "CAL", "productFilename": "a_cal.fits"},
        {"obs_id": "A", "filters": "F200W", "productType": "SCIENCE", "productFilename": "a_sci.fits"},
    ]
    selected = select_products(products)
    assert selected[0]["productType"] == "SCIENCE"
    assert rank_product(selected[0]) < rank_product(products[0])


def test_select_products_prefers_newer_version_then_identifier() -> None:
    products = [
        {
            "obs_id": "A",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "jw_a_v1.fits",
            "productSubGroupDescription": "v1",
        },
        {
            "obs_id": "A",
            "filters": "F200W",
            "productType": "SCIENCE",
            "productFilename": "jw_a_v3.fits",
            "productSubGroupDescription": "v3",
        },
    ]
    selected = select_products(products)
    assert selected[0]["productFilename"] == "jw_a_v3.fits"


def test_select_products_can_keep_latest_per_filter() -> None:
    products = [
        {"obs_id": "A", "filters": "F657N", "productType": "SCIENCE", "productFilename": "a.fits", "_obs_t_max": 1.0},
        {"obs_id": "B", "filters": "F657N", "productType": "SCIENCE", "productFilename": "b.fits", "_obs_t_max": 5.0},
        {"obs_id": "C", "filters": "F673N", "productType": "SCIENCE", "productFilename": "c.fits", "_obs_t_max": 3.0},
    ]
    selected = select_products(products, SearchConfig(observation_selection="latest_per_filter", max_observations_per_filter=1))
    assert [item["productFilename"] for item in selected] == ["b.fits", "c.fits"]


def test_select_products_can_keep_deepest_per_filter() -> None:
    products = [
        {"obs_id": "A", "filters": "F657N", "productType": "SCIENCE", "productFilename": "a.fits", "_obs_exptime": 100.0},
        {"obs_id": "B", "filters": "F657N", "productType": "SCIENCE", "productFilename": "b.fits", "_obs_exptime": 300.0},
        {"obs_id": "C", "filters": "F673N", "productType": "SCIENCE", "productFilename": "c.fits", "_obs_exptime": 200.0},
    ]
    selected = select_products(products, SearchConfig(observation_selection="deepest_per_filter", max_observations_per_filter=1))
    assert [item["productFilename"] for item in selected] == ["b.fits", "c.fits"]
