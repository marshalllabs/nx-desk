from typing import Union

from pydantic import JsonValue, TypeAdapter

JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(type=JsonValue)


def parse_json(text: Union[str, bytes]) -> JsonValue:
    return JSON_VALUE.validate_json(text)


def json_value(value: object) -> JsonValue:
    return JSON_VALUE.validate_python(value)
