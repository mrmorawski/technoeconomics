import pytest
from pydantic import TypeAdapter, ValidationError

from technoeconomics.data import (
    Constant,
    ScalarDataset,
)

SCALAR = TypeAdapter(ScalarDataset)


class TestTaggedCodec:
    def test_in_memory_object_passes_through(self):
        ds = Constant(1.0)
        assert SCALAR.validate_python(ds) is ds

    def test_unknown_type_tag_rejected(self):
        with pytest.raises(ValidationError, match="unknown dataset type"):
            SCALAR.validate_python({"type": "NoSuchDataset", "value": 1.0})

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            SCALAR.validate_python({"type": "Constant", "value": 1.0, "bogus": 2.0})
