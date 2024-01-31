# %%
from tqdm import tqdm
import logging
import backoff
from utils import Record, CommitPair, GptResponse, RepoName, load_records, save_records
import os

from openai import OpenAI, APIError
from openai.types.chat.chat_completion import ChatCompletion

client = OpenAI(api_key=os.getenv("OPENAI_KEY", ""))

logging.getLogger('backoff').addHandler(logging.StreamHandler())
# %%

REPO_NAME: RepoName  = 'synapse'

# GPT 4 suggestion:
IMPROVED_SYSTEM_MESSAGE = """You will be provided a 4-element input comprising of "old_comment", "old_code", "new_comment", "new_code". Each encapsulated within XML tags (e.g., <old_comment>...</old_comment>). The "old_code" and "new_code" will contain Java code, and "old_comment" and "new_comment" will include comments describing the code. 

Your task includes:

1. Analyze if the "new_comment" appropriately describes the "old_code". 

2. Determine if the "new_comment" accurately explains the "new_code".

Give your responses according to the following JSON structure:
{
"old2new": <Does "new_comment" explain "old_code"?>,
"new2new": <Does "new_comment" describe "new_code"?>,
"reason-old2new": <Justify your "old2new" response>,
"reason-new2new": <Justify your "new2new" response>
}
"""


MODEL = "gpt-3.5-turbo-1106"


# %%

GptMessage = list
def get_gpt_message(commit_pair: CommitPair, system_message=IMPROVED_SYSTEM_MESSAGE) -> GptMessage:
    user_message = (f"<old_comment>{commit_pair.old_comment}</old_comment>\n"
                    f"<old_code>{commit_pair.old_method_content}</old_code>\n"
                    f"<new_comment>{commit_pair.new_comment}</new_comment>\n"
                    f"<new_code>{commit_pair.new_method_content}</new_code>")
    return [
        {
            "role": "system",
            "content": system_message
        },
        {
            "role": "user",
            "content": user_message
        },
    ]


@backoff.on_exception(backoff.expo, APIError, max_value=60)
def get_completion_with_backoff(message: GptMessage):
    response = client.chat.completions.create(
        model=MODEL,
        messages=message,
        response_format={
            "type": "json_object"},
        max_tokens=1000
    )
    return response

def ask_gpt(r: Record) -> ChatCompletion:
    r.prompt = get_gpt_message(r.commit_pair, system_message=IMPROVED_SYSTEM_MESSAGE) 
    return get_completion_with_backoff(r.prompt)

# %%
# Loading data
records = load_records(REPO_NAME, allow_partial=True, auto_create=True)
# %%
for r in tqdm(Record.Filter(records, filter='no_response', partial_save=10)):
    response: ChatCompletion = None
    while not response and r.attempts<4:
        try:
            response = ask_gpt(r)
        except:
            r.attempts += 1
    if not response:
        print("FAILED :(")
        continue
    r.gpt_response = GptResponse.from_ChatCompletion(response)

#%%
print("FINAL SAVE")
save_records(records, repo_name=REPO_NAME, partial=False, invalidate_partial=True)
