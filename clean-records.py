from utils import *
import pickle as pkl

repo_name: RepoName = "storm"


def parse_gpt_response(response: str) -> (bool, bool):
    response = response.lower()
    true_keywords = ["true", "yes", "consistent"]
    false_keywords = ["false", "no", "inconsistent"]
    old2new_keywords = ["old2new"]
    new2new_keywords = ["new2new"]

    response_dict = json.loads(response)

    for old2new in old2new_keywords:
        if old2new in response_dict:
            if type(response_dict[old2new]) is bool:
                res_old2new = response_dict[old2new]
            elif response_dict[old2new] in true_keywords:
                res_old2new = True
            elif response_dict[old2new] in false_keywords:
                res_old2new = False
            else:
                raise Exception
            break
    else:
        raise Exception

    for new2new in new2new_keywords:
        if new2new in response_dict:
            if type(response_dict[new2new]) is bool:
                res_new2new = response_dict[new2new]
            elif response_dict[new2new] in true_keywords:
                res_new2new = True
            elif response_dict[new2new] in false_keywords:
                res_new2new = False
            else:
                raise Exception
            break
    else:
        raise Exception

    return (res_old2new, res_new2new)


records = load_records(repo_name, allow_partial=False)

failed_records = []
for r in records:
    if not r.gpt_response or r.gpt_response.finish_reason != "stop":
        failed_records.append(r)
        if r.gpt_response:
            print(r.gpt_response.finish_reason)

print(repo_name, ":Failed records:", len(failed_records))
action = input("continue by removing these records or not?[y/N]")
if action.lower() != "y":
    raise Exception

print(
    repo_name, f":removing {len(failed_records)} records from {len(records)}")
# remove failed records
for r in failed_records:
    records.remove(r)

print(repo_name, f":reamining records: {len(records)}")

parsed_records: list[ParsedRecord] = []
for r in records:
    try:
        pr = parse_gpt_response(r.gpt_response.response)
    except Exception as e:
        print(r.commit_pair.id, "="*40)
        print(r.gpt_response.response, flush=True)
        action = input("What to do? D to detele, 1:(TT), 2:(TF), 3:(FT), 4:(FF)")
        if action.lower() == "d":
            continue
        elif action == "1":
            pr = (True, True)
        elif action == "2":
            pr = (True, False)
        elif action == "3":
            pr = (False, True)
        elif action == "4":
            pr = (False, False)

    parsed_records.append(ParsedRecord(r, RecordResult(pr[0], pr[1])))

print(f"Done with {repo_name}. Saving {len(parsed_records)} parsed records.")

with open(f"data/out/cleaned/{repo_name}.pkl", "wb") as fout:
    pkl.dump(parsed_records, fout)
