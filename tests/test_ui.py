import pytest

from galaxy.ui import _parse_style_document


def test_parse_style_document_accepts_yaml_mapping() -> None:
    style = _parse_style_document(
        """
mapping:
  channels:
    red:
      - plane: red_plane
        weight: 1.5
tone:
  percentiles:
    black: 1.0
    white: 99.5
enabled_planes:
  - red_plane
"""
    )
    assert style["mapping"]["channels"]["red"][0]["plane"] == "red_plane"


def test_parse_style_document_rejects_non_mapping() -> None:
    with pytest.raises(ValueError):
        _parse_style_document("- just\n- a\n- list\n")
