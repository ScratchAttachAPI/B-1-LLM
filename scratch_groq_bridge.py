import getpass
import os
import sys
import time

import scratchattach as scratch
from groq import Groq
from scratchattach.utils.exceptions import LoginFailure


PROMPT_VARIABLE = "☁ prompt"
RESPONSE_VARIABLE = "☁ response"
REQUEST_ID_VARIABLE = "☁ request_id"
MAX_CLOUD_VALUE_LENGTH = 256
MAX_TEXT_LENGTH = (MAX_CLOUD_VALUE_LENGTH - 1) // 2
POLL_INTERVAL_SECONDS = 0.5
MODEL = "llama-3.3-70b-versatile"


class ScratchLoginError(Exception):
    pass


def encode_text(text: str) -> str:
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text must be at most {MAX_TEXT_LENGTH} characters.")
    if any(not 32 <= ord(character) <= 126 for character in text):
        raise ValueError("Text must contain printable ASCII characters only.")
    encoded = "".join(f"{ord(character) - 32:02d}" for character in text)
    return f"9{encoded}"


def decode_text(value: str) -> str:
    if not value.isascii() or not value.isdigit() or not value.startswith("9"):
        raise ValueError("Cloud prompt must start with the numeric encoding marker 9.")
    if (len(value) - 1) % 2:
        raise ValueError("Cloud prompt must contain two digits per encoded character.")
    characters = []
    for offset in range(1, len(value), 2):
        code = int(value[offset : offset + 2])
        if code > 94:
            raise ValueError("Cloud prompt contains an invalid encoded character.")
        characters.append(chr(code + 32))
    return "".join(characters)


def read_credentials() -> tuple[str, str, str, str, str]:
    session_id = os.environ.get("SCRATCH_SESSION_ID") or getpass.getpass(
        "Scratch session ID (leave blank to use username/password): "
    ).strip()
    username = ""
    password = ""
    if not session_id:
        username = input("Scratch username: ").strip()
        password = getpass.getpass("Scratch password: ")
    project_id = input("Scratch project ID: ").strip()
    api_key = os.environ.get("GROQ_API_KEY") or getpass.getpass("Groq API key: ")
    if (not session_id and (not username or not password)) or not project_id or not api_key:
        raise ValueError("Scratch authentication, project ID, and Groq API key are required.")
    return username, password, session_id, project_id, api_key


def main() -> None:
    username, password, session_id, project_id, api_key = read_credentials()
    try:
        if session_id:
            session = scratch.login_by_id(session_id, username=username or None)
        else:
            session = scratch.login(username, password)
    except LoginFailure as error:
        raise ScratchLoginError(
            "Scratch rejected username/password login. This can happen when the "
            "runtime's IP is blocked by Scratch. Run the bridge on your own "
            "computer, or restart and enter your Scratch session ID instead. "
            "Treat that ID like your password and never share it."
        ) from error
    cloud = session.connect_cloud(project_id)
    groq = Groq(api_key=api_key)

    current_request_id = int(cloud.get_var(REQUEST_ID_VARIABLE) or "0")
    response_value = cloud.get_var(RESPONSE_VARIABLE) or "0"
    last_request_id = current_request_id if response_value != "0" else None
    print("Connected. Waiting for new Scratch prompts; press Ctrl+C to stop.")

    try:
        while True:
            request_id = int(cloud.get_var(REQUEST_ID_VARIABLE) or "0")
            response_value = cloud.get_var(RESPONSE_VARIABLE) or "0"
            if request_id > 0 and request_id != last_request_id and response_value == "0":
                prompt_value = cloud.get_var(PROMPT_VARIABLE) or ""
                prompt = decode_text(prompt_value)
                if not prompt:
                    raise ValueError("Scratch submitted an empty prompt.")

                print(f"Received request {request_id}.")
                completion = groq.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Answer helpfully in printable ASCII only. "
                                "Keep the answer within 128 characters."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=120,
                )
                answer = completion.choices[0].message.content or ""
                ascii_answer = "".join(
                    character if 32 <= ord(character) <= 126 else " "
                    for character in answer.encode("ascii", "replace").decode("ascii")
                )
                if ascii_answer != answer:
                    print("Warning: unsupported response characters were replaced with spaces.")
                answer = ascii_answer
                if len(answer) > MAX_TEXT_LENGTH:
                    answer = answer[: MAX_TEXT_LENGTH - 3] + "..."
                    print("Warning: response was truncated to fit the Scratch cloud variable.")
                encoded_answer = encode_text(answer)
                cloud.set_var(RESPONSE_VARIABLE, encoded_answer or "0")
                last_request_id = request_id
                print(f"Response for request {request_id} sent to Scratch.")

            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping Scratch-Groq bridge.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, ScratchLoginError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
