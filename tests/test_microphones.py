from voxflow.microphones import SYSTEM_DEFAULT, list_microphones, match_saved, stream_device

APIS = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"}]


def device(name, api, inputs=1):
    return {"name": name, "hostapi": api, "max_input_channels": inputs}


# This PC: every microphone appears once per Windows audio interface, plus outputs and system aliases.
DEVICES = [
    device("Microsoft 声音映射器 - Input", 0),
    device("麦克风 (KZ Acoustics M2)", 0),
    device("麦克风 (Steam Streaming Microphone", 0),  # MME cuts names at 31 characters
    device("麦克风 (ToDesk Virtual Audio)", 0),
    device("麦克风 (Realtek(R) Audio)", 0),
    device("耳机 (张三的Pixel Buds Pro 2)", 0),
    device("扬声器 (Realtek(R) Audio)", 0, inputs=0),
    device("主声音捕获驱动程序", 1),
    device("麦克风 (KZ Acoustics M2)", 1),
    device("麦克风 (Steam Streaming Microphone)", 2),
    device("麦克风 (ToDesk Virtual Audio)", 2),
    device("麦克风 (Realtek(R) Audio)", 2),
    device("麦克风 (KZ Acoustics M2)", 2),
    device("耳机 (张三的Pixel Buds Pro 2)", 2),
    device("麦克风 (KZ Acoustics M2)", 3),
]


def test_each_microphone_is_listed_once_real_ones_first():
    mics = list_microphones(DEVICES, APIS)
    assert [mic.name for mic in mics] == [
        "麦克风 (Realtek(R) Audio)", "麦克风 (KZ Acoustics M2)", "耳机 (张三的Pixel Buds Pro 2)",
        "麦克风 (Steam Streaming Microphone)", "麦克风 (ToDesk Virtual Audio)"]
    assert [mic.virtual for mic in mics] == [False, False, False, True, True]
    assert mics[1].index == 12  # the WASAPI entry, whose name is complete


def test_falls_back_to_mme_without_wasapi():
    devices = [device("Microsoft 声音映射器 - Input", 0), device("麦克风 (USB)", 0), device("麦克风 (USB)", 1)]
    mics = list_microphones(devices, [{"name": "MME"}, {"name": "Windows DirectSound"}])
    assert [(mic.name, mic.index) for mic in mics] == [("麦克风 (USB)", 1)]


def test_no_input_devices_gives_an_empty_list():
    assert list_microphones([device("扬声器", 0, inputs=0)], APIS) == []


def test_saved_choice_from_the_old_list_still_matches():
    mics = list_microphones(DEVICES, APIS)
    assert match_saved("麦克风 (KZ Acoustics M2) · MME", mics) == 1
    assert match_saved("麦克风 (Steam Streaming Microphone · MME", mics) == 3  # truncated MME name
    assert match_saved("麦克风 (Realtek(R) Audio)", mics) == 0
    assert match_saved("主声音捕获驱动程序 · Windows DirectSound", mics) == SYSTEM_DEFAULT
    assert match_saved("Microsoft 声音映射器 - Input · MME", mics) == SYSTEM_DEFAULT
    assert match_saved("system", mics) == SYSTEM_DEFAULT
    assert match_saved("", mics) == SYSTEM_DEFAULT
    assert match_saved("麦克风 (unplugged)", mics) is None


def test_system_default_opens_the_default_device():
    assert stream_device(SYSTEM_DEFAULT) is None
    assert stream_device(12) == 12
