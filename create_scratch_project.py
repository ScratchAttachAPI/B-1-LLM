import argparse
import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROMPT_VARIABLE_ID = "cloud_prompt"
RESPONSE_VARIABLE_ID = "cloud_response"
REQUEST_ID_VARIABLE_ID = "cloud_request_id"
VALID_VARIABLE_ID = "valid_prompt"
INDEX_VARIABLE_ID = "character_index"
CODE_VARIABLE_ID = "character_code"
CHARACTER_VARIABLE_ID = "current_character"
ENCODED_VARIABLE_ID = "encoded_text"
OUTPUT_VARIABLE_ID = "decoded_text"
CHARACTERS_LIST_ID = "ascii_characters"


@dataclass
class Block:
    opcode: str
    inputs: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, list[Any]] = field(default_factory=dict)
    next: "Block | None" = None


def number(value: Any) -> list[Any]:
    return [1, [4, str(value)]]


def text(value: str) -> list[Any]:
    return [1, [10, value]]


def reporter(opcode: str, inputs: dict[str, Any] | None = None,
             fields: dict[str, list[Any]] | None = None) -> Block:
    return Block(opcode, inputs or {}, fields or {})


def statement(opcode: str, inputs: dict[str, Any] | None = None,
              fields: dict[str, list[Any]] | None = None) -> Block:
    return Block(opcode, inputs or {}, fields or {})


def chain(*blocks: Block) -> Block | None:
    if not blocks:
        return None
    for current, following in zip(blocks, blocks[1:]):
        current.next = following
    return blocks[0]


def variable(name: str, identifier: str) -> Block:
    return reporter("data_variable", fields={"VARIABLE": [name, identifier]})


def set_variable(identifier: str, name: str, value: Any) -> Block:
    return statement(
        "data_setvariableto",
        inputs={"VALUE": value},
        fields={"VARIABLE": [name, identifier]},
    )


def change_variable(identifier: str, name: str, amount: Any) -> Block:
    return statement(
        "data_changevariableby",
        inputs={"VALUE": amount},
        fields={"VARIABLE": [name, identifier]},
    )


def list_index(item: Any) -> Block:
    return reporter(
        "data_itemnumoflist",
        inputs={"ITEM": item},
        fields={"LIST": ["characters", CHARACTERS_LIST_ID]},
    )


def make_prompt_script() -> Block:
    answer = reporter("sensing_answer")
    answer_length = reporter("operator_length", {"STRING": answer})
    too_long = reporter("operator_gt", {"OPERAND1": answer_length, "OPERAND2": number(127)})
    empty = reporter(
        "operator_equals",
        {
            "OPERAND1": reporter("operator_length", {"STRING": reporter("sensing_answer")}),
            "OPERAND2": number(0),
        },
    )
    index_is_zero = reporter(
        "operator_equals",
        {
            "OPERAND1": variable("character_index", INDEX_VARIABLE_ID),
            "OPERAND2": number(0),
        },
    )
    code_under_ten = reporter(
        "operator_lt",
        {"OPERAND1": variable("character_code", CODE_VARIABLE_ID), "OPERAND2": number(10)},
    )
    valid_equals_one = reporter(
        "operator_equals",
        {"OPERAND1": variable("valid_prompt", VALID_VARIABLE_ID), "OPERAND2": number(1)},
    )
    prompt_loop = statement(
        "control_repeat",
        inputs={
            "TIMES": reporter("operator_length", {"STRING": reporter("sensing_answer")}),
            "SUBSTACK": chain(
                set_variable(
                    CHARACTER_VARIABLE_ID,
                    "current_character",
                    reporter(
                        "operator_letter_of_string",
                        {
                            "LETTER": variable("character_index", INDEX_VARIABLE_ID),
                            "STRING": reporter("sensing_answer"),
                        },
                    ),
                ),
                set_variable(
                    INDEX_VARIABLE_ID,
                    "character_index",
                    list_index(variable("current_character", CHARACTER_VARIABLE_ID)),
                ),
                statement(
                    "control_if",
                    inputs={
                        "CONDITION": index_is_zero,
                        "SUBSTACK": set_variable(VALID_VARIABLE_ID, "valid_prompt", number(0)),
                    },
                ),
                set_variable(
                    CODE_VARIABLE_ID,
                    "character_code",
                    reporter(
                        "operator_subtract",
                        {"NUM1": variable("character_index", INDEX_VARIABLE_ID), "NUM2": number(1)},
                    ),
                ),
                statement(
                    "control_if_else",
                    inputs={
                        "CONDITION": code_under_ten,
                        "SUBSTACK": set_variable(
                            ENCODED_VARIABLE_ID,
                            "encoded_text",
                            reporter(
                                "operator_join",
                                {
                                    "STRING1": variable("encoded_text", ENCODED_VARIABLE_ID),
                                    "STRING2": reporter(
                                        "operator_join",
                                        {
                                            "STRING1": text("0"),
                                            "STRING2": variable("character_code", CODE_VARIABLE_ID),
                                        },
                                    ),
                                },
                            ),
                        ),
                        "SUBSTACK2": set_variable(
                            ENCODED_VARIABLE_ID,
                            "encoded_text",
                            reporter(
                                "operator_join",
                                {
                                    "STRING1": variable("encoded_text", ENCODED_VARIABLE_ID),
                                    "STRING2": variable("character_code", CODE_VARIABLE_ID),
                                },
                            ),
                        ),
                    },
                ),
                change_variable(INDEX_VARIABLE_ID, "character_index", number(1)),
            ),
        },
    )

    encoded_response = variable("cloud_response", RESPONSE_VARIABLE_ID)
    response_count = reporter(
        "operator_divide",
        {
            "NUM1": reporter("operator_subtract", {
                "NUM1": reporter("operator_length", {"STRING": encoded_response}),
                "NUM2": number(1),
            }),
            "NUM2": number(2),
        },
    )
    response_code = reporter(
        "operator_add",
        {
            "NUM1": reporter(
                "operator_multiply",
                {
                    "NUM1": reporter(
                        "operator_letter_of_string",
                        {
                            "LETTER": variable("character_index", INDEX_VARIABLE_ID),
                            "STRING": variable("cloud_response", RESPONSE_VARIABLE_ID),
                        },
                    ),
                    "NUM2": number(10),
                },
            ),
            "NUM2": reporter(
                "operator_letter_of_string",
                {
                    "LETTER": reporter(
                        "operator_add",
                        {"NUM1": variable("character_index", INDEX_VARIABLE_ID), "NUM2": number(1)},
                    ),
                    "STRING": variable("cloud_response", RESPONSE_VARIABLE_ID),
                },
            ),
        },
    )
    decoded_character = reporter(
        "data_itemoflist",
        inputs={
            "INDEX": reporter(
                "operator_add",
                {"NUM1": response_code, "NUM2": number(1)},
            )
        },
        fields={"LIST": ["characters", CHARACTERS_LIST_ID]},
    )
    decode_loop = statement(
        "control_repeat",
        inputs={
            "TIMES": response_count,
            "SUBSTACK": chain(
                set_variable(
                    OUTPUT_VARIABLE_ID,
                    "decoded_text",
                    reporter(
                        "operator_join",
                        {
                            "STRING1": variable("decoded_text", OUTPUT_VARIABLE_ID),
                            "STRING2": decoded_character,
                        },
                    ),
                ),
                change_variable(INDEX_VARIABLE_ID, "character_index", number(2)),
            ),
        },
    )
    wait_for_response = statement(
        "control_wait_until",
        inputs={
            "CONDITION": reporter(
                "operator_not",
                {
                    "OPERAND": reporter(
                        "operator_equals",
                        {
                            "OPERAND1": variable("cloud_response", RESPONSE_VARIABLE_ID),
                            "OPERAND2": number(0),
                        },
                    )
                },
            )
        },
    )

    submit_and_decode = chain(
        set_variable(PROMPT_VARIABLE_ID, "☁ prompt", variable("encoded_text", ENCODED_VARIABLE_ID)),
        set_variable(RESPONSE_VARIABLE_ID, "☁ response", number(0)),
        change_variable(REQUEST_ID_VARIABLE_ID, "☁ request_id", number(1)),
        wait_for_response,
        set_variable(OUTPUT_VARIABLE_ID, "decoded_text", text("")),
        set_variable(INDEX_VARIABLE_ID, "character_index", number(2)),
        decode_loop,
        statement(
            "looks_say",
            inputs={
                "MESSAGE": reporter(
                    "operator_join",
                    {"STRING1": text("Groq: "), "STRING2": variable("decoded_text", OUTPUT_VARIABLE_ID)},
                )
            },
        ),
    )
    invalid_message = statement(
        "looks_say",
        inputs={"MESSAGE": text("Use 1-127 printable ASCII characters.")},
    )

    length_invalid = reporter(
        "operator_or",
        {"OPERAND1": too_long, "OPERAND2": empty},
    )
    valid_prompt_branch = chain(
        statement(
            "control_if",
            inputs={
                "CONDITION": length_invalid,
                "SUBSTACK": set_variable(VALID_VARIABLE_ID, "valid_prompt", number(0)),
            },
        ),
        set_variable(ENCODED_VARIABLE_ID, "encoded_text", text("9")),
        set_variable(INDEX_VARIABLE_ID, "character_index", number(1)),
        prompt_loop,
        statement(
            "control_if_else",
            inputs={
                "CONDITION": valid_equals_one,
                "SUBSTACK": submit_and_decode,
                "SUBSTACK2": invalid_message,
            },
        ),
    )
    ask = statement("sensing_askandwait", inputs={"QUESTION": text("What should I ask Groq?")})
    ask.next = set_variable(VALID_VARIABLE_ID, "valid_prompt", number(1))
    ask.next.next = valid_prompt_branch
    return Block("event_whenthisspriteclicked", next=ask)


def serialize_blocks(roots: list[Block]) -> dict[str, dict[str, Any]]:
    blocks: dict[str, dict[str, Any]] = {}
    next_id = 0

    def serialize(block: Block | None, parent: str | None = None, top_level: bool = False,
                  x: int = 0, y: int = 0) -> str | None:
        nonlocal next_id
        if block is None:
            return None
        next_id += 1
        block_id = f"block_{next_id:04d}"
        blocks[block_id] = {
            "opcode": block.opcode,
            "next": None,
            "parent": parent,
            "inputs": {},
            "fields": block.fields,
            "shadow": False,
            "topLevel": top_level,
        }
        if top_level:
            blocks[block_id]["x"] = x
            blocks[block_id]["y"] = y
        for input_name, value in block.inputs.items():
            if isinstance(value, Block):
                child_id = serialize(value, block_id)
                blocks[block_id]["inputs"][input_name] = [2, child_id]
            elif isinstance(value, list) and value and isinstance(value[0], Block):
                first_id = serialize(value[0], block_id)
                blocks[block_id]["inputs"][input_name] = [2, first_id]
            else:
                blocks[block_id]["inputs"][input_name] = value
        following_id = serialize(block.next, block_id)
        blocks[block_id]["next"] = following_id
        return block_id

    for root_index, root in enumerate(roots):
        serialize(root, top_level=True, x=40, y=40 + root_index * 420)
    return blocks


def svg_asset(svg: str) -> tuple[dict[str, Any], tuple[str, bytes]]:
    data = svg.encode("utf-8")
    asset_id = hashlib.md5(data).hexdigest()
    return (
        {
            "name": "backdrop" if "width=\"480\"" in svg else "Groq",
            "bitmapResolution": 1,
            "dataFormat": "svg",
            "assetId": asset_id,
            "md5ext": f"{asset_id}.svg",
            "rotationCenterX": 0 if "width=\"480\"" in svg else 48,
            "rotationCenterY": 0 if "width=\"480\"" in svg else 48,
        },
        (f"{asset_id}.svg", data),
    )


def build_project() -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    backdrop, backdrop_file = svg_asset(
        '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360">'
        '<rect width="480" height="360" fill="#ffffff"/></svg>'
    )
    sprite_costume, sprite_file = svg_asset(
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
        '<circle cx="48" cy="48" r="44" fill="#6c5ce7"/>'
        '<path d="M27 32h42v8H27zm0 12h42v8H27zm0 12h28v8H27z" fill="#fff"/>'
        '<circle cx="66" cy="63" r="12" fill="#00cec9"/>'
        '<path d="M60 63l4 4 8-9" fill="none" stroke="#fff" stroke-width="3"/></svg>'
    )
    prompt_script = make_prompt_script()
    welcome_script = Block(
        "event_whenflagclicked",
        next=statement(
            "looks_say",
            inputs={"MESSAGE": text("Click me to send a prompt to Groq.")},
        ),
    )
    sprite_blocks = serialize_blocks([welcome_script, prompt_script])
    characters = [chr(code) for code in range(32, 127)]

    stage = {
        "isStage": True,
        "name": "Stage",
        "variables": {
            PROMPT_VARIABLE_ID: ["☁ prompt", 0, True],
            RESPONSE_VARIABLE_ID: ["☁ response", 0, True],
            REQUEST_ID_VARIABLE_ID: ["☁ request_id", 0, True],
        },
        "lists": {CHARACTERS_LIST_ID: ["characters", characters]},
        "broadcasts": {},
        "blocks": {},
        "comments": {},
        "currentCostume": 0,
        "costumes": [backdrop],
        "sounds": [],
        "volume": 100,
        "layerOrder": 0,
        "tempo": 60,
        "videoTransparency": 50,
        "videoState": "on",
        "textToSpeechLanguage": None,
    }
    sprite = {
        "isStage": False,
        "name": "Groq Bridge",
        "variables": {
            VALID_VARIABLE_ID: ["valid_prompt", 1],
            INDEX_VARIABLE_ID: ["character_index", 1],
            CODE_VARIABLE_ID: ["character_code", 0],
            CHARACTER_VARIABLE_ID: ["current_character", ""],
            ENCODED_VARIABLE_ID: ["encoded_text", "9"],
            OUTPUT_VARIABLE_ID: ["decoded_text", ""],
        },
        "lists": {},
        "broadcasts": {},
        "blocks": sprite_blocks,
        "comments": {},
        "currentCostume": 0,
        "costumes": [sprite_costume],
        "sounds": [],
        "volume": 100,
        "layerOrder": 1,
        "visible": True,
        "x": 0,
        "y": 0,
        "size": 100,
        "direction": 90,
        "draggable": False,
        "rotationStyle": "all around",
    }
    project = {
        "targets": [stage, sprite],
        "monitors": [],
        "extensions": [],
        "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "Scratch-Groq project generator"},
    }
    return project, [backdrop_file, sprite_file]


def create_sb3(destination: Path) -> None:
    project, assets = build_project()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", json.dumps(project, ensure_ascii=False, separators=(",", ":")))
        for asset_path, data in assets:
            archive.writestr(asset_path, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an importable Scratch-Groq .sb3 project.")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("Scratch-Groq.sb3"),
        help="destination .sb3 path (default: Scratch-Groq.sb3)",
    )
    args = parser.parse_args()
    destination = args.output if args.output.suffix.lower() == ".sb3" else args.output.with_suffix(".sb3")
    create_sb3(destination)
    print(f"Created {destination.resolve()}")


if __name__ == "__main__":
    main()
