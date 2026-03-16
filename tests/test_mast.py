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
