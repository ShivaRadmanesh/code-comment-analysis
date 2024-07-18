# %%
from utils import *
from openai import OpenAI
import os
import json
# %%


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


def get_train_data(record, label):
    return {
        "messages": [
            get_gpt_prompt(record)[0],
            {
                "role": "assistant",
                "content": json.dumps({"consistency": label}, indent=2)
            }
        ]
    }


# %%
# LOADING DATA
records = load_records('valid')
# %%
gt = {}
# Load a sample of the IDs
with open('data/temp/readableSamples/fine_tune - train.csv', 'r') as fin:
    for l in fin:
        l = l.strip("\n")
        id, label = l.split(',')
        gt[id] = int(label)


# %%
# Keep only the sampled ids
filtered_records = [r for r in records if r.commit_pair.id in gt]

# %%
# create training data
# JSONL FORMAT {messages: [M1, R1]}
train_data = [get_train_data(r, not bool(gt[r.commit_pair.id]))
              for r in filtered_records]

# %% Create the file
with open('data/temp/finetune-train.jsonl', 'w') as fout:
    for d in train_data:
        fout.write(json.dumps(d))
        fout.write("\n")

# %%
gt = {}
# Load IDs and create validation.csv
with open('data/temp/readableSamples/fine_tune - validation.csv', 'r') as fin:
    for l in fin:
        l = l.strip("\n")
        id, label = l.split(',')
        gt[id] = int(label)
filtered_records = [r for r in records if r.commit_pair.id in gt]


train_data = [get_train_data(r, not bool(gt[r.commit_pair.id]))
              for r in filtered_records]

with open('data/temp/finetune-valid.jsonl', 'w') as fout:
    for d in train_data:
        fout.write(json.dumps(d))
        fout.write("\n")

# %% Get client
client = OpenAI(api_key=os.getenv("OPENAI_KEY", ""))
#%%
# %% Upload file
train_file_id = client.files.create(
    file=open("data/temp/shiva-finetune-train.jsonl", "rb"),
    purpose="fine-tune"
)

# %%
validation_file_id = client.files.create(
    file=open("data/temp/shiva-finetune-valid.jsonl", "rb"),
    purpose="fine-tune"
)
# %%
#!!!!!!!!!!!! Create Fine tuning Job
job = client.fine_tuning.jobs.create(training_file=train_file_id.id,
                                     validation_file=validation_file_id.id,
                                     model="gpt-3.5-turbo-1106",
                                     suffix="shiva-50S-2",
                                     )
