#%%
import concurrent.futures
from tqdm import tqdm 
import logging
import backoff
from utils import Record
import os

from openai import OpenAI, RateLimitError
from openai.types.chat.chat_completion import ChatCompletion
from utils import *

client = OpenAI(api_key=os.getenv("OPENAI_KEY", ""))

logging.getLogger('backoff').addHandler(logging.StreamHandler())
logging.getLogger('backoff').setLevel(level="INFO")
logging.getLogger().setLevel(level="INFO")


#%%

MODEL = "ft:gpt-3.5-turbo-1106:sepe:shiva-50s-2:9GJ3v0UT"


def get_gpt_prompt(record: Record) -> GptMessage:
    cp = record.commit_pair
    prompt = {
        "instructions": "Determine if the old comment remains consostent for the new code, focusing on the method's described functionality. A record is 'consistent' if the old comment still appropriately describes the method's functionality in the new code, ignoring syntactic changes that do not alter the described behavior. Direct contradictions, such as changes in method names, variables, or operations that fundamentally alter what's described, render a record 'inconsistent'. Assess whether any changes, including method signature adjustments or efficiency improvements, materially affect the method's described behavior. Use 'true' for consistent records and 'false' for inconsistent ones in your JSON response",
        "note": "Consider the impact of changes on the method's overall purpose and functionality. For example, replacing a direct equality check with a null-safe version (using 'Objects.equals') does not change the fundamental operation or its description. However, changing a method from returning the 'first' element to returning the 'last' element in a collection, or vice versa, significantly alters the described behavior and thus affects consistency.",

        "task": {
            "old_method_content": cp.old_method_content,
            "new_method_content": cp.new_method_content,
            "old_comment": cp.old_comment,
            "new_comment": cp.new_comment
        },
        "response_template": {
            "consistency": "<true/false>"
        }
    }
    return [
        {
            "role": "system",
            "content": json.dumps(prompt, indent=2)
        },
    ]


@backoff.on_exception(backoff.expo, RateLimitError, max_value=60)
def get_completion_with_backoff(message: GptMessage):
    response = client.chat.completions.create(
        model=MODEL,
        messages=message,
        response_format={
            "type": "json_object"},
        max_tokens=1000,
        temperature=0.3
    )
    return response

def ask_gpt(r: Record) -> ChatCompletion:
    r.prompt = get_gpt_prompt(r) 
    return get_completion_with_backoff(r.prompt)

#%%
def process_record(record:Record):
    response: ChatCompletion| None = None
    attempts = 0
    while not response and attempts<4:
        try:
            response = ask_gpt(record)
        except:
            record.attempts += 1
    if not response:
        print("FAILED :(")
    if response:
        record.gpt_response = GptResponse.from_ChatCompletion(response)
    return record


# %%
name = "gt"
records = load_records(name, allow_partial=False)

print(name, len(records))
#%%
with concurrent.futures.ProcessPoolExecutor(max_workers=12) as executor:
    futures = [executor.submit(process_record, record) for record in records]

    results = []
    with tqdm(total=len(records)) as pbar:
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            pbar.update(1)

#%%
with open(f'data/out/{name}--fintuned50S.pkl', 'wb') as fout:
    pkl.dump(results,fout)
