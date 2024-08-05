import os
from datetime import datetime
import logging
import openai
import json
import re
from dotenv import load_dotenv

load_dotenv()


def save_prompt(messages, filename):
    with open(filename + ".prompt.json", "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=4, ensure_ascii=False)


logging.getLogger().setLevel(logging.CRITICAL)
log = logging.getLogger("Anki Card Creator")
log.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
log.addHandler(console_handler)

OPEN_AI_KEY = os.getenv("OPEN_AI_KEY")
organization = os.getenv("ORGANIZATION_ID")
project = os.getenv("PROJECT_ID")

if OPEN_AI_KEY is None or organization is None or project is None:
    log.error(
        "Missing environment variables. Please set OPEN_AI_KEY, ORGANIZATION_ID and PROJECT_ID."
    )
    exit(1)

log.info("Welcome to Anki Card Creator !")

# FORCED_TIMESTAMP = "20240805_175528"
FORCED_TIMESTAMP = None
# USE_EXISTING_CREATED = True
USE_EXISTING_CREATED = False
SKIP_ERASING = True

client = openai.Client(organization=organization, project=project, api_key=OPEN_AI_KEY)
timestamp = (
    datetime.now().strftime("%Y%m%d_%H%M%S")
    if FORCED_TIMESTAMP is None
    else FORCED_TIMESTAMP
)
outputs_dir = f"./outputs/{timestamp}"

log.debug(
    f"Configuration: FORCED_TIMESTAMP={FORCED_TIMESTAMP}, USE_EXISTING_CREATED={USE_EXISTING_CREATED}"
)

if not os.path.exists(outputs_dir):
    log.debug(f"Creating directory {outputs_dir}")
    os.mkdir(outputs_dir)

if not USE_EXISTING_CREATED:
    # Ask user to get is document as txt
    log.debug(f"Reading file 'inputs/text.txt'")
    input = open("inputs/text.txt", "r", encoding="utf-8").read()

    words_by_chunk = 1000
    # Split the text into chunks of <words_by_chunk> words
    splitted_text = input.split(" ")
    chunks = [
        " ".join(splitted_text[i : i + words_by_chunk])
        for i in range(0, len(splitted_text), words_by_chunk)
    ]
    log.debug(f"Chunks created with length {words_by_chunk} words")

    log.debug(f"Start asking chat gpt Q/A ({len(chunks)} steps)...")
    # For each chunk ask chatgpt the chunck of word with the system prompt in './system-prompt-creator.txt'
    # For each output write the output in dedicated file with timestamp as filename 'created' as suffix
    # Iterate over each chunk
    for i, chunk in enumerate(chunks):
        # Create a new timestamped filename
        filename = f"{outputs_dir}/created_{i}"

        messages = [
            {
                "role": "system",
                "content": open("./system-prompt-creator.txt", "r", encoding="utf-8")
                .read()
                .encode("utf-8")
                .decode(),
            },
            {"role": "user", "content": chunk},
        ]

        # Prompt the model to generate output
        response = client.chat.completions.create(
            model="gpt-4o", max_tokens=4095, messages=messages
        )

        # Write the prompt
        save_prompt(messages, filename)

        # Write the output to the file
        with open(filename + ".txt", "w", encoding="utf-8") as f:
            f.write(response.choices[0].message.content.encode("utf-8").decode())

        # Print the filename
        log.debug(f"[{(i+1)}/{len(chunks)}] Write chat gpt answer in file {filename}.")

    log.debug("Chat gpt as done.")
else:
    log.info(f"Using existing created file {FORCED_TIMESTAMP}")


# Aggregate all the outputs in variable outputs_agregated
outputs_agregated = []
log.debug("Start aggregating outputs ...")
for filename in os.listdir(outputs_dir):
    if filename.startswith("created") and not filename.endswith(".prompt.json"):
        with open(f"{outputs_dir}/{filename}", "r", encoding="utf-8") as f:
            outputs_agregated.append(f.read())

outputs_agregated_as_txt = "\n".join(outputs_agregated)

result = re.findall("(.*);(.*)", outputs_agregated_as_txt)
number_before_trimming = len(result)
log.debug(f"Found {len(result)} Q/A")
result = "\n".join([f"{x[0]};{x[1]}" for x in result])


if not SKIP_ERASING:
    # ask chatgpt the output in './system-prompt-eraser.txt'
    log.debug("Prepare final prompt for chatgpt ...")
    prompt = {"role": "user", "content": outputs_agregated_as_txt}

    response = None
    try:
        filename = f"{outputs_dir}/erased"
        messages = [
            {
                "role": "system",
                "content": open("./system-prompt-eraser.txt", "r", encoding="utf-8")
                .read()
                .encode("utf-8")
                .decode(),
            },
            prompt,
        ]

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=4096,
            messages=messages,
            stream=True,
        )

        save_prompt(messages, filename)

        full_response = ""

        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                full_response += chunk.choices[0].delta.content

        result = re.findall("(.*);(.*)", full_response)
        number_after_trimming = len(result)
        result = "\n".join([f"{x[0]};{x[1]}" for x in result])

        log.debug(
            f"Found {number_after_trimming} Q/A after trimming {number_before_trimming} Q/A"
        )

        # write the output in dedicated file with timestamp as filename and 'erased' as suffix
        with open(filename + ".txt", "w", encoding="utf-8") as f:
            f.write(result.encode("utf-8").decode())

        log.debug(f"Good news ! Your anki cards as csv are ready ! {filename}")

    except Exception as e:
        print(e)

filename = f"{outputs_dir}/result"
# write the output in dedicated file with timestamp as filename and 'erased' as suffix
with open(filename + ".txt", "w", encoding="utf-8") as f:
    f.write(result.encode("utf-8").decode())
