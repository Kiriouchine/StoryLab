# Third-party software and models used by Story Lab

Story Lab's own code is Apache License 2.0. Nothing below is shipped inside
the Story Lab installer except uv.exe and 7zr.exe; everything else is
downloaded from its makers by Story Lab Setup, and each model and program
asks for your agreement to its licence first.

## Programs Setup installs or uses

| what | licence | where from |
|---|---|---|
| Python 3.11 (python-build-standalone, via uv) | PSF License | https://docs.python.org/3/license.html |
| uv (bundled) | MIT OR Apache-2.0 | https://github.com/astral-sh/uv |
| 7-Zip 7zr.exe (bundled) | public domain | https://www.7-zip.org |
| Ollama | MIT | https://github.com/ollama/ollama |
| ComfyUI (official Windows portable) | GPL-3.0 | https://github.com/Comfy-Org/ComfyUI |

Story Lab talks to Ollama and ComfyUI over their local web interfaces; it
does not include or modify their code.

## Models

| model | licence | page |
|---|---|---|
| Rocinante-X-12B v1 (TheDrummer), GGUF by bartowski | Mistral NeMo base: Apache-2.0; no separate licence stated for the fine-tune | https://huggingface.co/TheDrummer/Rocinante-X-12B-v1 |
| Kokoro-82M (hexgrad) | Apache-2.0 | https://huggingface.co/hexgrad/Kokoro-82M |
| Nova Furry XL IL v14.0 (Crody) | Illustrious base: Fair AI Public License 1.0-SD; creator permissions on CivitAI | https://civitai.com/models/503815 |
| lazyneg (janxd), optional | Illustrious base: FAIPL 1.0-SD; creator permissions on CivitAI | https://civitai.com/models/1302719 |
| Marshmallow Milk Anima v1.0 (mommymia) | Anima base: CircleStone Labs Non-Commercial License v1.2; creator permissions on CivitAI | https://civitai.com/models/2968947 |
| Anima Aesthetic v1.1 (CircleStone Labs), only without a CivitAI key | CircleStone Labs Non-Commercial License v1.2 | https://huggingface.co/circlestone-labs/Anima |
| Qwen3 0.6B text encoder | Apache-2.0 | https://huggingface.co/Qwen/Qwen3-0.6B-Base |
| Qwen-Image VAE | Apache-2.0 | https://huggingface.co/Qwen/Qwen-Image |
| ACE-Step 1.5 turbo + VAE (ACE-Step), music | MIT; ComfyUI repack by Comfy-Org: Apache-2.0 | https://huggingface.co/ACE-Step/Ace-Step1.5 |
| Qwen3 0.6B / 1.7B for ACE-Step, music | Apache-2.0 (Qwen3); repack Apache-2.0 | https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files |

"The CircleStone Model is licensed by CircleStone Labs LLC under the
CircleStone Non-Commercial License. Copyright CircleStone Labs LLC."

## Python packages (installed by uv from PyPI)

The full pinned list is requirements.txt. Most are MIT, BSD or Apache-2.0
(customtkinter, httpx, ollama, requests, numpy, pillow, torch, kokoro, misaki,
spacy, transformers, huggingface-hub, truststore...). Two that kokoro's
English phonemiser uses are GPL-3.0: phonemizer-fork and espeakng-loader
(espeak-ng). num2words is LGPL. They are installed on your PC from PyPI, not
shipped by Story Lab.
