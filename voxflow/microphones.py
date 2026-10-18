"""One entry per microphone: Windows lists each device once per audio interface (MME, DirectSound, WASAPI,
WDM-KS); VoxFlow shows the WASAPI ones, whose names are complete, plus "follow the system default"."""

from dataclasses import dataclass

from PySide6.QtCore import Qt

from .i18n import tr

SYSTEM_DEFAULT = -1  # list value for "follow the Windows default microphone"
SYSTEM_SETTING = "system"  # saved microphone/name for the system default
MICROPHONE_ROLE = Qt.ItemDataRole.UserRole + 1  # list item role holding the Microphone
PREFERRED_APIS = ("Windows WASAPI", "MME")
# Aliases Windows uses for "the default device" rather than a real microphone.
DEFAULT_ALIASES = ("microsoft 声音映射器", "microsoft sound mapper", "主声音捕获驱动程序", "primary sound capture driver")
VIRTUAL_HINTS = ("steam streaming", "todesk", "virtual", "vb-audio", "cable output", "voicemeeter",
                 "nvidia broadcast", "obs-camera", "oray")


@dataclass(frozen=True)
class Microphone:
    index: int  # sounddevice device index
    name: str
    virtual: bool


def _is_alias(name: str) -> bool:
    return name.strip().lower().startswith(DEFAULT_ALIASES)


def list_microphones(devices: list[dict], hostapis: list[dict]) -> list[Microphone]:
    """Real microphones first, then virtual ones, each once, from the best available audio interface."""
    inputs = [(index, device) for index, device in enumerate(devices) if device.get("max_input_channels", 0) > 0]
    api_names = [api.get("name", "") for api in hostapis]
    chosen = next((name for name in PREFERRED_APIS
                   if any(api_names[device["hostapi"]] == name for _index, device in inputs)), None)
    seen, real, virtual = set(), [], []
    for index, device in inputs:
        name = str(device["name"]).strip()
        if chosen is not None and api_names[device["hostapi"]] != chosen:
            continue
        if _is_alias(name) or name in seen:
            continue
        seen.add(name)
        is_virtual = any(hint in name.lower() for hint in VIRTUAL_HINTS)
        (virtual if is_virtual else real).append(Microphone(index, name, is_virtual))
    return real + virtual


def match_saved(saved: str, microphones: list[Microphone]) -> int | None:
    """Position in `microphones` of a saved choice (also old "name · interface" values), SYSTEM_DEFAULT for
    the default device, or None when that microphone is no longer connected."""
    name = str(saved or "").strip()
    if " · " in name:
        name = name.rsplit(" · ", 1)[0]
    if not name or name == SYSTEM_SETTING or _is_alias(name):
        return SYSTEM_DEFAULT
    for position, microphone in enumerate(microphones):
        if microphone.name == name:
            return position
    for position, microphone in enumerate(microphones):
        if len(name) >= 20 and microphone.name.startswith(name):  # MME cut the saved name at 31 characters
            return position
    return None


def microphone_label(microphone: "Microphone | None") -> str:
    """List text in the interface language: the default entry, or the name marked virtual when it is."""
    if microphone is None:
        return tr("mic.system_default")
    return tr("mic.virtual", name=microphone.name) if microphone.virtual else microphone.name


def stream_device(value):
    """The device to open for a list value: None asks sounddevice for the Windows default."""
    return None if value == SYSTEM_DEFAULT else value
