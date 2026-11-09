from pydantic import BaseModel, ConfigDict
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel


class FormGroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    box: QGroupBox
    form: QFormLayout


class PanelHeader(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    head: QHBoxLayout
    notes: QHBoxLayout


class LegendNote(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    label: QLabel
    text: str
