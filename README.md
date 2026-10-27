# Scratch-Groq Bridge

This script connects a Scratch project's cloud variables to the Groq chat API.
It watches a numeric-encoded prompt, sends it to Groq, and writes the encoded
answer back for the Scratch project to display.

## Requirements

- Python 3.10 or newer
- A Scratch account and a project with cloud-variable access
- A Groq API key

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Set `GROQ_API_KEY` in your environment to avoid being prompted for it, or let
the program ask for it securely. The key is never written to Scratch. Scratch
cloud variables only support numeric values, and putting an API key in a
project would expose it to anyone who can inspect the project.

Run the bridge:

```bash
python scratch_groq_bridge.py
```

Enter your Scratch username, password, and project ID when prompted. The
password and Groq API key are hidden as you type.

## Create and use the Scratch project

Generate the ready-to-import project archive:

```bash
python create_scratch_project.py
```

This creates `Scratch-Groq.sb3` in the current directory. You can choose a
different destination:

```bash
python create_scratch_project.py ./projects/my-groq-project.sb3
```

The archive contains a Scratch stage, a clickable sprite, the prompt and
response scripts, the three cloud variables, and the ASCII encoding list. Open
Scratch, choose **Create**, then use **File > Load from your computer** to
import the generated `.sb3` file. Save or share the project from Scratch to
use its cloud variables. If Scratch does not retain the cloud flags on import,
open the variable menu in the editor and enable cloud status for `prompt`,
`response`, and `request_id`.

Keep the bridge running, start the Scratch project, and click the sprite. Type
a prompt of 1-127 printable ASCII characters. The project sends it, waits for
the cloud response, decodes the answer, and displays it. Submit another
prompt by clicking the sprite again.

The encoded prompt and response each fit within Scratch's 256-character cloud
variable limit: a `9` marker plus two digits for each of up to 127 characters.
The project rejects empty, overlong, or non-ASCII prompts. The bridge replaces
unsupported Groq response characters with spaces and truncates long answers.

## Cloud-variable protocol

| Variable | Purpose |
| --- | --- |
| `☁ prompt` | `9` marker followed by two decimal digits per character |
| `☁ request_id` | Increase by 1 each time a new prompt is submitted |
| `☁ response` | Answer encoded in the same format; `0` means no response yet |

Keep the bridge running while using the Scratch project. Cloud-variable
updates are visible to other users of a shared project; do not submit private
information in prompts.