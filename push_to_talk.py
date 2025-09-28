import streamlit.components.v1 as components
import base64
import tempfile

_component_func = components.declare_component(
    "push_to_talk",
    path="./frontend/build",  # Path to compiled React app
)

def push_to_talk(label="Hold to Talk"):
    base64_audio = _component_func(default=None)
    if base64_audio is not None:
        audio_bytes = base64.b64decode(base64_audio)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(audio_bytes)
            return f.name
    return None
