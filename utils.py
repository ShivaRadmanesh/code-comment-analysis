from os import path, rename, remove
import json
from typing import Literal
from openai.types.chat.chat_completion import ChatCompletion
import pickle as pkl
import jsonlines
from pydantic import BaseModel
from datetime import datetime, timedelta
from dataclasses import dataclass

RepoName = Literal[
    'ambari',
    'ant',
    'archiva',
    'aries',
    'beam',
    'cassandra',
    'cocoon',
    'cxf',
    'directory-server',
    'flink',
    'fop-cs',
    'geronimo',
    'hadoop',
    'ignite',
    'isis',
    'jclouds',
    'jena',
    'JMETER',
    'karaf',
    'lenya',
    'logging-log4j2',
    'maven',
    'mesos',
    'ofbizApp',
    'out',
    'poi',
    'qpid',
    'storm',
    'synapse',
    'tomcat',
    'tomee',
    'usergrid',
    'wicket'
]

DATA_PATH = "data/"
INPUTS_DIR = "in"
OUTPUTS_DIR = "out"
PARTIAL_DIR = "partial"


class CommitPair(BaseModel):
    old_commit_hash: str
    new_commit_hash: str
    old_method_content: str
    new_method_content: str
    old_comment: str
    new_comment: str
    file_path: str
    bug_introducing: bool
    old_commit_date: datetime
    new_commit_date: datetime
    id: str


class GptResponse(BaseModel):
    created: int
    response: str
    finish_reason: str
    usage: dict[str, int]
    id: str
    model: str

    @classmethod
    def from_ChatCompletion(cls, openai_res: ChatCompletion) -> 'GptResponse':
        d = {
            "id": openai_res.id,
            "response": openai_res.choices[0].message.content,
            "finish_reason": openai_res.choices[0].finish_reason,
            "usage": openai_res.usage.model_dump(),
            "model": openai_res.model,
            "created": openai_res.created
        }
        return cls(**d)


class Record(BaseModel):
    repo: str
    commit_pair: CommitPair

    gpt_response: GptResponse | None = None
    prompt: str | None = None
    attempts: int = 0

    class Filter:
        def __init__(self, data: list['Record'], filter: Literal['no_response'] | None = None, partial_save: int = 10):
            self.data = data
            if filter == 'no_response':
                self.filtered_indices = [i for i, r in enumerate(
                    data) if r.gpt_response is None]
            else:
                self.filtered_indices = range(len(data))

            self.iter = iter(self.filtered_indices)
            self.count = -1
            self.partial_save = partial_save

        def __iter__(self):
            return self

        def __next__(self):
            i = next(self.iter)
            if self.count % self.partial_save == 0:
                print("Saving partial result")
                save_records(self.data, partial=True)
            self.count += 1
            return self.data[i]

        def __len__(self):
            return len(self.filtered_indices)


def convert_commit_pair_2_records(cp_name: RepoName, auto_save=True,
                                  save_as: Literal["pkl", "jsonl"] = "pkl"):
    with open(path.join(DATA_PATH, INPUTS_DIR, f"{cp_name}.json"), 'r') as fin:
        # HOTFIX: json files have the field _id CommitPair expects id
        tmp = json.load(fin)
        for dp in tmp:
            dp["id"] = dp["_id"]
        cps = [CommitPair(**x) for x in tmp]

    records = [Record(repo=cp_name, commit_pair=cp) for cp in cps]
    if auto_save:
        save_path = path.join(DATA_PATH, OUTPUTS_DIR,
                              f"{cp_name}.{save_as}")
        if save_as == "pkl":
            save_records(records, repo_name=cp_name, invalidate_partial=False)
        elif save_as == "jsonl":
            json_res = [r.model_dump_json() for r in records]
            with jsonlines.open(save_path, 'w') as writer:
                writer.write_all(json_res)
        else:
            raise ValueError("save_as must be either pkl or jsonl.")
    return records


def load_records(repo_name: RepoName, auto_create=False, allow_partial=True):
    records_path = path.join(DATA_PATH, OUTPUTS_DIR, f"{repo_name}.pkl")
    if allow_partial and path.exists(path.join(DATA_PATH, OUTPUTS_DIR, PARTIAL_DIR, f"{repo_name}.pkl")):
        print("loading from partial data")
        records_path = path.join(DATA_PATH, OUTPUTS_DIR,
                                 PARTIAL_DIR, f"{repo_name}.pkl")

    if not path.exists(records_path) and auto_create:
        records_path = path.join(DATA_PATH, OUTPUTS_DIR, f"{repo_name}.pkl")
        convert_commit_pair_2_records(repo_name)

    if not path.exists(records_path):
        raise ValueError("Could not find records")

    with open(records_path, 'rb') as fin:
        records: list[Record] = pkl.load(fin)

    return records


def save_records(records: list[Record], repo_name: RepoName | None = None, partial=False, invalidate_partial=False):
    if not repo_name:
        repo_name = records[0].repo
    partial_path = path.join(DATA_PATH, OUTPUTS_DIR,
                             PARTIAL_DIR, f"{repo_name}.pkl")
    
    record_path = path.join(DATA_PATH, OUTPUTS_DIR, f"{repo_name}.pkl")
    
    if partial:
        save_path = partial_path
    else:
        save_path = record_path
        # Saving full/empty versions
        if path.exists(record_path):
            # backuping old data.
            directory, old_name = path.split(record_path)
            new_path = path.join(
                directory, f"{str(datetime.now().date())}-{old_name}")
            rename(record_path, new_path)

    with open(save_path, 'wb') as fout:
        pkl.dump(records, fout)

    # Remove partial only if save was successfull
    if not partial and invalidate_partial:
        if invalidate_partial and path.exists(partial_path):
            remove(partial_path)


@dataclass
class RecordResult:
    old2new: bool
    new2new: bool


@dataclass
class ParsedRecord:
    record: Record
    result: RecordResult


def print_info(name: str, segment: list[ParsedRecord], separator: str = ""):
    count7bi, count7nbi = 0, 0
    count14bi, count14nbi = 0, 0
    for r in segment:
        if r.record.commit_pair.bug_introducing:
            count14bi += 1
        else:
            count14nbi += 1
        if r.record.commit_pair.new_commit_date - r.record.commit_pair.old_commit_date <= timedelta(days=7):
            if r.record.commit_pair.bug_introducing:
                count7bi += 1
            else:
                count7nbi += 1
    print(
        f"| {name:^30} | {count14bi:^10} | {count14nbi:^10} | {count7bi:^10} | {count7nbi:^10} |")
    print(separator)
